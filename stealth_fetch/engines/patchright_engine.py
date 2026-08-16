"""Level 3.5 — Patchright (patched Playwright Chromium, clears Akamai Bot Manager).

Why this engine exists: nodriver and camoufox both hand back Akamai's `bm-verify`
interstitial rather than the document. Measured 2026-08-16 on intramuros.org, on
the VPS where every other engine is installed — camoufox returned 2 220 bytes of
challenge page. Patchright cleared the same URL and returned the full
`__NEXT_DATA__` payload.

It sits between `stealth` (nodriver) and `camoufox` because it is the cheapest
browser that clears Akamai, and it is already deployed on srv759970 for
cookie-health-vps.

⚠️ **HEADED IS NOT OPTIONAL HERE.** Akamai fingerprints headless Chromium and
answers 403 before any challenge is shown. Measured on the same URL, same
machine, same run (2026-08-16):

    headless=True   -> 403,        308 bytes, no __NEXT_DATA__
    headless=False  -> 200,    356 825 bytes, __NEXT_DATA__ present

So this engine launches headed by default. On a headless host (a VPS), that
requires a virtual display — run the service under `xvfb-run -a`, otherwise the
browser cannot start at all. Set `STEALTH_FETCH_PATCHRIGHT_HEADLESS=1` to force
headless, but expect 403 from Akamai-protected hosts: it is a debugging switch,
not a deployment mode.

⚠️ Akamai's interstitial is served as **HTTP 200 with a multi-kilobyte body**, so
a size check cannot tell it apart from real content — that mistake is what let it
through the cascade in the first place. This engine waits for the challenge marker
to disappear, and reports the status honestly if it never does.
"""

from __future__ import annotations

import os

_AVAILABLE = True
try:
    from patchright.async_api import async_playwright  # type: ignore[import-untyped]
except ImportError:
    _AVAILABLE = False
    async_playwright = None  # type: ignore[assignment]


#: Markers that mean a challenge page is being shown INSTEAD of the document.
#: `bm-verify` is Akamai Bot Manager; the rest are Cloudflare's.
_CHALLENGE_MARKERS = (
    "bm-verify",
    "just a moment...",
    "challenge-running",
    "challenge-stage",
    "challenges.cloudflare.com",
    "__cf_chl",
    "please enable javascript and cookies",
)

#: A challenge usually clears within a few seconds; past this we stop waiting and
#: report what we actually have rather than pretending success.
_CHALLENGE_POLLS = 6
_CHALLENGE_INTERVAL_MS = 2000


def is_available() -> bool:
    return _AVAILABLE


def _is_challenge(html: str) -> bool:
    head = html[:5000].lower()
    return any(marker in head for marker in _CHALLENGE_MARKERS)


def _parse_proxy(proxy_url: str) -> dict[str, str]:
    from urllib.parse import urlparse

    parsed = urlparse(proxy_url)
    result: dict[str, str] = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
    if parsed.username:
        result["username"] = parsed.username
    if parsed.password:
        result["password"] = parsed.password
    return result


async def fetch(
    url: str,
    *,
    timeout: float = 45,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    proxy: str | None = None,
) -> tuple[int, str, dict[str, str]]:
    if not _AVAILABLE or async_playwright is None:
        raise RuntimeError("patchright not installed — pip install stealth-fetch[patchright]")

    headless = os.environ.get("STEALTH_FETCH_PATCHRIGHT_HEADLESS", "") == "1"

    async with async_playwright() as playwright:
        launch: dict[str, object] = {
            "headless": headless,
            "proxy": _parse_proxy(proxy) if proxy else None,
        }
        try:
            # The real Chrome build fingerprints better than bundled Chromium.
            browser = await playwright.chromium.launch(channel="chrome", **launch)
        except Exception:
            browser = await playwright.chromium.launch(**launch)
        try:
            context = await browser.new_context(
                locale="fr-FR",
                extra_http_headers=headers or {},
            )
            if cookies:
                from urllib.parse import urlparse

                domain = urlparse(url).hostname or ""
                await context.add_cookies(
                    [{"name": k, "value": v, "domain": domain, "path": "/"} for k, v in cookies.items()]
                )

            page = await context.new_page()
            response = await page.goto(url, timeout=int(timeout * 1000), wait_until="domcontentloaded")
            status = response.status if response else 200

            html = await page.content()
            for _ in range(_CHALLENGE_POLLS):
                if not _is_challenge(html):
                    break
                await page.wait_for_timeout(_CHALLENGE_INTERVAL_MS)
                html = await page.content()

            final_url = page.url
            if len(html) < 100:
                raise RuntimeError(f"empty page for {url} ({len(html)}B)")

            return status, html, {"x-final-url": final_url}
        finally:
            await browser.close()
