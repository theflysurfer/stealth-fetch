"""Cascading fetch orchestrator — tries engines in order until one succeeds."""

from __future__ import annotations

import logging
import os
import time
from dataclasses import dataclass, field

from .detection import is_blocked

log = logging.getLogger("stealth_fetch")

ENGINE_NAMES = ["direct", "curlffi", "stealth", "camoufox", "saas"]
DEFAULT_PROXY = os.environ.get("STEALTH_FETCH_PROXY")

_PROXY_SSL_MARKERS = [
    "WRONG_VERSION_NUMBER", "PROXY_BAD_GATEWAY", "SSL_ERROR_UNKNOWN",
    "SSL_ERROR_SYSCALL", "SEC_ERROR_UNKNOWN_ISSUER", "unable to get local issuer",
    "SSL_ERROR_UNRECOGNIZED_NAME_ALERT", "PROXY_CONNECTION_REFUSED",
    "CONNECT tunnel failed",
]


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
    min_level: int = 1,
    max_level: int = 3,
    timeout: float | None = None,
    headers: dict[str, str] | None = None,
    cookies: dict[str, str] | None = None,
    proxy: str | None = None,
) -> FetchResult:
    """Fetch HTML through the cascade. Levels: 1=direct, 2=curl_cffi, 3=nodriver, 4=camoufox, 5=saas.

    Args:
        url: target URL
        min_level: lowest engine to try (1-5). Default 1. Use 3 to skip straight
            to the browser when the target page requires JS rendering.
        max_level: highest engine to try (1-5). Default 3 (no camoufox/SaaS).
        timeout: per-engine timeout in seconds (engine defaults if None)
        headers: extra HTTP headers (passed to all engines)
        cookies: cookies dict (passed to engines that support it)
        proxy: SOCKS5/HTTP proxy URL (e.g. socks5://127.0.0.1:1080).
            Falls back to STEALTH_FETCH_PROXY env var if not set.

    Returns:
        FetchResult with HTML content and metadata

    Raises:
        RuntimeError: if all engines fail
    """
    if proxy is None:
        proxy = DEFAULT_PROXY

    from .engines import direct, curlffi, stealth, camoufox_engine, saas

    engines: list[tuple[str, object]] = []
    if min_level <= 1:
        engines.append(("direct", direct))
    if min_level <= 2 and max_level >= 2 and curlffi.is_available():
        engines.append(("curlffi", curlffi))
    if max_level >= 3 and min_level <= 3 and stealth.is_available():
        engines.append(("stealth", stealth))
    if max_level >= 4 and min_level <= 4 and camoufox_engine.is_available():
        engines.append(("camoufox", camoufox_engine))
    if max_level >= 5 and saas.is_available():
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
            if proxy:
                kwargs["proxy"] = proxy

            status, html, resp_headers = await engine.fetch(url, **kwargs)  # type: ignore[union-attr]
            elapsed = int((time.monotonic() - t0) * 1000)

            if is_blocked(status, html, resp_headers):
                from .detection import detect_protection
                protection = detect_protection(status, html, resp_headers)
                attempts.append({
                    "engine": name, "status": status, "blocked": True,
                    "protection": protection, "elapsed_ms": elapsed,
                })
                last_error = f"{name}: blocked by {protection}"
                log.warning("engine=%s blocked=%s elapsed=%dms url=%s", name, protection, elapsed, url)

                if proxy and name in ("camoufox", "stealth") and protection == "generic-block":
                    log.warning("engine=%s generic-block with proxy, retrying without proxy url=%s", name, url)
                    t0 = time.monotonic()
                    try:
                        kwargs_no_proxy2: dict[str, object] = {}
                        if timeout is not None:
                            kwargs_no_proxy2["timeout"] = timeout
                        if headers:
                            kwargs_no_proxy2["headers"] = headers
                        if cookies:
                            kwargs_no_proxy2["cookies"] = cookies
                        status2, html2, resp_headers2 = await engine.fetch(url, **kwargs_no_proxy2)  # type: ignore[union-attr]
                        elapsed2 = int((time.monotonic() - t0) * 1000)
                        if not is_blocked(status2, html2, resp_headers2):
                            log.info("engine=%s status=%d (no-proxy retry) elapsed=%dms url=%s", name, status2, elapsed2, url)
                            return FetchResult(
                                html=html2, status=status2, engine=name,
                                final_url=resp_headers2.get("x-final-url"),
                                elapsed_ms=elapsed2, attempts=attempts,
                            )
                        protection2 = detect_protection(status2, html2, resp_headers2)
                        attempts.append({
                            "engine": name, "status": status2, "blocked": True,
                            "protection": protection2, "elapsed_ms": elapsed2,
                            "note": "retry-no-proxy",
                        })
                        log.warning("engine=%s blocked=%s (no-proxy retry) elapsed=%dms url=%s", name, protection2, elapsed2, url)
                    except Exception as exc_np:
                        elapsed2 = int((time.monotonic() - t0) * 1000)
                        attempts.append({
                            "engine": name, "error": str(exc_np), "elapsed_ms": elapsed2,
                            "note": "retry-no-proxy",
                        })
                        log.warning("engine=%s error=%s (no-proxy retry) elapsed=%dms url=%s", name, exc_np, elapsed2, url)

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
            err_str = str(exc)
            last_error = f"{name}: {exc}"
            attempts.append({
                "engine": name, "error": err_str, "elapsed_ms": elapsed,
            })
            log.warning("engine=%s error=%s elapsed=%dms url=%s", name, exc, elapsed, url)

            if proxy and any(m in err_str for m in _PROXY_SSL_MARKERS):
                log.warning("engine=%s proxy-induced SSL error, retrying without proxy url=%s", name, url)
                t0 = time.monotonic()
                try:
                    kwargs_no_proxy: dict[str, object] = {}
                    if timeout is not None:
                        kwargs_no_proxy["timeout"] = timeout
                    if headers:
                        kwargs_no_proxy["headers"] = headers
                    if cookies:
                        kwargs_no_proxy["cookies"] = cookies
                    status, html, resp_headers = await engine.fetch(url, **kwargs_no_proxy)  # type: ignore[union-attr]
                    elapsed = int((time.monotonic() - t0) * 1000)

                    if is_blocked(status, html, resp_headers):
                        from .detection import detect_protection
                        protection = detect_protection(status, html, resp_headers)
                        attempts.append({
                            "engine": name, "status": status, "blocked": True,
                            "protection": protection, "elapsed_ms": elapsed,
                            "note": "retry-no-proxy",
                        })
                        last_error = f"{name}: blocked by {protection} (no-proxy retry)"
                        log.warning("engine=%s blocked=%s (no-proxy retry) elapsed=%dms url=%s", name, protection, elapsed, url)
                        continue

                    log.info("engine=%s status=%d (no-proxy retry) elapsed=%dms url=%s", name, status, elapsed, url)
                    return FetchResult(
                        html=html,
                        status=status,
                        engine=name,
                        final_url=resp_headers.get("x-final-url"),
                        elapsed_ms=elapsed,
                        attempts=attempts,
                    )
                except Exception as exc2:
                    elapsed = int((time.monotonic() - t0) * 1000)
                    attempts.append({
                        "engine": name, "error": str(exc2), "elapsed_ms": elapsed,
                        "note": "retry-no-proxy",
                    })
                    log.warning("engine=%s error=%s (no-proxy retry) elapsed=%dms url=%s", name, exc2, elapsed, url)

            continue

    raise RuntimeError(
        f"all engines failed for {url} (tried: {', '.join(a['engine'] for a in attempts)}). "  # type: ignore[str-bytes-safe]
        f"Last: {last_error}"
    )
