"""Celery application backed by RabbitMQ.

The API enqueues photo-processing jobs onto the `photos` queue; a dedicated
worker container consumes them. Results are never retrieved (matching writes to
Postgres), so the app runs without a result backend.
"""

from __future__ import annotations

import logging
import os

from celery import Celery
from celery.signals import after_setup_logger, after_setup_task_logger, worker_ready

from app.core.config import get_settings

logger = logging.getLogger("app.worker")

settings = get_settings()

celery_app = Celery(
    "immich_lite",
    broker=settings.rabbitmq_url,
    include=["app.workers.photo_worker"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_ignore_result=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    broker_connection_retry_on_startup=True,
    broker_heartbeat=30,
    worker_send_task_events=True,
    task_send_sent_event=True,
    task_track_started=True,
    # RabbitMQ 4.3+ rejects transient non-exclusive queues; Celery's control
    # (pidbox) and event queues default to that shape, so make them exclusive.
    control_queue_exclusive=True,
    event_queue_exclusive=True,
    task_default_queue="photos",
    # Periodic sweep: warn attendees ~20 min before an event ends, then delete it.
    # Driven by the worker's embedded beat (see photo_worker.main).
    beat_schedule={
        "sweep-expired-events": {
            "task": "app.workers.photo_worker.sweep_expired_events",
            "schedule": float(settings.event_sweep_interval_seconds),
            "options": {"queue": "photos", "expires": 55},
        }
    },
    timezone="UTC",
    enable_utc=True,
)


@after_setup_logger.connect
@after_setup_task_logger.connect
def _install_error_alerts(**_kwargs) -> None:
    """Celery replaces the root logger's handlers when the worker starts, so the
    Telegram alert handler is (re)attached here. Failed tasks are logged at ERROR
    by Celery and so become alerts. Idempotent; a no-op unless alerts are enabled."""
    try:
        from app.core.alerting import install_alert_handler

        install_alert_handler()
    except Exception:
        logger.warning("could not set up error alerts", exc_info=True)


@worker_ready.connect
def _start_worker_metrics(**_kwargs) -> None:
    """Serve the worker's /metrics from the parent process so Prometheus can
    alert the moment the worker dies."""
    from app.core.worker_metrics import start_metrics_server

    start_metrics_server(port=int(os.environ.get("WORKER_METRICS_PORT", "9100")))
