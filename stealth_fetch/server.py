"""HTTP microservice — POST /fetch-html."""

import logging

from .cascade import fetch_html

log = logging.getLogger("stealth_fetch")


def create_app():
    from fastapi import FastAPI
    from pydantic import BaseModel

    app = FastAPI(title="stealth-fetch", version="0.1.0")

    class FetchRequest(BaseModel):
        url: str
        min_level: int = 1
        max_level: int = 3
        timeout: float | None = None
        headers: dict[str, str] | None = None
        cookies: dict[str, str] | None = None

    class FetchResponse(BaseModel):
        html: str
        status: int
        engine: str
        final_url: str | None = None
        elapsed_ms: int = 0
        protection: str | None = None

    class ErrorResponse(BaseModel):
        error: str
        attempts: list[dict] = []

    @app.post("/fetch-html", response_model=FetchResponse)
    async def handle_fetch(req: FetchRequest):
        try:
            result = await fetch_html(
                req.url,
                min_level=req.min_level,
                max_level=req.max_level,
                timeout=req.timeout,
                headers=req.headers,
                cookies=req.cookies,
            )
            return FetchResponse(
                html=result.html,
                status=result.status,
                engine=result.engine,
                final_url=result.final_url,
                elapsed_ms=result.elapsed_ms,
                protection=result.protection,
            )
        except RuntimeError as exc:
            from fastapi.responses import JSONResponse
            return JSONResponse(
                status_code=502,
                content={"error": str(exc)},
            )

    @app.get("/health")
    async def health():
        from .engines import curlffi, stealth, saas
        return {
            "status": "ok",
            "engines": {
                "direct": True,
                "curlffi": curlffi.is_available(),
                "stealth": stealth.is_available(),
                "saas": saas.is_available(),
            },
        }

    return app


def main():
    import uvicorn
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8410)


if __name__ == "__main__":
    main()
