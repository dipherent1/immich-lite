"""Rate limiting via slowapi (wraps the `limits` library).

Two limits are enforced:
  - Global: every route is capped at RATE_LIMIT_GLOBAL requests/minute per IP.
  - Auth:   login and register get the stricter RATE_LIMIT_AUTH limit.

The key function uses the real client IP, respecting X-Forwarded-For when the
request comes through a trusted proxy (Nginx in production). We only peel one
proxy hop so a bot cannot spoof by stuffing extra X-Forwarded-For values.

Counter storage:
  - REDIS_URL set  → Redis (shared across all Uvicorn workers / containers).
  - REDIS_URL unset / "memory://" → in-memory (dev only, resets on restart).
"""

from __future__ import annotations

import logging

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from limits.storage import MemoryStorage, RedisStorage
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded

from app.core.config import get_settings

logger = logging.getLogger("app.rate_limit")


def _client_ip(request: Request) -> str:
    """Return the real client IP.

    In production Nginx sets X-Forwarded-For before the request reaches
    Uvicorn; we trust only the leftmost address (the original client) so a bot
    cannot inject a forged IP by appending extra values.
    """
    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        # "client, proxy1, proxy2" — take only the leftmost entry.
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _build_limiter() -> Limiter:
    settings = get_settings()
    redis_url = settings.redis_url
    global_limit = settings.rate_limit_global

    if redis_url and redis_url != "memory://":
        try:
            storage = RedisStorage(redis_url)
            logger.info(
                "Rate limiter using Redis storage at %s (global=%s)",
                redis_url,
                global_limit,
            )
        except Exception:
            logger.warning(
                "Could not connect to Redis (%s); falling back to in-memory rate limiting",
                redis_url,
                exc_info=True,
            )
            storage = MemoryStorage()
    else:
        logger.info("Rate limiter using in-memory storage (dev mode, global=%s)", global_limit)
        storage = MemoryStorage()

    return Limiter(
        key_func=_client_ip,
        storage_uri=None,
        storage=storage,
        default_limits=[global_limit],
    )


# Single shared limiter instance — imported by main.py and endpoint modules.
limiter: Limiter = _build_limiter()


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Return a JSON 429 with standard Retry-After semantics."""
    logger.warning(
        "rate limit exceeded: %s %s (ip=%s limit=%s)",
        request.method,
        request.url.path,
        _client_ip(request),
        exc.limit,
    )
    retry_after = getattr(exc.limit, "reset_time", None)
    headers = {"Retry-After": str(retry_after)} if retry_after else {}
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests. Please slow down.",
            "limit": str(exc.limit),
        },
        headers=headers,
    )
