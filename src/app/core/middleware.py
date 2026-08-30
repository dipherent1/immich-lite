"""HTTP request logging middleware.

Logs every request with method, path, response status and duration, plus the
authenticated user id when available. Server errors (5xx) are logged at ERROR
with the full traceback so they're easy to find. No tokens are ever logged.
"""

from __future__ import annotations

import logging
import time

from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger("app.request")

_WELL_KNOWN = {"/ping", "/openapi.json", "/docs", "/redoc", "/docs/oauth2-redirect"}


class RequestLoggingMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

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
            )
            raise
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            status = scope.get("_status_code", 500)

            if request.url.path in _WELL_KNOWN:
                return

            user = getattr(request.state, "user_id", None)
            user_part = f" user={user}" if user else ""

            if status >= 500:
                logger.error(
                    "HTTP %s %s -> %d (%.1fms)%s",
                    request.method,
                    request.url.path,
                    status,
                    duration_ms,
                    user_part,
                )
            elif status >= 400:
                logger.warning(
                    "HTTP %s %s -> %d (%.1fms)%s",
                    request.method,
                    request.url.path,
                    status,
                    duration_ms,
                    user_part,
                )
            else:
                logger.info(
                    "HTTP %s %s -> %d (%.1fms)%s",
                    request.method,
                    request.url.path,
                    status,
                    duration_ms,
                    user_part,
                )
