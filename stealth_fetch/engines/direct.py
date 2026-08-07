"""Level 1 — plain httpx fetch with rotating User-Agent."""

from __future__ import annotations

import random

import httpx

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
]

DEFAULT_HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7",
    "Cache-Control": "no-cache",
    "Referer": "https://www.google.com/",
}


async def fetch(
    url: str,
    *,
    timeout: float = 10,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    proxy: str | None = None,
) -> tuple[int, str, dict[str, str]]:
    merged = {
        **DEFAULT_HEADERS,
        "User-Agent": random.choice(USER_AGENTS),
        **(headers or {}),
    }
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=timeout,
        http2=True,
        proxy=proxy,
    ) as client:
        resp = await client.get(url, headers=merged, cookies=cookies)
        resp_headers = {k: v for k, v in resp.headers.items()}
        return resp.status_code, resp.text, resp_headers
