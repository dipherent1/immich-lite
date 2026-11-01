"""Publish notification events to RabbitMQ (used by the worker process).

The worker does the heavy ingestion/matching and may live in a separate
container from the API server. When it finds a match it publishes a
notification event to a RabbitMQ fanout exchange; the API server's listener
subscribes to that exchange, persists a Notification row, and relays it to the
requesting user's live SSE connection. This keeps the two processes decoupled —
the worker only knows RabbitMQ, never about the browser SSE connections.
"""

from __future__ import annotations

import json
import logging

from app.core.config import get_settings

logger = logging.getLogger("app.notifications")

# Fanout exchange the worker publishes to; every API instance binds its own
# (exclusive) queue so each connected browser receives the event.
EVENTS_EXCHANGE = "notifications.events"


def publish_notification(
    *,
    user_id: str,
    type: str,
    title: str,
    body: str,
    subject_type: str | None = None,
    subject_id: str | None = None,
) -> None:
    """Publish a notification event to RabbitMQ. Best-effort: a broker outage
    here must never fail the worker job, so failures are logged, not raised."""
    try:
        import pika

        params = pika.URLParameters(get_settings().rabbitmq_url)
        params.connection_attempts = 1
        params.socket_timeout = 10
        params.blocked_connection_timeout = 10
        connection = pika.BlockingConnection(params)
        try:
            channel = connection.channel()
            channel.exchange_declare(
                exchange=EVENTS_EXCHANGE, exchange_type="fanout", durable=True
            )
            channel.basic_publish(
                exchange=EVENTS_EXCHANGE,
                routing_key="",
                body=json.dumps(
                    {
                        "user_id": user_id,
                        "type": type,
                        "title": title,
                        "body": body,
                        "subject_type": subject_type,
                        "subject_id": subject_id,
                    }
                ).encode("utf-8"),
                properties=pika.BasicProperties(content_type="application/json"),
            )
        finally:
            connection.close()
        logger.info(
            "published notification event",
            extra={"extra_fields": {"user_id": user_id, "type": type}},
        )
    except Exception:
        logger.exception(
            "failed to publish notification event user=%s type=%s", user_id, type
        )
