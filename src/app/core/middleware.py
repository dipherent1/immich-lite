"""HTTP request logging middleware.

Logs every request with method, path, response status and duration, plus the
authenticated user id when available. Server errors (5xx) are logged at ERROR
with the full traceback so they're easy to find. No tokens are ever logged.
"""

from __future__ import annotations

import logging
import time
import uuid

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.logging import clear_correlation, set_correlation
from app.core.metrics import observe_http

logger = logging.getLogger("app.request")

_WELL_KNOWN = {"/ping", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect", "/metrics"}


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid.uuid4().hex[:12]
        set_correlation(request_id=request_id)
        scope["request_id"] = request_id

        start = time.perf_counter()
        request = Request(scope)
        # Where the first response status will be recorded.
        scope["_status_code"] = 500

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                scope["_status_code"] = message.get("status", 500)
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            logger.error(
                "unhandled exception in %s %s (%.1fms)",
                request.method,
                request.url.path,
                duration_ms,
                exc_info=True,
                extra={"extra_fields": {"method": request.method, "path": request.url.path}},
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            duration_s = duration_ms / 1000.0
            status = scope.get("_status_code", 500)

            # Emit Prometheus metrics (skip well-known endpoints like docs/ping/metrics).
            route = getattr(scope.get("route"), "path", None) or request.url.path
            observe_http(request.method, route, status, duration_s)

            if request.url.path in _WELL_KNOWN:
                clear_correlation()
                return

            user = getattr(request.state, "user_id", None)
            if user:
                set_correlation(user_id=user)

            fields = {
                "method": request.method,
                "path": request.url.path,
                "status": status,
                "duration_ms": round(duration_ms, 1),
                "request_id": request_id,
            }
            msg = "%s %s -> %d (%.1fms)" % (request.method, request.url.path, status, duration_ms)

            if status >= 500:
                logger.error(msg, extra={"extra_fields": fields})
            elif status >= 400:
                logger.warning(msg, extra={"extra_fields": fields})
            else:
                logger.info(msg, extra={"extra_fields": fields})

            clear_correlation()
