#!/usr/bin/env python3
"""
paris_sorties.py : trouver des événements et des bars à Paris via des API publiques et gratuites.

Sources (aucune clé requise) :
  - Événements : jeu de données « Que faire à Paris ? » (opendata.paris.fr, API Opendatasoft v2.1)
  - Bars       : OpenStreetMap via l'API Overpass
  - Géocodage  : Nominatim (OpenStreetMap), pour transformer une adresse en coordonnées

Exemples :
  python paris_sorties.py events --adresse "Place de la Bastille, Paris" --rayon 1000
  python paris_sorties.py events --lat 48.8566 --lon 2.3522 --gratuit --jours 7
  python paris_sorties.py bars --adresse "Canal Saint-Martin" --rayon 500
  python paris_sorties.py bars --limite 50 --json > bars.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone

import requests

# --- Configuration (surchargeable par variables d'environnement, jamais de secret en dur) ---
USER_AGENT = os.environ.get(
    "PARIS_SORTIES_USER_AGENT",
    "paris-sorties/1.0 (+https://github.com/)",  # mettez l'URL de votre dépôt ou un contact
)
QFAP_URL = os.environ.get(
    "QFAP_URL",
    "https://opendata.paris.fr/api/explore/v2.1/catalog/datasets/que-faire-a-paris-/records",
)
OVERPASS_URL = os.environ.get("OVERPASS_URL", "https://overpass-api.de/api/interpreter")
NOMINATIM_URL = os.environ.get("NOMINATIM_URL", "https://nominatim.openstreetmap.org/search")
TIMEOUT = int(os.environ.get("PARIS_SORTIES_TIMEOUT", "60"))

# Centre de Paris (Notre-Dame), utilisé quand aucune position n'est donnée.
PARIS_CENTRE = (48.8530, 2.3499)

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT, "Accept": "application/json"})


# --------------------------------------------------------------------------------------------
# Utilitaires
# --------------------------------------------------------------------------------------------
def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance à vol d'oiseau en mètres (formule de haversine)."""
    r = 6_371_000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def geocoder(adresse: str) -> tuple[float, float, str]:
    """Adresse -> (lat, lon, libellé) via Nominatim. Limite d'usage : 1 requête/seconde."""
    resp = session.get(
        NOMINATIM_URL,
        params={"q": adresse, "format": "jsonv2", "limit": 1, "countrycodes": "fr"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    resultats = resp.json()
    if not resultats:
        raise SystemExit(f"Adresse introuvable : {adresse!r}")
    r = resultats[0]
    return float(r["lat"]), float(r["lon"]), r.get("display_name", adresse)


def resoudre_position(args: argparse.Namespace) -> tuple[float, float, str] | None:
    """Renvoie la position demandée (adresse ou lat/lon), ou None si aucune."""
    if args.adresse:
        return geocoder(args.adresse)
    if args.lat is not None and args.lon is not None:
        return args.lat, args.lon, f"{args.lat:.5f}, {args.lon:.5f}"
    if (args.lat is None) != (args.lon is None):
        raise SystemExit("Indiquez à la fois --lat et --lon.")
    return None


def formater_distance(d: float | None) -> str:
    if d is None:
        return ""
    return f"{d:.0f} m" if d < 1000 else f"{d / 1000:.1f} km"


# --------------------------------------------------------------------------------------------
# Événements : « Que faire à Paris ? »
# --------------------------------------------------------------------------------------------
@dataclass
class Evenement:
    titre: str
    debut: str | None
    fin: str | None
    lieu: str | None
    adresse: str | None
    prix: str | None
    url: str | None
    resume: str | None
    lat: float | None = None
    lon: float | None = None
    distance_m: float | None = None
    tags: list[str] = field(default_factory=list)


def chercher_evenements(
    position: tuple[float, float] | None,
    rayon_m: int,
    jours: int,
    gratuit: bool,
    recherche: str | None,
    limite: int,
) -> list[Evenement]:
    maintenant = datetime.now(timezone.utc)
    horizon = maintenant + timedelta(days=jours)

    # Requête ODSQL : événements pas encore terminés, qui commencent avant l'horizon.
    clauses = [
        f"date_end >= date'{maintenant:%Y-%m-%dT%H:%M:%S}'",
        f"date_start <= date'{horizon:%Y-%m-%dT%H:%M:%S}'",
    ]
    if position:
        lat, lon = position
        clauses.append(f"within_distance(lat_lon, geom'POINT({lon} {lat})', {rayon_m}m)")
    if gratuit:
        clauses.append("price_type = 'gratuit'")
    if recherche:
        clauses.append(f'search("{recherche.replace(chr(34), "")}")')

    evenements: list[Evenement] = []
    offset, page = 0, 100  # l'API limite à 100 résultats par appel
    while len(evenements) < limite:
        resp = session.get(
            QFAP_URL,
            params={
                "where": " AND ".join(clauses),
                "order_by": "date_start",
                "limit": min(page, limite - len(evenements)),
                "offset": offset,
            },
            timeout=TIMEOUT,
        )
        resp.raise_for_status()
        resultats = resp.json().get("results", [])
        if not resultats:
            break
        for r in resultats:
            coords = r.get("lat_lon") or {}
            elat, elon = coords.get("lat"), coords.get("lon")
            adresse = " ".join(
                str(x) for x in (r.get("address_street"), r.get("address_zipcode"), r.get("address_city")) if x
            )
            tags = r.get("qfap_tags") or r.get("tags") or []
            if isinstance(tags, str):
                tags = [t.strip() for t in tags.split(";") if t.strip()]
            ev = Evenement(
                titre=r.get("title") or "(sans titre)",
                debut=r.get("date_start"),
                fin=r.get("date_end"),
                lieu=r.get("address_name"),
                adresse=adresse or None,
                prix=r.get("price_type"),
                url=r.get("url"),
                resume=r.get("lead_text"),
                lat=elat,
                lon=elon,
                tags=list(tags),
            )
            if position and elat is not None and elon is not None:
                ev.distance_m = round(distance_m(position[0], position[1], elat, elon))
            evenements.append(ev)
        offset += len(resultats)
        if len(resultats) < page:
            break
    return evenements


def afficher_evenements(evenements: list[Evenement]) -> None:
    if not evenements:
        print("Aucun événement trouvé.")
        return
    for i, ev in enumerate(evenements, 1):
        quand = (ev.debut or "")[:16].replace("T", " ")
        if ev.fin and ev.fin[:10] != (ev.debut or "")[:10]:
            quand += f" → {ev.fin[:10]}"
        print(f"{i:>3}. {ev.titre}")
        print(f"     📅 {quand}   💶 {ev.prix or '?'}   {formater_distance(ev.distance_m)}")
        if ev.lieu or ev.adresse:
            print(f"     📍 {' · '.join(x for x in (ev.lieu, ev.adresse) if x)}")
        if ev.url:
            print(f"     🔗 {ev.url}")
    print(f"\n{len(evenements)} événement(s).")


# --------------------------------------------------------------------------------------------
# Bars : OpenStreetMap / Overpass
# --------------------------------------------------------------------------------------------
@dataclass
class Bar:
    nom: str
    type: str
    adresse: str | None
    horaires: str | None
    site: str | None
    telephone: str | None
    lat: float
    lon: float
    distance_m: float | None = None
    osm: str = ""


def chercher_bars(position: tuple[float, float] | None, rayon_m: int, types: list[str]) -> list[Bar]:
    filtre_types = "|".join(types)
    if position:
        lat, lon = position
        zone = f"(around:{rayon_m},{lat},{lon})"
        prefixe = ""
    else:
        # Toute la commune de Paris (relation administrative de niveau 8).
        prefixe = 'area["boundary"="administrative"]["admin_level"="8"]["name"="Paris"]->.paris;\n'
        zone = "(area.paris)"
    requete = (
        f"[out:json][timeout:{TIMEOUT}];\n{prefixe}"
        f'nwr["amenity"~"^({filtre_types})$"]{zone};\n'
        "out center tags;"
    )
    resp = session.post(OVERPASS_URL, data={"data": requete}, timeout=TIMEOUT + 15)
    resp.raise_for_status()

    bars: list[Bar] = []
    for el in resp.json().get("elements", []):
        t = el.get("tags", {})
        blat = el.get("lat") or el.get("center", {}).get("lat")
        blon = el.get("lon") or el.get("center", {}).get("lon")
        if blat is None or blon is None:
            continue
        adresse = " ".join(
            x for x in (t.get("addr:housenumber"), t.get("addr:street"), t.get("addr:postcode")) if x
        )
        bar = Bar(
            nom=t.get("name", "(sans nom)"),
            type=t.get("amenity", ""),
            adresse=adresse or None,
            horaires=t.get("opening_hours"),
            site=t.get("website") or t.get("contact:website"),
            telephone=t.get("phone") or t.get("contact:phone"),
            lat=blat,
            lon=blon,
            osm=f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
        )
        if position:
            bar.distance_m = round(distance_m(position[0], position[1], blat, blon))
        bars.append(bar)

    if position:
        bars.sort(key=lambda b: b.distance_m or 0)
    else:
        bars.sort(key=lambda b: b.nom.lower())
    return bars


def afficher_bars(bars: list[Bar], total: int) -> None:
    if not bars:
        print("Aucun bar trouvé.")
        return
    for i, b in enumerate(bars, 1):
        print(f"{i:>3}. {b.nom}  [{b.type}]  {formater_distance(b.distance_m)}")
        if b.adresse:
            print(f"     📍 {b.adresse}")
        if b.horaires:
            print(f"     🕒 {b.horaires}")
        if b.site:
            print(f"     🔗 {b.site}")
    suffixe = f" (sur {total} trouvés)" if total > len(bars) else ""
    print(f"\n{len(bars)} bar(s) affiché(s){suffixe}.")


# --------------------------------------------------------------------------------------------
# Interface en ligne de commande
# --------------------------------------------------------------------------------------------
def ajouter_options_position(p: argparse.ArgumentParser, rayon_defaut: int) -> None:
    g = p.add_argument_group("position (facultatif)")
    g.add_argument("--adresse", help='adresse ou lieu, ex. "Place de la République, Paris"')
    g.add_argument("--lat", type=float, help="latitude, ex. 48.8566")
    g.add_argument("--lon", type=float, help="longitude, ex. 2.3522")
    g.add_argument("--rayon", type=int, default=rayon_defaut, help=f"rayon en mètres (défaut {rayon_defaut})")
    p.add_argument("--limite", type=int, default=20, help="nombre maximum de résultats (défaut 20)")
    p.add_argument("--json", action="store_true", help="sortie JSON au lieu du texte")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Événements et bars à Paris via des API publiques (Que faire à Paris, OpenStreetMap).",
    )
    sub = parser.add_subparsers(dest="commande", required=True)

    p_ev = sub.add_parser("events", help="événements à venir (« Que faire à Paris ? »)")
    ajouter_options_position(p_ev, rayon_defaut=2000)
    p_ev.add_argument("--jours", type=int, default=7, help="fenêtre de recherche en jours (défaut 7)")
    p_ev.add_argument("--gratuit", action="store_true", help="seulement les événements gratuits")
    p_ev.add_argument("--recherche", help='mot-clé, ex. "jazz" ou "exposition"')

    p_bar = sub.add_parser("bars", help="bars de Paris (OpenStreetMap)")
    ajouter_options_position(p_bar, rayon_defaut=800)
    p_bar.add_argument(
        "--types",
        default="bar,pub,biergarten",
        help="types OSM séparés par des virgules (défaut bar,pub,biergarten)",
    )

    args = parser.parse_args(argv)

    try:
        pos = resoudre_position(args)
        coords = (pos[0], pos[1]) if pos else None
        if pos and not args.json:
            print(f"📌 Position : {pos[2]} (rayon {formater_distance(args.rayon)})\n", file=sys.stderr)

        if args.commande == "events":
            evenements = chercher_evenements(
                coords, args.rayon, args.jours, args.gratuit, args.recherche, args.limite
            )
            if args.json:
                print(json.dumps([asdict(e) for e in evenements], ensure_ascii=False, indent=2))
            else:
                afficher_evenements(evenements)
        else:
            types = [t.strip() for t in args.types.split(",") if t.strip()]
            tous = chercher_bars(coords, args.rayon, types)
            bars = tous[: args.limite]
            if args.json:
                print(json.dumps([asdict(b) for b in bars], ensure_ascii=False, indent=2))
            else:
                afficher_bars(bars, len(tous))
    except requests.HTTPError as e:
        corps = e.response.text[:300] if e.response is not None else ""
        print(f"Erreur HTTP de l'API : {e}\n{corps}", file=sys.stderr)
        return 1
    except requests.RequestException as e:
        print(f"Erreur réseau : {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
