"""Publish notification events to Redis (used by the worker process).

The worker does the heavy ingestion/matching and may live in a separate
container from the API server. When it finds a match it publishes a
notification event to a Redis pub/sub channel; the API server's listener
subscribes to that channel, persists a Notification row, and relays it to the
requesting user's live SSE connection. This keeps the two processes decoupled —
the worker only knows Redis, never about the browser SSE connections.
"""

from __future__ import annotations

import json
import logging

from app.core.config import get_settings

logger = logging.getLogger("app.notifications")

# Channel the worker publishes to; the API server subscribes on the same channel.
EVENTS_CHANNEL = "notifications:events"


def publish_notification(
    *,
    user_id: str,
    type: str,
    title: str,
    body: str,
    subject_type: str | None = None,
    subject_id: str | None = None,
) -> None:
    """Publish a notification event to Redis. Best-effort: a Redis outage here
    must never fail the worker job, so failures are logged, not raised."""
    try:
        from redis import Redis

        connection = Redis.from_url(get_settings().redis_url)
        connection.publish(
            EVENTS_CHANNEL,
            json.dumps(
                {
                    "user_id": user_id,
                    "type": type,
                    "title": title,
                    "body": body,
                    "subject_type": subject_type,
                    "subject_id": subject_id,
                }
            ),
        )
        logger.info(
            "published notification event",
            extra={"extra_fields": {"user_id": user_id, "type": type}},
        )
    except Exception:
        logger.exception(
            "failed to publish notification event user=%s type=%s", user_id, type
        )
