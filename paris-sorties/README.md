# paris-sorties

Petit script Python en ligne de commande pour trouver **les événements autour de vous** et **les bars à Paris**, à partir d'API publiques, gratuites et sans clé.

| Besoin | Source | Clé ? |
|---|---|---|
| Événements | [« Que faire à Paris ? »](https://opendata.paris.fr/explore/dataset/que-faire-a-paris-/) (Open Data Paris, API Opendatasoft v2.1) | Non |
| Bars, pubs, biergartens | [OpenStreetMap](https://www.openstreetmap.org) via l'[API Overpass](https://wiki.openstreetmap.org/wiki/Overpass_API) | Non |
| Adresse → coordonnées | [Nominatim](https://nominatim.org) (OpenStreetMap) | Non |

## Installation

Python 3.9 ou plus récent.

```bash
git clone https://github.com/<vous>/paris-sorties.git
cd paris-sorties
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## Utilisation

### Événements

```bash
# Événements des 7 prochains jours à moins de 2 km de Bastille
python paris_sorties.py events --adresse "Place de la Bastille, Paris"

# Autour d'une position GPS, rayon 1 km, gratuits uniquement, sur 3 jours
python paris_sorties.py events --lat 48.8566 --lon 2.3522 --rayon 1000 --gratuit --jours 3

# Recherche par mot-clé dans tout Paris
python paris_sorties.py events --recherche jazz --limite 50
```

Options : `--adresse`, `--lat`/`--lon`, `--rayon` (m, défaut 2000), `--jours` (défaut 7), `--gratuit`, `--recherche`, `--limite` (défaut 20), `--json`.

Sans position, la recherche porte sur tout Paris.

### Bars

```bash
# Bars les plus proches du canal Saint-Martin (500 m), triés par distance
python paris_sorties.py bars --adresse "Canal Saint-Martin, Paris" --rayon 500

# Tous les bars de Paris, export JSON
python paris_sorties.py bars --limite 100000 --json > bars.json

# Seulement les pubs
python paris_sorties.py bars --adresse "Châtelet" --types pub
```

Options : `--adresse`, `--lat`/`--lon`, `--rayon` (m, défaut 800), `--types` (défaut `bar,pub,biergarten`), `--limite` (défaut 20), `--json`.

Sans position, le script interroge toute la commune de Paris (plusieurs milliers de lieux, la requête peut prendre quelques secondes).

### Utiliser le script comme module

```python
from paris_sorties import chercher_evenements, chercher_bars

events = chercher_evenements((48.8566, 2.3522), rayon_m=1500, jours=7,
                             gratuit=False, recherche=None, limite=30)
bars = chercher_bars((48.8566, 2.3522), rayon_m=500, types=["bar", "pub"])
```

## Configuration (variables d'environnement)

Aucune clé n'est nécessaire. Ces variables sont facultatives :

| Variable | Rôle | Défaut |
|---|---|---|
| `PARIS_SORTIES_USER_AGENT` | User-Agent envoyé aux API. **Mettez-y l'URL de votre dépôt ou un contact** : la [politique de Nominatim](https://operations.osmfoundation.org/policies/nominatim/) l'exige. | `paris-sorties/1.0 (+https://github.com/)` |
| `OVERPASS_URL` | Autre instance Overpass si la principale est saturée (ex. `https://overpass.kumi.systems/api/interpreter`) | `https://overpass-api.de/api/interpreter` |
| `NOMINATIM_URL` | Autre instance Nominatim | instance officielle |
| `QFAP_URL` | URL de l'API « Que faire à Paris ? » | opendata.paris.fr |
| `PARIS_SORTIES_TIMEOUT` | Délai max des requêtes, en secondes | `60` |

```bash
export PARIS_SORTIES_USER_AGENT="paris-sorties/1.0 (https://github.com/<vous>/paris-sorties)"
```

## Bon usage des API

- Nominatim : 1 requête par seconde maximum, pas d'usage massif.
- Overpass : service gratuit et partagé ; évitez les requêtes sur tout Paris en boucle.
- Données : © contributeurs OpenStreetMap (licence ODbL) et Ville de Paris (Licence Ouverte / ODbL selon le jeu). Citez les sources si vous republiez les données.

## Licence

MIT (à adapter).
