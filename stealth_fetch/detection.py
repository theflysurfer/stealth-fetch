"""Anti-bot protection detection — Cloudflare, DataDome, Akamai, generic."""

from __future__ import annotations

CLOUDFLARE_MARKERS = [
    "Attention Required! | Cloudflare",
    "Just a moment...",
    "cf-error-details",
    "__cf_chl",
    "challenges.cloudflare.com",
    "cf-mitigated: challenge",
]

DATADOME_MARKERS = [
    "datadome",
    "dd.datadome.co",
    "interstitial.datadome",
]

#: Marqueurs d'INFRASTRUCTURE Akamai : présents aussi bien sur une page servie
#: normalement (cookie de session, CDN) que sur un blocage. Leur présence seule
#: ne prouve rien — cf. l'exception de `is_blocked`.
AKAMAI_MARKERS = [
    "_abck",
    "akam/",
    "akamaihd.net",
]

#: Marqueurs d'INTERSTITIEL — la page de vérification servie À LA PLACE du
#: contenu. Contrairement aux précédents, ils prouvent le blocage à eux seuls.
#:
#: ⚠️ Akamai Bot Manager sert cet interstitiel en **HTTP 200**, avec un corps de
#: plusieurs kilo-octets. L'heuristique « 200 + page longue = vrai contenu » le
#: laissait donc passer, et la cascade s'arrêtait au premier moteur en croyant
#: avoir réussi (constaté sur intramuros.org, 2026-08-16).
#: Volontairement étroit : « access denied » a été écarté car il apparaît dans
#: des 403 ordinaires, déjà couverts par `generic-block`.
INTERSTITIAL_MARKERS = [
    "bm-verify",
    "please enable javascript and cookies",
]

CAPTCHA_MARKERS = [
    "g-recaptcha",
    "h-captcha",
    "hcaptcha.com",
    "recaptcha/api",
    "turnstile",
]


def detect_protection(status: int, html: str, headers: dict[str, str] | None = None) -> str | None:
    lower_html = html.lower() if html else ""
    header_str = " ".join(f"{k}={v}" for k, v in (headers or {}).items()).lower()

    for marker in CLOUDFLARE_MARKERS:
        if marker.lower() in lower_html or marker.lower() in header_str:
            return "cloudflare"

    for marker in DATADOME_MARKERS:
        if marker in lower_html or marker in header_str:
            return "datadome"

    for marker in INTERSTITIAL_MARKERS:
        if marker in lower_html:
            return "interstitial"

    for marker in AKAMAI_MARKERS:
        if marker in lower_html or marker in header_str:
            return "akamai"

    for marker in CAPTCHA_MARKERS:
        if marker in lower_html:
            return "captcha"

    if status in (403, 503) and not html.strip():
        return "empty-block"

    if status in (403, 503):
        return "generic-block"

    return None


def is_blocked(status: int, html: str, headers: dict[str, str] | None = None) -> bool:
    protection = detect_protection(status, html, headers)
    if protection is None:
        return False

    # Une page longue servie en 200 est probablement du vrai contenu : les
    # marqueurs d'INFRASTRUCTURE (cookie `_abck`, CDN) s'y trouvent normalement.
    # ⚠️ L'exception ne vaut PAS pour un interstitiel, qui est précisément servi
    # en 200 avec un corps volumineux — l'y inclure revenait à conclure « pas de
    # blocage » sur la page de vérification elle-même.
    if status == 200 and len(html) > 5000:
        if protection in ("datadome", "akamai"):
            return False

    return True
