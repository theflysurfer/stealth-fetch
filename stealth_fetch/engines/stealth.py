"""Level 3 — nodriver (CDP-direct stealth browser, no Playwright dependency)."""

from __future__ import annotations

_AVAILABLE = True
try:
    import nodriver  # type: ignore[import-untyped]
except ImportError:
    _AVAILABLE = False
    nodriver = None  # type: ignore[assignment]


def is_available() -> bool:
    return _AVAILABLE


def _is_cloudflare_challenge(html: str) -> bool:
    head = html[:5000].lower()
    return any(m in head for m in (
        "just a moment...",
        "challenge-running",
        "challenge-stage",
        "challenges.cloudflare.com",
        "__cf_chl",
    ))


def _strip_proxy_auth(proxy_url: str) -> str:
    """Chrome's --proxy-server flag does not support user:pass@ authentication.

    For HTTP proxies with credentials (like Webshare rotating residential),
    we raise so the cascade falls through to Camoufox which handles auth natively.
    SOCKS5 proxies without auth (like microsocks) pass through unchanged.
    """
    from urllib.parse import urlparse
    p = urlparse(proxy_url)
    if p.username or p.password:
        raise RuntimeError(
            f"nodriver/Chrome cannot authenticate to proxy {p.hostname}:{p.port} "
            f"(--proxy-server does not support credentials) — falling through to next engine"
        )
    return proxy_url


def _is_chrome_error(html: str) -> bool:
    """Detect Chrome's built-in error pages (connection failures, DNS errors).

    These are rendered locally by Chrome and returned as 200 by nodriver,
    masking the actual failure. Typical size: ~185KB. Chrome uses multiple
    error messages ("temporarily down", "DNS address could not be found",
    "refused to connect") but all share the Chromium CSS copyright.
    """
    return "The Chromium Authors" in html[:2000]


async def fetch(
    url: str,
    *,
    timeout: float = 30,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    proxy: str | None = None,
) -> tuple[int, str, dict[str, str]]:
    if nodriver is None:
        raise RuntimeError("nodriver not installed — pip install stealth-fetch[stealth]")

    browser_args = ["--no-sandbox", "--disable-dev-shm-usage"]
    if proxy:
        proxy_for_chrome = _strip_proxy_auth(proxy)
        browser_args.append(f"--proxy-server={proxy_for_chrome}")

    browser = await nodriver.start(
        headless=True,
        lang="fr-FR",
        browser_args=browser_args,
    )
    try:
        page = await browser.get(url, new_tab=True)
        await page.sleep(2)

        html = await page.get_content()

        if _is_cloudflare_challenge(html):
            # Try clicking the Turnstile checkbox if present
            for sel in ["#challenge-stage iframe", "iframe[src*='turnstile']"]:
                try:
                    frame = await page.find(sel, timeout=2)
                    if frame:
                        await frame.click()
                        break
                except Exception:
                    continue

            # Wait for challenge to auto-resolve (up to 10s, polling every 2s)
            for _ in range(5):
                await page.sleep(2)
                html = await page.get_content()
                if not _is_cloudflare_challenge(html):
                    break

        # Dismiss common cookie banners
        for selector in [
            "#didomi-notice-agree-button",
            "[id*='accept']",
            "button[class*='consent']",
            "[data-testid='cookie-policy-manage-dialog-btn-accept-all']",
        ]:
            try:
                btn = await page.find(selector, timeout=1)
                if btn:
                    await btn.click()
                    await page.sleep(0.5)
                    break
            except Exception:
                continue

        html = await page.get_content()
        final_url = page.url or url

        if _is_chrome_error(html):
            raise RuntimeError(f"Chrome error page for {url} (connection failed or blocked)")

        if len(html) < 100:
            raise RuntimeError(f"empty page for {url} ({len(html)}B — redirect or render failure)")

        return 200, html, {"x-final-url": final_url}
    finally:
        browser.stop()
