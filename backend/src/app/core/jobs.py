from __future__ import annotations

import logging

from app.core.celery_app import celery_app
from app.core.metrics import record_enqueue

logger = logging.getLogger("app.jobs")


def enqueue_photo_processing(photo_id: str) -> None:
    """Enqueue a photo for background embedding/matching (Celery + RabbitMQ).

    Only the API process calls this; the dedicated `worker` container consumes
    the job and runs the CPU-bound face/embedding step, keeping the event loop
    free to serve requests. If RabbitMQ is unavailable the API still returns a
    valid pending Photo, but a failure here is logged loudly so the operator
    knows the job never reached the worker.
    """
    try:
        # Send by name so the API never imports the worker module (and thus the
        # heavy CV/ONNX stack); the worker registers this task from `include`.
        result = celery_app.send_task(
            "app.workers.photo_worker.process_photo", args=[photo_id], queue="photos"
        )
        record_enqueue("photos")
        logger.info(
            "enqueued photo job",
            extra={"extra_fields": {"photo_id": photo_id, "job_id": result.id}},
        )
    except Exception:
        logger.exception("failed to enqueue photo job photo=%s", photo_id)
        raise
