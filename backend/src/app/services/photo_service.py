from __future__ import annotations

import logging
import uuid
from pathlib import PurePath

from fastapi import HTTPException, status

from app.core.file_storage import LocalFileService
from app.core.jobs import enqueue_photo_processing
from app.models.photo import Photo
from app.repositories.event_repository import EventRepository
from app.repositories.photo_repository import PhotoRepository
from app.services.event_service import EventService

logger = logging.getLogger("app.photo")

# Allow common raster formats that the embedding pipeline can decode (incl. HEIC).
_ALLOWED_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp",
    ".heic", ".heif", ".tiff", ".tif", ".gif", ".avif",
}
MAX_UPLOAD_BYTES = 20 * 1024 * 1024  # 20 MB


class PhotoService:
    """Upload business rules for event photos.

    Scoped to a single event: only an owner/attendee may upload, and only while
    the event is active. The image is stored once (never duplicated), a `pending`
    Photo row is created, and embedding is handed off to the worker queue. The
    recipient/matching code (Phase 5) references the same `storage_path` — it
    never copies the file.
    """

    def __init__(
        self,
        events: EventRepository,
        photos: PhotoRepository,
        files: LocalFileService,
    ) -> None:
        self._events = events
        self._photos = photos
        self._files = files

    def upload(self, user_id: str, event_id: str, filename: str, data: bytes) -> Photo:
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Photo exceeds the 20 MB upload limit",
            )

        event = self._events.get_by_id(event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )

        # Only an owner/attendee may upload, and only while the event is active.
        self._ensure_member(user_id, event_id)
        if not EventService.is_active(event):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This event is no longer active",
            )

        ext = PurePath(filename).suffix.lower() or ".jpg"
        if ext not in _ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Unsupported image type: {ext}",
            )

        photo_id = str(uuid.uuid4())
        storage_path = self._files.save_upload(
            data=data,
            relative=f"photos/{event_id}/{photo_id}{ext}",
        )
        photo = self._photos.create(
            event_id=event_id,
            uploader_user_id=user_id,
            storage_path=storage_path,
        )
        try:
            enqueue_photo_processing(photo.id)
        except Exception:
            # The photo is saved and recorded; the worker will simply never pick
            # it up. Log loudly so the operator notices the queue is down.
            logger.exception(
                "photo saved but not enqueued event=%s photo=%s", event_id, photo.id
            )
        logger.info("photo uploaded event=%s uploader=%s photo=%s", event_id, user_id, photo.id)
        return photo

    def _ensure_member(self, user_id: str, event_id: str) -> Event:
        event = self._events.get_by_id(event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )
        is_owner = event.owner_id == user_id
        is_attendee = self._events.is_attendee(event_id, user_id)
        if not (is_owner or is_attendee):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this event",
            )
        return event

    def list_for_event(
        self,
        user_id: str,
        event_id: str,
        *,
        offset: int = 0,
        limit: int = 24,
    ) -> tuple[list[Photo], bool]:
        """Paginated newest-first photos for an event (members only)."""
        self._ensure_member(user_id, event_id)
        return self._photos.list_for_event(event_id, offset=offset, limit=limit)

    def get_photo_file(self, user_id: str, event_id: str, photo_id: str) -> bytes:
        """Return the stored bytes of a photo (members only)."""
        # Membership check guards access to a private photo of a private event.
        self._ensure_member(user_id, event_id)
        photo = self._photos.get_by_id(photo_id)
        if photo is None or photo.event_id != event_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Photo not found",
            )
        try:
            return self._files.read(photo.storage_path)
        except FileNotFoundError:
            logger.warning("photo file missing on disk photo=%s path=%s", photo.id, photo.storage_path)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Photo file not found",
            )
