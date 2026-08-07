"""Cascading fetch orchestrator — tries engines in order until one succeeds."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field

from .detection import is_blocked

log = logging.getLogger("stealth_fetch")

ENGINE_NAMES = ["direct", "curlffi", "stealth", "saas"]


@dataclass
class FetchResult:
    html: str
    status: int
    engine: str
    final_url: str | None = None
    elapsed_ms: int = 0
    protection: str | None = None
    attempts: list[dict[str, object]] = field(default_factory=list)


async def fetch_html(
    url: str,
    *,
    max_level: int = 3,
    timeout: float | None = None,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
) -> FetchResult:
    """Fetch HTML through the cascade. Levels: 1=direct, 2=curl_cffi, 3=nodriver, 4=saas.

    Args:
        url: target URL
        max_level: highest engine to try (1-4). Default 3 (no SaaS).
        timeout: per-engine timeout in seconds (engine defaults if None)
        headers: extra HTTP headers (passed to all engines)
        cookies: cookies dict (passed to engines that support it)

    Returns:
        FetchResult with HTML content and metadata

    Raises:
        RuntimeError: if all engines fail
    """
    from .engines import direct, curlffi, stealth, saas

    engines: list[tuple[str, object]] = [
        ("direct", direct),
    ]
    if max_level >= 2 and curlffi.is_available():
        engines.append(("curlffi", curlffi))
    if max_level >= 3 and stealth.is_available():
        engines.append(("stealth", stealth))
    if max_level >= 4 and saas.is_available():
        engines.append(("saas", saas))

    attempts: list[dict[str, object]] = []
    last_error: str = ""

    for name, engine in engines:
        t0 = time.monotonic()
        try:
            kwargs: dict[str, object] = {}
            if timeout is not None:
                kwargs["timeout"] = timeout
            if headers:
                kwargs["headers"] = headers
            if cookies:
                kwargs["cookies"] = cookies

            status, html, resp_headers = await engine.fetch(url, **kwargs)  # type: ignore[union-attr]
            elapsed = int((time.monotonic() - t0) * 1000)

            if is_blocked(status, html, resp_headers):
                from .detection import detect_protection
                protection = detect_protection(status, html, resp_headers)
                attempts.append({
                    "engine": name, "status": status, "blocked": True,
                    "protection": protection, "elapsed_ms": elapsed,
                })
                log.info("engine=%s blocked=%s elapsed=%dms url=%s", name, protection, elapsed, url)
                continue

            log.info("engine=%s status=%d elapsed=%dms url=%s", name, status, elapsed, url)
            return FetchResult(
                html=html,
                status=status,
                engine=name,
                final_url=resp_headers.get("x-final-url"),
                elapsed_ms=elapsed,
                attempts=attempts,
            )

        except Exception as exc:
            elapsed = int((time.monotonic() - t0) * 1000)
            last_error = f"{name}: {exc}"
            attempts.append({
                "engine": name, "error": str(exc), "elapsed_ms": elapsed,
            })
            log.warning("engine=%s error=%s elapsed=%dms url=%s", name, exc, elapsed, url)
            continue

    raise RuntimeError(
        f"all engines failed for {url} (tried: {', '.join(a['engine'] for a in attempts)}). "  # type: ignore[str-bytes-safe]
        f"Last: {last_error}"
    )
