"""Server-Sent Events (SSE) connection manager.

The API process keeps one module-level `sse_manager`. Each connected browser
registers a per-user queue via `connect(user_id)`; a Redis pub/sub listener
(started in `main.py`) calls `dispatch(user_id, data)` whenever a notification
event was published for that user, which fans the payload out to every live
connection for that user.

The worker process never talks to browsers directly — it only publishes to
Redis. The API server is the single SSE gateway, so a single broadcast touchpoint
(Redis) keeps the two process models decoupled.
"""

from __future__ import annotations

import asyncio
import json

from app.models.notification import Notification

_SSE_TYPE = "notification"


class SSEManager:
    def __init__(self) -> None:
        # user_id -> list of per-connection asyncio.Queue
        self._clients: dict[str, list[asyncio.Queue]] = {}

    def add_client(self, user_id: str, queue: asyncio.Queue) -> None:
        """Register a connection queue for a user (called by the SSE endpoint)."""
        self._clients.setdefault(user_id, []).append(queue)

    def remove_client(self, user_id: str, queue: asyncio.Queue) -> None:
        """Deregister a connection queue (called when the stream closes)."""
        try:
            self._clients[user_id].remove(queue)
        except (KeyError, ValueError):
            pass
        if not self._clients.get(user_id):
            self._clients.pop(user_id, None)

    async def connect(self, user_id: str) -> object:
        """Register a new connection for a user; returns an async generator of
        event payloads. The caller wraps this in a StreamingResponse."""
        queue: asyncio.Queue = asyncio.Queue()
        self._clients.setdefault(user_id, []).append(queue)
        try:
            while True:
                payload = await queue.get()
                yield f"event: {_SSE_TYPE}\n" f"data: {json.dumps(payload)}\n\n"
        finally:
            try:
                self._clients[user_id].remove(queue)
            except (KeyError, ValueError):
                pass
            if not self._clients.get(user_id):
                self._clients.pop(user_id, None)

    def dispatch(self, user_id: str, notification: Notification, payload: dict) -> None:
        """Fan a notification out to every live connection of a user."""
        for queue in self._clients.get(user_id, []):
            queue.put_nowait(payload)

    def dispatch_raw(self, user_id: str, payload: dict) -> None:
        """Fan an already-built payload dict out to a user's live connections."""
        for queue in self._clients.get(user_id, []):
            queue.put_nowait(payload)


# Shared singleton — the API process's client manager.
sse_manager = SSEManager()


def _notification_payload(notification: Notification) -> dict:
    """Serialize a Notification ORM object into the JSON shape relayed to SSE."""
    return {
        "id": notification.id,
        "type": notification.type,
        "title": notification.title,
        "body": notification.body,
        "subject_type": notification.subject_type,
        "subject_id": notification.subject_id,
        "is_read": notification.is_read,
        "created_at": notification.created_at.isoformat(),
    }
