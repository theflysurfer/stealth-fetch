# Consumers — repos qui doivent migrer vers stealth-fetch

> Note de synthèse établie le 2026-08-07. Cartographie exhaustive de tous les repos utilisant
> du fetching anti-bot, avec plan de migration vers `stealth-fetch`.

## Pourquoi ce repo existe

FlareSolverr est en fin de vie (CAPTCHA cassé depuis janvier 2026, dernier release novembre 2025).
12+ repos réimplémentent chacun leur propre cascade de fetching anti-bot, avec 3 stratégies
indépendantes (cf-bypass-client en JS, curl_cffi en Python, patchright en Python). Aucun
service centralisé n'existait.

`stealth-fetch` unifie tout en une **bibliothèque Python + microservice HTTP** avec 5 niveaux
en cascade : direct → curl_cffi → nodriver → Camoufox → SaaS (optionnel).

## Distinction : fetching PUBLIC vs AUTHENTIFIÉ

### Fetching public (domaine de stealth-fetch)

Récupérer le HTML d'un site **sans identité utilisateur**. Le problème est purement technique :
contourner Cloudflare, DataDome, Akamai, CAPTCHAs. C'est le périmètre de `stealth-fetch`.

### Fetching authentifié (hors périmètre direct)

Accéder à un service **avec les cookies/tokens de Julien** (LinkedIn, Auchan, Google Recorder,
Facebook, exports d'IA). L'authentification (obtention et renouvellement des cookies) reste dans
chaque repo spécialisé et/ou Cookie Health Manager.

**Mais** : `stealth-fetch` peut servir de **couche de transport** pour ces flux authentifiés.
L'API accepte des `cookies` et `headers` en paramètre — le repo appelant gère l'auth, stealth-fetch
gère l'anti-bot. Exemple : LinkedIn bloque les IPs datacenter même avec des cookies valides →
passer par le niveau 2 (curl_cffi TLS fingerprint) résout le problème sans toucher à l'auth.

## Inventaire complet des consommateurs

### Priorité 1 — Migration immédiate (utilisent FlareSolverr aujourd'hui)

| Repo | Fichier(s) | Méthode actuelle | Mode | Migration |
|---|---|---|---|---|
| **Waaker** | `src/pages/api/parse-url.ts` | cf-bypass-client (fetch + FlareSolverr) | PUBLIC | `POST /fetch-html` (HTTP, car TypeScript) |
| **activity-scraper** | `server.py`, `fetcher.py` | httpx + FlareSolverr | PUBLIC | `from stealth_fetch import fetch_html` (Python direct) |
| **Allocine API** | `allocine_api/resolvers.py` | curl_cffi → FlareSolverr → patchright (3 moteurs inline) | PUBLIC | `from stealth_fetch import fetch_html` — supprime 80 lignes |
| **cf-bypass-client** | `src/index.js` (117 lignes) | fetch + FlareSolverr | PUBLIC | **Décommissionné** — remplacé par stealth-fetch |

### Priorité 2 — Gains immédiats (utilisent curl_cffi, pourraient bénéficier de la cascade)

| Repo | Fichier(s) | Méthode actuelle | Mode | Migration |
|---|---|---|---|---|
| **Leclerc Drive API** | `mcp_server.py` | curl_cffi (DataDome) | AUTH (cookies) | Transport : `fetch_html(url, cookies=…)` — curl_cffi comme niveau 2, escalade auto vers nodriver si DataDome durcit |
| **Google Recorder API** | `recorder.py`, `auth.py` | curl_cffi + SAPISIDHASH | AUTH (cookies + headers) | Transport : `fetch_html(url, cookies=…, headers={"Authorization": …})` |
| **AI Chat Export** | `curlffi_browser.py` | curl_cffi + patchright legacy | AUTH (session tokens) | Transport pour la phase fetch ; l'auth reste dans le repo |
| **Cookie Health Manager** | `manager.py` | curl_cffi (health checks) | AUTH (cookies) | Transport : les health checks passent par la cascade |
| **Festival Avignon** | `server/`, `scraper/` | curl_cffi | PUBLIC | `from stealth_fetch import fetch_html` |
| **Chats Libres** | `scraper.py` | curl_cffi (Facebook GraphQL) | AUTH (cookies FB) | Transport : `fetch_html(url, cookies=fb_cookies)` — nécessite IP résidentielle, SaaS exclu |

### Priorité 3 — Nouveaux consommateurs (n'utilisent pas encore de fetching structuré)

| Repo | Besoin | Mode | Intégration |
|---|---|---|---|
| **Deep Research** (sessions Claude Code) | Fetch de pages web pour recherche approfondie | PUBLIC | `POST /fetch-html` depuis le VPS ou en lib Python |
| **Cooking Manager** | Scraping de recettes (sites tiers, pas Auchan) | PUBLIC | `from stealth_fetch import fetch_html` pour les URLs de recettes |
| **recipe-parser** | Parse HTML déjà reçu (pas de fetch propre), mais pourrait fetcher directement | PUBLIC | Optionnel : supprimer le routage via Waaker si recipe-parser fetch lui-même |
| **Web Scraper** | Toolkit générique de scraping | PUBLIC | `from stealth_fetch import fetch_html` — remplace le patchright_client maison |
| **YouTube Manager** | Potentiellement fetch de pages pour metadata | PUBLIC | À évaluer |
| **Hesiodus** | Scraping de contenus éducatifs | PUBLIC | `from stealth_fetch import fetch_html` |
| **MCP servers futurs** | Tout MCP qui a besoin de lire une page web | PUBLIC/AUTH | Dépendance standard |

### Priorité 4 — Cas spéciaux (l'auth domine, le transport est secondaire)

| Repo | Méthode actuelle | Mode | Note |
|---|---|---|---|
| **LinkedIn AoT** | curl_cffi | AUTH (cookies LinkedIn) | L'anti-bot est secondaire ici — LinkedIn bloque sur l'absence de cookies, pas sur le fingerprinting. Cookie Health Manager gère le cycle. stealth-fetch utile seulement si LinkedIn durcit le TLS fingerprinting. |
| **Auchan Drive (Cooking Manager)** | curl_cffi | AUTH (session Auchan) | API REST interne, pas de page HTML à fetcher — stealth-fetch hors périmètre |
| **MCP LinkedIn, Gmail, etc.** | Chaque MCP a son propre client HTTP | AUTH | stealth-fetch non pertinent — ce sont des APIs, pas des pages web |

## Architecture de déploiement

```
┌─────────────────────────────────────────────────────────────┐
│ VPS srv759970                                               │
│                                                             │
│  stealth-fetch (port 8410)                                  │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ POST /fetch-html                                    │    │
│  │                                                     │    │
│  │  Niveau 1: httpx direct           (~0.5s, gratuit)  │    │
│  │  Niveau 2: curl_cffi TLS fingerp. (~1-2s, gratuit)  │    │
│  │  Niveau 3: nodriver browser       (~3-8s, gratuit)  │    │
│  │  Niveau 4: Camoufox anti-detect   (~5-12s, gratuit) │    │
│  │  Niveau 5: Scrapfly SaaS          (~2-5s, payant)   │    │
│  └────────┬────────────────────────────────────────────┘    │
│           │                                                 │
│  ┌────────┼────────────────────────────────────────────┐    │
│  │ Consommateurs Python (import direct, pas de réseau) │    │
│  │  · activity-scraper                                 │    │
│  │  · allocine-api                                     │    │
│  │  · recipe-parser                                    │    │
│  │  · cookie-health-manager                            │    │
│  │  · ai-chat-export                                   │    │
│  └─────────────────────────────────────────────────────┘    │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Consommateurs HTTP (POST /fetch-html)               │    │
│  │  · Waaker (TypeScript, port 3020)                   │    │
│  │  · Deep Research (Claude Code sessions)             │    │
│  └─────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ Poste local (dev)                                           │
│                                                             │
│  stealth-fetch (même code, port 8410 ou import direct)      │
│  HydraSpecter (port 8765) = stealth browser alternatif      │
│                                                             │
│  · Waaker dev → POST http://127.0.0.1:8410/fetch-html      │
│  · Web Scraper → from stealth_fetch import fetch_html       │
│  · Cooking Manager → idem                                   │
└─────────────────────────────────────────────────────────────┘
```

## Résultats du benchmark (2026-08-07)

### Tests réels HydraSpecter (Patchright) sur les domaines bloqués par FlareSolverr

| Domaine | Protection | FlareSolverr | HydraSpecter | nodriver (benchmark tiers) |
|---|---|---|---|---|
| seriouseats.com | Cloudflare | ❌ timeout | ✅ passe | ✅ (0/31 bloqué) |
| bonappetit.com | Cloudflare | ❌ timeout | ✅ passe | ✅ |
| tripadvisor.fr | DataDome | ❌ timeout | ✅ passe (34K chars) | ✅ (avec résidentiel) |
| getyourguide.com | Cloudflare | ❌ timeout | ✅ passe | ✅ |
| musee-orsay.fr | Faible | ❌ timeout | ✅ passe | ✅ |
| chateauversailles.fr | Cookie wall | ❌ timeout | ✅ passe | ✅ |
| disneylandparis.com | Akamai | ❌ timeout | ✅ passe | ✅ |
| decathlon.fr | Akamai (SPA) | ❌ timeout | ⚠️ partiel (SPA) | ⚠️ |

### SaaS benchmarké (juillet 2026)

| Service | Taux de succès | Prix | Verdict |
|---|---|---|---|
| Scrapfly | 98% (#1/8 benchmark) | 30 €/mois | Meilleur rapport, niveau 5 |
| Bright Data | 98.4% | Pay-as-you-go | Complexe à configurer |
| ZenRows | 58% | 69 €/mois | Marketing > réalité |
| ScraperAPI | 49% | 49 €/mois | À éviter |

## Plan de migration

### Phase 1 : repo fonctionnel
- [x] Créer le repo `stealth-fetch`
- [x] Implémenter la cascade 5 niveaux (direct → curl_cffi → nodriver → Camoufox → SaaS)
- [x] Serveur HTTP FastAPI
- [x] Déployer sur VPS (systemd unit, port 8410)
- [x] Proxy résidentiel Webshare + clé Scrapfly en credstore
- [ ] Tests unitaires (détection + cascade mock)

### Phase 2 : premiers consommateurs
- [ ] Waaker : remplacer cf-bypass-client par `POST /fetch-html`
- [x] activity-scraper : remplacé le fetcher maison par `POST stealth-fetch/fetch-html` (d764e52)
- [x] Allocine API : remplacé les 3 moteurs inline par `fetch_html(min_level=3)` (bb0e968)

### Phase 3 : extension
- [ ] Leclerc Drive, Google Recorder, AI Chat Export : transport authentifié
- [ ] Deep Research, Cooking Manager, Web Scraper : nouveaux consommateurs
- [ ] Cookie Health Manager : health checks via la cascade

### Phase 4 : décommissionnement
- [ ] Retirer FlareSolverr Docker du VPS
- [ ] Archiver cf-bypass-client (npm)
- [ ] Supprimer les fetchers maison dans chaque repo
