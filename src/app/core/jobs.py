from __future__ import annotations

import logging
import os

from app.core.config import get_settings

logger = logging.getLogger("app.jobs")


def enqueue_photo_processing(photo_id: str) -> None:
    """Enqueue a photo for background embedding/matching (Redis + RQ).

    Only the API process calls this; the dedicated `worker` container consumes
    the job and runs the CPU-bound face/embedding step, keeping the event loop
    free to serve requests. If Redis/RQ is unavailable the API still returns a
    valid pending Photo, but a failure here is logged loudly so the operator
    knows the job never reached the worker.
    """
    try:
        from redis import Redis
        from rq import Queue

        connection = Redis.from_url(get_settings().redis_url)
        queue = Queue("photos", connection=connection)
        queue.enqueue("app.workers.photo_worker.process_photo", photo_id, job_timeout=300)
        logger.info("enqueued photo job photo=%s", photo_id)
    except Exception:
        logger.exception("failed to enqueue photo job photo=%s", photo_id)
        raise
