from __future__ import annotations

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.api import api_router
from app.core.config import get_settings
from app.core.logging import setup_logging
from app.core.middleware import RequestLoggingMiddleware

logger = setup_logging()

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)

# Order matters: within Starlette/FastAPI, the LAST-added middleware is the
# outermost. We add CORS first so it wraps request logging, then our logging
# middleware so it wraps the routing layer.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in settings.cors_origins.split(",") if origin.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

app.include_router(api_router)

logger.info("Application starting up (app=%s v%s)", settings.app_name, settings.app_version)


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Last-resort handler: log any uncaught error with its traceback so it's
    findable, then return a generic 500 (never leak internals to the client)."""
    logger.error(
        "unhandled exception on %s %s: %s",
        request.method,
        request.url.path,
        exc,
        exc_info=True,
    )
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


@app.get("/ping")
async def ping() -> dict[str, str]:
    return {"message": "pong"}
