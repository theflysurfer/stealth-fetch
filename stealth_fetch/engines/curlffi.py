"""Level 2 — curl_cffi with Chrome TLS fingerprint impersonation."""

from __future__ import annotations

_AVAILABLE = True
try:
    from curl_cffi.requests import AsyncSession  # type: ignore[import-untyped]
except ImportError:
    _AVAILABLE = False
    AsyncSession = None  # type: ignore[assignment]


def is_available() -> bool:
    return _AVAILABLE


async def fetch(
    url: str,
    *,
    timeout: float = 15,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    impersonate: str = "chrome131",
    proxy: str | None = None,
) -> tuple[int, str, dict[str, str]]:
    if AsyncSession is None:
        raise RuntimeError("curl_cffi not installed — pip install stealth-fetch[curlffi]")

    async with AsyncSession(impersonate=impersonate) as session:  # type: ignore[arg-type]
        resp = await session.get(
            url,
            headers=headers or {},
            cookies=cookies or {},
            timeout=timeout,
            allow_redirects=True,
            proxy=proxy,
        )
        resp_headers = {k: v for k, v in resp.headers.items()}
        return resp.status_code, resp.text, resp_headers
