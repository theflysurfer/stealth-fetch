# stealth-fetch — Claude Code guide

Bibliothèque Python + microservice HTTP de fetching anti-bot en cascade.
Remplace FlareSolverr (mourant) et unifie le fetching de 12+ repos.

## Architecture

4 niveaux en cascade, chacun essayé si le précédent est bloqué :

| Niveau | Moteur | Module | Dépendance |
|---|---|---|---|
| 1 | httpx direct | `engines/direct.py` | `httpx` (core) |
| 2 | curl_cffi TLS fingerprint | `engines/curlffi.py` | `curl_cffi` (optional) |
| 3 | nodriver stealth browser | `engines/stealth.py` | `nodriver` (optional) |
| 4 | Scrapfly SaaS | `engines/saas.py` | `SCRAPFLY_API_KEY` env var |

`detection.py` identifie le type de protection (Cloudflare, DataDome, Akamai, CAPTCHA).
`cascade.py` orchestre les niveaux et produit un `FetchResult`.
`server.py` expose `POST /fetch-html` et `GET /health` via FastAPI.

## Usage

```python
# En bibliothèque
from stealth_fetch import fetch_html
result = await fetch_html("https://example.com", max_level=3)
# result.html, result.status, result.engine, result.elapsed_ms

# En service HTTP
# POST http://127.0.0.1:8410/fetch-html
# {"url": "...", "max_level": 3, "cookies": {"session": "abc"}}
```

## Commands

- `pip install -e ".[all]"` — install avec tous les moteurs
- `pip install -e ".[server]"` — install avec FastAPI seulement
- `stealth-fetch` ou `python -m stealth_fetch.server` — lance le serveur (port 8410)
- `python -m ruff check stealth_fetch/` — lint
- `python -m pyright` — typecheck
- `python -m pytest tests/` — tests

## Déploiement VPS (srv759970)

- Port : **8410** (127.0.0.1 uniquement)
- Unit systemd : `stealth-fetch.service`
- Consommateurs : Waaker (HTTP), activity-scraper (import), allocine-api (import)
- FlareSolverr (port 8191) sera décommissionné après migration complète

## Consumers

Voir `docs/CONSUMERS.md` pour l'inventaire complet des repos qui migrent vers stealth-fetch,
avec la distinction fetching public vs authentifié.

## Gotchas

- **nodriver a besoin de Chrome/Chromium installé** sur la machine. Sur le VPS, vérifier
  `which google-chrome` ou `which chromium-browser`.
- **curl_cffi = optional** : si absent, le niveau 2 est sauté (pas d'erreur, juste escalade
  directe vers le niveau 3).
- **Le niveau 4 (SaaS) est désactivé par défaut** : il faut poser `SCRAPFLY_API_KEY` en env.
  `max_level=3` (défaut) ne l'atteint jamais.
- **Cookies et headers** : passés tels quels aux moteurs. L'authentification (obtention,
  renouvellement) n'est PAS du ressort de stealth-fetch — c'est au repo appelant de gérer.
- **Un seul navigateur nodriver à la fois** par requête : le niveau 3 lance un Chrome headless
  et le ferme après. Pas de pool de navigateurs (v0.1 — à réévaluer si contention).
