"""RabbitMQ → SSE relay for the API process.

Notifications can be produced in two places:
  - In-process (API): join-request/approval/denial services call
    `NotificationService.create`, which persists a row and dispatches directly
    to the user's live SSE connection.
  - The worker process (photo matched): it publishes a raw event to a RabbitMQ
    fanout exchange. This background listener binds its own exclusive queue to
    that exchange, persists a Notification row (its own DB session), and relays
    it to the user's live SSE connection.

Either way the source of truth is the Postgres row; the live push is an
optimization. The listener is started in `main.py`.
"""

from __future__ import annotations

import asyncio
import json
import logging

from app.core.config import get_settings
from app.core.notification_publisher import EVENTS_EXCHANGE

logger = logging.getLogger("app.notifications.sse")


async def notification_relay() -> None:
    """Subscribe to the notification exchange and relay each event to the
    relevant user's SSE connections. Never raises out: on any transient error it
    logs and reconnects so the gateway stays alive."""
    try:
        import aio_pika
    except ImportError:
        logger.warning("aio-pika unavailable; notification SSE relay disabled")
        return

    while True:
        connection = None
        try:
            # Non-robust connect + our own retry loop: `connect_robust` returns
            # immediately and blocks `channel()` forever while the broker is
            # down, which also makes shutdown/cancellation hang.
            connection = await aio_pika.connect(
                get_settings().rabbitmq_url, timeout=10
            )
            channel = await connection.channel()
            exchange = await channel.declare_exchange(
                EVENTS_EXCHANGE,
                aio_pika.ExchangeType.FANOUT,
                durable=True,
            )
            # Exclusive/auto-delete queue: every API instance gets its own copy
            # of every event (fanout) and the queue disappears when it stops.
            queue = await channel.declare_queue(exclusive=True, auto_delete=True)
            await queue.bind(exchange)
            logger.info("notification SSE relay subscribed to %s", EVENTS_EXCHANGE)
            async with queue.iterator() as messages:
                async for message in messages:
                    async with message.process():
                        try:
                            payload = json.loads(message.body)
                            _handle_event(payload)
                        except Exception:
                            logger.exception("failed to relay notification event")
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("notification SSE relay error; reconnecting in 5s")
            await asyncio.sleep(5)
        finally:
            if connection is not None:
                try:
                    await connection.close()
                except Exception:
                    logger.debug("failed to close relay connection", exc_info=True)


def _handle_event(payload: dict) -> None:
    """Persist a worker-published notification and dispatch it to the user's
    live SSE connection."""
    user_id = payload.get("user_id")
    if not user_id:
        return

    # Persist the row with a fresh DB session (the async loop must not block on
    # the DB writer; run the synchronous DB work in a thread).
    from concurrent.futures import ThreadPoolExecutor

    saved = None

    def _persist() -> dict:
        from app.core.database import SessionLocal
        from app.repositories.notification_repository import NotificationRepository

        db = SessionLocal()
        try:
            repo = NotificationRepository(db)
            notif = repo.create(
                user_id=user_id,
                type=payload["type"],
                title=payload["title"],
                body=payload["body"],
                subject_type=payload.get("subject_type"),
                subject_id=payload.get("subject_id"),
            )
            return {
                "id": notif.id,
                "type": notif.type,
                "title": notif.title,
                "body": notif.body,
                "subject_type": notif.subject_type,
                "subject_id": notif.subject_id,
                "is_read": notif.is_read,
                "created_at": notif.created_at.isoformat(),
            }
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        saved = pool.submit(_persist).result()

    from app.core.sse import sse_manager

    sse_manager.dispatch_raw(user_id, saved)
