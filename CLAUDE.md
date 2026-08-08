# stealth-fetch — Claude Code guide

Bibliothèque Python + microservice HTTP de fetching anti-bot en cascade.
Remplace FlareSolverr (mourant) et unifie le fetching de 12+ repos.

## Architecture

5 niveaux en cascade, chacun essayé si le précédent est bloqué :

| Niveau | Moteur | Module | Dépendance |
|---|---|---|---|
| 1 | httpx direct | `engines/direct.py` | `httpx` (core) |
| 2 | curl_cffi TLS fingerprint | `engines/curlffi.py` | `curl_cffi` (optional) |
| 3 | nodriver stealth browser | `engines/stealth.py` | `nodriver` (optional) |
| 4 | Camoufox anti-detection Firefox | `engines/camoufox_engine.py` | `camoufox` + `playwright` (optional) |
| 5 | Scrapfly SaaS | `engines/saas.py` | `SCRAPFLY_API_KEY` env var |

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
- **Camoufox (niveau 4)** : Firefox anti-détection via Playwright. Après `pip install camoufox`,
  lancer `python -m camoufox fetch` pour télécharger le binaire Firefox (~660 Mo).
  Le premier appel avec `geoip=True` télécharge aussi GeoLite2 (~45 Mo) → prévoir un
  timeout plus long ou pré-lancer une requête de warmup.
- **Le niveau 5 (SaaS) est désactivé par défaut** : il faut poser `SCRAPFLY_API_KEY` en env.
  `max_level=3` (défaut cascade) ne l'atteint jamais — passer `max_level=5` explicitement.
- **Cookies et headers** : passés tels quels aux moteurs. L'authentification (obtention,
  renouvellement) n'est PAS du ressort de stealth-fetch — c'est au repo appelant de gérer.
- **nodriver exige `--no-sandbox` sur le VPS** : Chrome refuse de démarrer en user non-root
  sans ce flag. `--disable-dev-shm-usage` est aussi passé par précaution. Ces flags sont
  codés dans `engines/stealth.py` — ne pas les retirer.
- **nodriver ne supporte pas les proxies authentifiés** : Chrome `--proxy-server` n'accepte
  que `host:port` sans credentials. Si un proxy `user:pass@host:port` est configuré, nodriver
  lève RuntimeError et la cascade tombe sur Camoufox (qui gère l'auth proxy via Playwright).
- **DataDome/Akamai = faux positifs sur pages 200** : le SDK JS de ces protections est
  présent sur toutes les pages (monitoring), pas seulement les pages de challenge.
  `is_blocked()` ne flague pas un status 200 avec >5 Ko de HTML pour ces deux protections.
- **uvicorn masque les log.info()** : le root logger d'uvicorn est à WARNING. Utiliser
  `log.warning()` pour les messages opérationnels (blocage, erreur cascade).
- **Secrets VPS en credstore** : proxy (`stealth-fetch-proxy`) et clé Scrapfly
  (`stealth-fetch-scrapfly-key`) chargés via `LoadCredentialEncrypted` dans l'unit systemd.
- **Un seul navigateur nodriver à la fois** par requête : le niveau 3 lance un Chrome headless
  et le ferme après. Pas de pool de navigateurs (v0.1 — à réévaluer si contention).
