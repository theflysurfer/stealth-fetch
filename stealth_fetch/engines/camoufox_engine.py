"""Level 4 — Camoufox (anti-detection Firefox via Playwright)."""

from __future__ import annotations

_AVAILABLE = True
try:
    from camoufox.async_api import AsyncCamoufox  # type: ignore[import-untyped]
except ImportError:
    _AVAILABLE = False
    AsyncCamoufox = None  # type: ignore[assignment,misc]


def is_available() -> bool:
    return _AVAILABLE


async def fetch(
    url: str,
    *,
    timeout: float = 30,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    proxy: str | None = None,
) -> tuple[int, str, dict[str, str]]:
    if not _AVAILABLE or AsyncCamoufox is None:
        raise RuntimeError("camoufox not installed — pip install stealth-fetch[camoufox]")

    proxy_cfg = None
    if proxy:
        proxy_cfg = _parse_proxy(proxy)

    async with AsyncCamoufox(
        headless=True,
        proxy=proxy_cfg,
        humanize=True,
        geoip=True,
    ) as browser:
        page = await browser.new_page()

        if headers:
            await page.set_extra_http_headers(headers)

        if cookies:
            from urllib.parse import urlparse
            domain = urlparse(url).hostname or ""
            await page.context.add_cookies([
                {"name": k, "value": v, "domain": domain, "path": "/"}
                for k, v in cookies.items()
            ])

        resp = await page.goto(url, timeout=int(timeout * 1000), wait_until="domcontentloaded")
        status = resp.status if resp else 200

        # Wait for JS rendering + potential challenge resolution
        await page.wait_for_timeout(3000)

        # Check for Cloudflare challenge and wait longer if needed
        html = await page.content()
        if _is_challenge(html):
            for _ in range(5):
                await page.wait_for_timeout(2000)
                html = await page.content()
                if not _is_challenge(html):
                    break

        html = await page.content()
        final_url = page.url

        if len(html) < 100:
            raise RuntimeError(f"empty page for {url} ({len(html)}B)")

        return status, html, {"x-final-url": final_url}


def _is_challenge(html: str) -> bool:
    head = html[:5000].lower()
    return any(m in head for m in (
        "just a moment...",
        "challenge-running",
        "challenges.cloudflare.com",
        "attention required",
        "__cf_chl",
    ))


def _parse_proxy(proxy_url: str) -> dict[str, str]:
    from urllib.parse import urlparse
    p = urlparse(proxy_url)
    result: dict[str, str] = {"server": f"{p.scheme}://{p.hostname}:{p.port}"}
    if p.username:
        result["username"] = p.username
    if p.password:
        result["password"] = p.password
    return result
