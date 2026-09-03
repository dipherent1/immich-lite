from __future__ import annotations

import logging
import os
import time

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


def process_photo(photo_id: str) -> int:
    """RQ job: process a single uploaded photo, then match it to attendees.

    1. Ingestion — detect + embed every face and store them in `event_faces`.
    2. Matching  — for each stored face, search attendees' `user_profiles`
       (restricted to the event's attendees) and write PhotoMatch rows.

    Ingestion failure marks the photo `failed` and aborts matching. NOTE: this
    synchronous pipeline is the seam where a heavier async pipeline would slot
    in — for volume growth the embedding call stays thread/process-offloaded
    and this worker can be scaled independently of the API container.
    """
    ingestion, matching, db = _build_job()
    try:
        photo = ingestion.process_by_id(photo_id)
        # Matching is a separate, independently testable service call that runs
        # automatically after embedding is stored (Phase 5).
        return matching.match_photo(photo)
    finally:
        db.close()


def main() -> None:
    import logging.config

    from app.core.logging import setup_logging

    setup_logging()

    from redis import Redis
    from redis.exceptions import ConnectionError as RedisConnectionError
    from redis.exceptions import TimeoutError as RedisTimeoutError
    from rq import Queue, Worker

    settings = get_settings()
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

    # The worker is long-lived but its Redis connection can hit a transient
    # socket timeout; RQ's work() then quits and the process dies, leaving any
    # queued photo job (and thus its matching) silently stalled. Keep the
    # connection alive with keepalive + retry-on-timeout and, should it ever
    # break anyway, reconnect and resume in a fresh loop instead of exiting.
    while True:
        try:
            connection = Redis.from_url(
                redis_url,
                socket_keepalive=True,
                socket_timeout=None,
                socket_connect_timeout=10,
                retry_on_timeout=True,
            )
            queue = Queue("photos", connection=connection)
            worker = Worker([queue], connection=connection)
            logger.info("photo worker starting (pid=%s) redis=%s", os.getpid(), redis_url)
            worker.work(with_scheduler=False)
            logger.warning("photo worker work() returned; reconnecting")
        except (RedisConnectionError, RedisTimeoutError) as exc:
            logger.warning("photo worker lost Redis connection (%s); reconnecting", exc)
        time.sleep(3)


if __name__ == "__main__":
    main()
