"""Level 5 — SaaS anti-bot API (Scrapfly). Optional, requires SCRAPFLY_API_KEY."""

from __future__ import annotations

import os

import httpx

SCRAPFLY_BASE = "https://api.scrapfly.io/scrape"


def is_available() -> bool:
    return bool(os.environ.get("SCRAPFLY_API_KEY"))


async def fetch(
    url: str,
    *,
    timeout: float = 30,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    proxy: str | None = None,
) -> tuple[int, str, dict[str, str]]:
    api_key = os.environ.get("SCRAPFLY_API_KEY")
    if not api_key:
        raise RuntimeError("SCRAPFLY_API_KEY not set — level 4 (SaaS) unavailable")

    params = {
        "key": api_key,
        "url": url,
        "asp": "true",  # anti-scraping protection bypass
        "render_js": "true",
        "country": "fr",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(SCRAPFLY_BASE, params=params)
        data = resp.json()

    result = data.get("result", {})
    html = result.get("content", "")
    status = result.get("status_code", resp.status_code)
    resp_headers = {k: v for k, v in result.get("response_headers", {}).items()}

    return status, html, resp_headers
