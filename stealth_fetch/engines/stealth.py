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


def _is_chrome_error(html: str) -> bool:
    """Detect Chrome's built-in error pages (connection failures, DNS errors).

    These are rendered locally by Chrome and returned as 200 by nodriver,
    masking the actual failure. Typical size: ~185KB, contains Chromium
    copyright and "might be temporarily down" text.
    """
    return "The Chromium Authors" in html[:2000] and "temporarily down" in html


async def fetch(
    url: str,
    *,
    timeout: float = 30,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> tuple[int, str, dict[str, str]]:
    if not _AVAILABLE:
        raise RuntimeError("nodriver not installed — pip install stealth-fetch[stealth]")

    browser = await nodriver.start(
        headless=True,
        lang="fr-FR",
        browser_args=["--no-sandbox", "--disable-dev-shm-usage"],
    )
    try:
        page = await browser.get(url, new_tab=True)

        # Wait for page to settle (JS rendering, challenges)
        await page.sleep(2)

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
