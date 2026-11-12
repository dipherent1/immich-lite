"""Rate limiting via slowapi (wraps the `limits` library).

Two limits are enforced:
  - Global: every IP is capped at RATE_LIMIT_GLOBAL total requests/minute across
    all endpoints — including non-existent (404) paths probed by bots.
  - Auth:   login and register get the stricter RATE_LIMIT_AUTH limit.

The key function uses the real client IP, preferring X-Real-IP (set by Nginx
to $remote_addr) and taking only the rightmost hop from X-Forwarded-For so a
bot cannot spoof its IP by injecting forged leftmost X-Forwarded-For headers.

Counter storage:
  - REDIS_URL set  -> Redis (shared across all Uvicorn workers / containers),
    with automatic in-memory fallback if Redis becomes unreachable at runtime.
  - REDIS_URL unset / "memory://" -> in-memory (dev only, resets on restart).
"""

from __future__ import annotations

import logging
import re

from fastapi import Request, Response
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import _find_route_handler, _get_route_name
from starlette.types import ASGIApp, Receive, Scope, Send

from app.core.config import get_settings

logger = logging.getLogger("app.rate_limit")

_EXEMPT_PATHS = {"/ping", "/metrics"}

# Authenticated image downloads: a gallery page fetches one per thumbnail, so
# counting them against the global per-IP budget throttles normal browsing.
_EXEMPT_PATH_RE = re.compile(r"^/api/v1/events/[^/]+/photos/[^/]+/file$")


def _client_ip(request: Request) -> str:
    """Return the real client IP without trusting spoofable client headers.

    Nginx sets X-Real-IP to $remote_addr and appends $remote_addr to the right
    side of X-Forwarded-For. Reading X-Real-IP (or the rightmost X-Forwarded-For
    entry) prevents bots from rotating fake leftmost X-Forwarded-For values.
    """
    real_ip = request.headers.get("X-Real-IP")
    if real_ip:
        return real_ip.strip()

    forwarded_for = request.headers.get("X-Forwarded-For")
    if forwarded_for:
        return forwarded_for.split(",")[-1].strip()

    return request.client.host if request.client else "unknown"


def _build_limiter() -> Limiter:
    settings = get_settings()
    redis_url = settings.redis_url
    global_limit = settings.rate_limit_global

    # Limiter accepts a storage_uri string:
    #   "memory://"          -> in-process MemoryStorage
    #   "redis://host:port"  -> Redis (requires the redis package)
    storage_uri = redis_url if (redis_url and redis_url != "memory://") else "memory://"
    use_redis = storage_uri.startswith("redis")

    if use_redis:
        logger.info(
            "Rate limiter using Redis storage at %s (global=%s)",
            storage_uri,
            global_limit,
        )
    else:
        logger.info("Rate limiter using in-memory storage (dev mode, global=%s)", global_limit)

    return Limiter(
        key_func=_client_ip,
        storage_uri=storage_uri,
        application_limits=[global_limit],
        in_memory_fallback=[global_limit] if use_redis else [],
        in_memory_fallback_enabled=use_redis,
    )


# Single shared limiter instance — imported by main.py and endpoint modules.
limiter: Limiter = _build_limiter()


def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceeded) -> Response:
    """Return a JSON 429 with standard Retry-After semantics."""
    limit_label = exc.detail or "rate limit exceeded"
    logger.warning(
        "rate limit exceeded: %s %s (ip=%s limit=%s)",
        request.method,
        request.url.path,
        _client_ip(request),
        limit_label,
    )

    retry_after = None
    limit_item = getattr(getattr(exc, "limit", None), "limit", None)
    if limit_item is not None and hasattr(limit_item, "get_expiry"):
        retry_after = limit_item.get_expiry()

    headers = {"Retry-After": str(retry_after)} if retry_after else {}
    return JSONResponse(
        status_code=429,
        content={
            "detail": "Too many requests. Please slow down.",
            "limit": limit_label,
        },
        headers=headers,
    )


class RateLimitMiddleware:
    """Pure ASGI rate-limiting middleware.

    Unlike SlowAPIMiddleware (which uses BaseHTTPMiddleware and skips 404s):
      1. Does not buffer responses, so SSE streaming works without interference.
      2. Enforces the global per-IP limit even on unknown/404 paths so bots
         probing random endpoints (/.env, /wp-login.php, etc.) are throttled.
      3. Exempts /ping and /metrics so healthchecks and Prometheus scrapes pass,
         and authenticated photo file downloads (one request per thumbnail).
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        app = scope.get("app")
        active_limiter: Limiter = getattr(getattr(app, "state", None), "limiter", limiter)
        if not active_limiter.enabled:
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive, send=send)
        if request.url.path in _EXEMPT_PATHS or _EXEMPT_PATH_RE.match(request.url.path):
            await self.app(scope, receive, send)
            return

        handler = _find_route_handler(app.routes, scope) if app is not None else None
        if handler is not None and _get_route_name(handler) in active_limiter._route_limits:
            # Route has its own @limiter.limit(...) decorator (e.g. tighter auth limit);
            # let the decorator enforce it rather than double-checking here.
            await self.app(scope, receive, send)
            return

        try:
            active_limiter._check_request_limit(request, handler, True)
        except RateLimitExceeded as exc:
            response = rate_limit_exceeded_handler(request, exc)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
