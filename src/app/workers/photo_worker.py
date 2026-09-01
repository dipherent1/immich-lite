from __future__ import annotations

import logging
import os

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.core.file_storage import LocalFileService
from app.core.vector_db import EventFaceRepository
from app.domain.interfaces import EmbeddingProvider
from app.repositories.photo_repository import PhotoRepository
from app.services.embedding_service import InsightFaceEmbeddingService
from app.services.ingestion_service import IngestionService

logger = logging.getLogger(__name__)


def _build_ingestion() -> tuple[IngestionService, SessionLocal]:
    """Construct an IngestionService with fresh deps for a single job, returning
    the owning session so the caller can close it when the job finishes.

    Each job opens its own DB session and its own lazily-loaded embedder so a
    worker restart or an individual failure never leaks state across photos.
    """
    settings = get_settings()
    embedder: EmbeddingProvider = InsightFaceEmbeddingService(
        model_name=settings.model_name,
        detection_threshold=settings.detection_threshold,
    )
    db = SessionLocal()
    repo = PhotoRepository(db)
    faces = EventFaceRepository(url=settings.qdrant_url)
    files = LocalFileService(root=settings.output_root)
    return IngestionService(embedder, repo, faces, files), db


def process_photo(photo_id: str) -> int:
    """RQ job: process a single uploaded photo (detect + embed + store faces).

    NOTE: this synchronous ingestion is the seam where a heavier async pipeline
    would slot in. For volume growth the `embedding_service` call stays
    thread/process-offloaded and this worker can be scaled out independently of
    the API container.
    """
    service, db = _build_ingestion()
    try:
        return service.process_by_id(photo_id)
    finally:
        db.close()


def main() -> None:
    import logging.config

    from app.core.logging import setup_logging

    setup_logging()

    from redis import Redis
    from rq import Queue, Worker

    settings = get_settings()
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    logger.info("photo worker starting, redis=%s", redis_url)

    connection = Redis.from_url(redis_url)
    queue = Queue("photos", connection=connection)
    worker = Worker([queue], connection=connection)
    worker.work(with_scheduler=False)


if __name__ == "__main__":
    main()
