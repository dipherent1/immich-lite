from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.core.file_storage import LocalFileService
from app.models.event import Event
from app.models.photo import Photo
from app.repositories.event_repository import EventRepository
from app.repositories.photo_repository import PhotoRepository
from app.services.event_service import EventService
from app.services.photo_service import _to_preview_jpeg

logger = logging.getLogger("app.public")

# Longest side of the previews served without an account. Originals are never
# served here, so downloading full quality needs an account.
PUBLIC_PREVIEW_PX = 800


class PublicEventService:
    """Read-only access to an event's photos for anyone holding its share link.

    The join token is the credential (128 random bits), so no session or account
    is involved. Only `processed` photos are visible, only as downscaled JPEG
    previews, and only while the event is active (same rule as joining).
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

    def _event_for_token(self, join_token: str) -> Event:
        event = self._events.get_by_token(join_token)
        if event is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Event not found")
        if not EventService.is_active(event):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This event has ended",
            )
        return event

    def event_view(self, join_token: str) -> tuple[Event, int]:
        event = self._event_for_token(join_token)
        return event, self._photos.count_for_event(event.id, status="processed")

    def list_photos(
        self, join_token: str, *, offset: int = 0, limit: int = 24
    ) -> tuple[list[Photo], bool]:
        event = self._event_for_token(join_token)
        return self._photos.list_for_event(
            event.id, offset=offset, limit=limit, status="processed"
        )

    def preview(self, join_token: str, photo_id: str) -> bytes:
        """JPEG preview (longest side <= PUBLIC_PREVIEW_PX) of one processed photo
        of this event. Generated once, then cached under the event's preview
        directory, which event expiry deletes along with everything else."""
        event = self._event_for_token(join_token)
        photo = self._photos.get_by_id(photo_id)
        if photo is None or photo.event_id != event.id or photo.status != "processed":
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")

        cache_path = f"previews/{event.id}/public-{photo.id}.jpg"
        try:
            return self._files.read(cache_path)
        except FileNotFoundError:
            pass
        try:
            preview = _to_preview_jpeg(self._files.read(photo.storage_path), PUBLIC_PREVIEW_PX)
        except FileNotFoundError:
            logger.warning("public preview: file missing photo=%s", photo.id)
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Photo not found")
        except Exception:
            logger.exception("public preview: could not decode photo=%s", photo.id)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This photo can't be previewed",
            )
        self._files.save_upload(data=preview, relative=cache_path)
        return preview
