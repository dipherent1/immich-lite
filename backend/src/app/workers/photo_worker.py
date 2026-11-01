from __future__ import annotations

import logging
import os
import sys

from app.core.celery_app import celery_app
from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.file_storage import LocalFileService
from app.core.vector_db import EventFaceRepository, QdrantProfileRepository
from app.domain.interfaces import EmbeddingProvider
from app.repositories.event_repository import EventRepository
from app.repositories.photo_match_repository import PhotoMatchRepository
from app.repositories.photo_repository import PhotoRepository
from app.services.embedding_service import InsightFaceEmbeddingService
from app.services.ingestion_service import IngestionService
from app.services.matching_service import MatchingService

logger = logging.getLogger(__name__)


def _build_job() -> tuple[IngestionService, MatchingService, SessionLocal]:
    """Construct fresh ingestion + matching services for a single job, returning
    the owning session so the caller can close it when the job finishes.

    Each job opens its own DB session, its own lazily-loaded embedder, and its
    own Qdrant handles so a worker restart or an individual failure never leaks
    state across photos.
    """
    settings = get_settings()
    embedder: EmbeddingProvider = InsightFaceEmbeddingService(
        model_name=settings.model_name,
        detection_threshold=settings.detection_threshold,
    )
    db = SessionLocal()
    photo_repo = PhotoRepository(db)
    event_repo = EventRepository(db)
    match_repo = PhotoMatchRepository(db)
    faces = EventFaceRepository(url=settings.qdrant_url)
    profiles = QdrantProfileRepository(url=settings.qdrant_url)
    files = LocalFileService(root=settings.output_root)

    ingestion = IngestionService(embedder, photo_repo, faces, files)
    matching = MatchingService(
        event_repo,
        faces,
        profiles,
        match_repo,
        similarity_threshold=settings.similarity_threshold,
    )
    return ingestion, matching, db


@celery_app.task(bind=True, name="app.workers.photo_worker.process_photo")
def process_photo(self, photo_id: str) -> int:
    """Celery task: process a single uploaded photo, then match it to attendees.

    1. Ingestion — detect + embed every face and store them in `event_faces`.
    2. Matching  — for each stored face, search attendees' `user_profiles`
       (restricted to the event's attendees) and write PhotoMatch rows.

    Ingestion failure marks the photo `failed` and aborts matching. NOTE: this
    synchronous pipeline is the seam where a heavier async pipeline would slot
    in — for volume growth the embedding call stays thread/process-offloaded
    and this worker can be scaled independently of the API container.
    """
    from app.core.logging import clear_correlation, set_correlation

    set_correlation(job_id=self.request.id)
    ingestion, matching, db = _build_job()
    try:
        photo = ingestion.process_by_id(photo_id)
        logger.info(
            "processing photo",
            extra={"extra_fields": {"photo_id": photo_id, "event_id": photo.event_id}},
        )
        # Matching is a separate, independently testable service call that runs
        # automatically after embedding is stored (Phase 5).
        matched_user_ids = matching.match_photo(photo)
        _publish_match_notifications(photo, matched_user_ids, db)
        return matched_user_ids
    finally:
        db.close()
        clear_correlation()


def _publish_match_notifications(photo, matched_user_ids: set[str], db) -> None:
    """Notify every attendee whose face matched this photo. Best-effort: a
    notification failure never marks the job as failed (publish_notification
    already swallows RabbitMQ errors)."""
    from app.core.notification_publisher import publish_notification
    from app.repositories.event_repository import EventRepository

    event_repo = EventRepository(db)
    event = event_repo.get_by_id(photo.event_id)
    event_name = event.name if event is not None else "the event"
    for user_id in matched_user_ids:
        # Never notify the uploader for their own upload (they know they added it).
        if user_id == photo.uploader_user_id:
            continue
        publish_notification(
            user_id=user_id,
            type="photo_matched",
            title="New match found!",
            body=f"A photo in {event_name} matches your face",
            subject_type="event",
            subject_id=photo.event_id,
        )


def main() -> None:
    from app.core.logging import setup_logging

    setup_logging()

    # Prefork is the default on Linux; solo is required for a native Windows
    # dev run (prefork is not supported there).
    pool = "solo" if sys.platform == "win32" else "prefork"
    concurrency = os.environ.get("CELERY_CONCURRENCY", "1")

    logger.info(
        "photo worker starting (pid=%s) broker=%s pool=%s concurrency=%s",
        os.getpid(),
        get_settings().rabbitmq_url,
        pool,
        concurrency,
    )
    celery_app.worker_main(
        argv=[
            "worker",
            "--loglevel=INFO",
            "--queues=photos",
            f"--pool={pool}",
            f"--concurrency={concurrency}",
        ]
    )


if __name__ == "__main__":
    main()
