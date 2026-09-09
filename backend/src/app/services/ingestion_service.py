from __future__ import annotations

import logging

from app.core.file_storage import LocalFileService
from app.core.vector_db import EventFaceRepository
from app.domain.interfaces import EmbeddingProvider
from app.models.photo import Photo
from app.repositories.photo_repository import PhotoRepository

logger = logging.getLogger("app.ingestion")


class IngestionService:
    """Turns a stored event photo into face embeddings in Qdrant.

    Reads the photo by its `storage_path` (never copies it), detects+embeds every
    face with the provided embedder, upserts one point per face into the
    `event_faces` Qdrant collection (payload carries `event_id` + `photo_id` +
    bbox), then marks the Photo `processed`. On any failure the photo is marked
    `failed` so the worker can surface it rather than silently dropping it.

    Embedding is CPU-bound; this class is called from a plain `def` context or a
    separate worker process (never inside the event loop hot path).
    """

    def __init__(
        self,
        embedder: EmbeddingProvider,
        repo: PhotoRepository,
        faces: EventFaceRepository,
        files: LocalFileService,
    ) -> None:
        self._embedder = embedder
        self._repo = repo
        self._faces = faces
        self._files = files

    def process(self, photo: Photo) -> int:
        """Process a single photo. Returns the number of faces stored."""
        try:
            image_bytes = self._files.read(photo.storage_path)
            embeddings = self._embedder.detect_and_embed(image_bytes)
            face_count = self._faces.upsert_faces(
                event_id=photo.event_id,
                photo_id=photo.id,
                embeddings=embeddings,
            )
            self._repo.set_status(photo.id, "processed", processed=True)
            logger.info(
                "photo processed event=%s photo=%s faces=%d",
                photo.event_id,
                photo.id,
                face_count,
            )
            return face_count
        except Exception:
            logger.exception(
                "photo processing failed event=%s photo=%s",
                photo.event_id,
                photo.id,
            )
            self._repo.set_status(photo.id, "failed")
            raise

    def process_by_id(self, photo_id: str) -> Photo:
        photo = self._repo.get_by_id(photo_id)
        if photo is None:
            logger.warning("photo not found for processing: %s", photo_id)
            raise FileNotFoundError(f"Photo {photo_id} not found")
        self.process(photo)
        return photo
