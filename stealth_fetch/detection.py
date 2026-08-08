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

AKAMAI_MARKERS = [
    "_abck",
    "akam/",
    "akamaihd.net",
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

    if status == 200 and len(html) > 5000:
        if protection in ("datadome", "akamai"):
            return False

    return True
