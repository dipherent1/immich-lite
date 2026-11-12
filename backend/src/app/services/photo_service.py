from __future__ import annotations

import io
import logging
import tempfile
import uuid
import zipfile
from pathlib import Path, PurePath

from fastapi import HTTPException, status

from app.core.file_storage import LocalFileService
from app.core.jobs import enqueue_photo_processing
from app.models.event import Event
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
MAX_BATCH_FILES = 100  # photos accepted per batch-upload request

# What a browser <img> can render as-is, with its media type. Anything else
# (HEIC/HEIF from phones, TIFF, ...) is converted to JPEG for display.
_BROWSER_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".avif": "image/avif",
    ".bmp": "image/bmp",
}
_PREVIEW_MAX_PX = 2048


def _to_preview_jpeg(data: bytes) -> bytes:
    """Decode any supported image (incl. HEIC) to an upright, display-sized JPEG."""
    from PIL import Image, ImageOps
    from pillow_heif import register_heif_opener

    register_heif_opener()
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((_PREVIEW_MAX_PX, _PREVIEW_MAX_PX))
        out = io.BytesIO()
        img.save(out, "JPEG", quality=85)
        return out.getvalue()


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

    def _store_and_enqueue(
        self, user_id: str, event_id: str, filename: str, data: bytes
    ) -> Photo:
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
        return photo

    def _ensure_can_upload(self, user_id: str, event_id: str) -> None:
        """Only an owner/attendee may upload, and only while the event is active."""
        event = self._events.get_by_id(event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )
        self._ensure_member(user_id, event_id)
        if not EventService.is_active(event):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This event is no longer active",
            )

    def upload(self, user_id: str, event_id: str, filename: str, data: bytes) -> Photo:
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Photo exceeds the 20 MB upload limit",
            )

        self._ensure_can_upload(user_id, event_id)
        photo = self._store_and_enqueue(user_id, event_id, filename, data)
        # Default the event cover image to the first uploaded photo.
        self._events.set_cover_photo_if_unset(event_id, photo.id)
        logger.info("photo uploaded event=%s uploader=%s photo=%s", event_id, user_id, photo.id)
        return photo

    def upload_many(
        self, user_id: str, event_id: str, files: list[tuple[str, bytes]]
    ) -> list[tuple[str, Photo | None, str | None]]:
        """Upload up to MAX_BATCH_FILES photos in one call.

        Access is checked once for the whole batch (a failure there fails the
        request). After that each file succeeds or fails on its own — a bad file
        type or an oversized photo never discards the rest. Returns
        (filename, photo-or-None, error-or-None) per input, in order.
        """
        if len(files) > MAX_BATCH_FILES:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"At most {MAX_BATCH_FILES} photos per batch",
            )
        self._ensure_can_upload(user_id, event_id)

        results: list[tuple[str, Photo | None, str | None]] = []
        first: Photo | None = None
        for filename, data in files:
            if len(data) > MAX_UPLOAD_BYTES:
                results.append((filename, None, "Exceeds the 20 MB limit"))
                continue
            try:
                photo = self._store_and_enqueue(user_id, event_id, filename, data)
            except HTTPException as exc:
                results.append((filename, None, str(exc.detail)))
                continue
            except Exception:
                logger.exception("batch upload failed event=%s file=%s", event_id, filename)
                results.append((filename, None, "Could not save this photo"))
                continue
            first = first or photo
            results.append((filename, photo, None))

        if first is not None:
            self._events.set_cover_photo_if_unset(event_id, first.id)
        logger.info(
            "batch upload event=%s uploader=%s ok=%d failed=%d",
            event_id,
            user_id,
            sum(1 for _, p, _ in results if p),
            sum(1 for _, p, _ in results if not p),
        )
        return results

    def _ensure_owner(self, user_id: str, event_id: str) -> Event:
        event = self._events.get_by_id(event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )
        if event.owner_id != user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the event creator can edit the cover image",
            )
        return event

    def set_cover_photo(self, user_id: str, event_id: str, photo_id: str) -> Event:
        """Select an existing event photo as the event's cover image (creator only)."""
        self._ensure_owner(user_id, event_id)
        photo = self._photos.get_by_id(photo_id)
        if photo is None or photo.event_id != event_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Photo not found",
            )
        updated = self._events.set_cover_photo(event_id, photo.id)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )
        logger.info("event cover updated event=%s photo=%s owner=%s", event_id, photo.id, user_id)
        return updated

    def upload_cover(self, user_id: str, event_id: str, filename: str, data: bytes) -> Event:
        """Upload a new image and set it as the event's cover image (creator only)."""
        if len(data) > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Photo exceeds the 20 MB upload limit",
            )
        self._ensure_owner(user_id, event_id)
        photo = self._store_and_enqueue(user_id, event_id, filename, data)
        updated = self._events.set_cover_photo(event_id, photo.id)
        if updated is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )
        logger.info("event cover uploaded event=%s photo=%s owner=%s", event_id, photo.id, user_id)
        return updated

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

    def _get_event_photo(self, user_id: str, event_id: str, photo_id: str) -> Photo:
        # Membership check guards access to a private photo of a private event.
        self._ensure_member(user_id, event_id)
        photo = self._photos.get_by_id(photo_id)
        if photo is None or photo.event_id != event_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Photo not found",
            )
        return photo

    def get_photo_file(
        self, user_id: str, event_id: str, photo_id: str
    ) -> tuple[bytes, str]:
        """Bytes + media type of a photo, ready for an <img> (members only).

        Web-friendly formats are served untouched with their real media type.
        Others (HEIC from phones, TIFF, ...) are converted to a JPEG preview once
        and cached on disk, so later views are plain file reads.
        """
        photo = self._get_event_photo(user_id, event_id, photo_id)
        ext = PurePath(photo.storage_path).suffix.lower()
        try:
            if ext in _BROWSER_MIME:
                return self._files.read(photo.storage_path), _BROWSER_MIME[ext]

            preview_path = f"previews/{event_id}/{photo.id}.jpg"
            try:
                return self._files.read(preview_path), "image/jpeg"
            except FileNotFoundError:
                pass
            preview = _to_preview_jpeg(self._files.read(photo.storage_path))
            self._files.save_upload(data=preview, relative=preview_path)
            return preview, "image/jpeg"
        except FileNotFoundError:
            logger.warning("photo file missing on disk photo=%s path=%s", photo.id, photo.storage_path)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Photo file not found",
            )
        except HTTPException:
            raise
        except Exception:
            logger.exception("could not decode photo for display photo=%s", photo.id)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="This photo can't be previewed",
            )

    def build_zip(
        self, user_id: str, event_id: str, photo_ids: list[str] | None
    ) -> Path:
        """Zip the originals of an event's photos (all, or just `photo_ids`).

        Written to a temp file (not memory) so large events don't balloon RAM;
        the caller must delete the returned path once it has been sent. Images
        are already compressed, so entries are stored, not deflated.
        """
        self._ensure_member(user_id, event_id)
        photos = self._photos.list_all_for_event(event_id, photo_ids)
        if not photos:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="No photos to download",
            )

        tmp = tempfile.NamedTemporaryFile(suffix=".zip", delete=False)
        tmp.close()
        added = 0
        try:
            with zipfile.ZipFile(tmp.name, "w", compression=zipfile.ZIP_STORED) as zf:
                for i, photo in enumerate(photos, start=1):
                    ext = PurePath(photo.storage_path).suffix.lower() or ".jpg"
                    try:
                        zf.write(self._files.abs_path(photo.storage_path), f"photo-{i:04d}{ext}")
                        added += 1
                    except FileNotFoundError:
                        logger.warning("zip: file missing photo=%s", photo.id)
            if added == 0:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No photo files found",
                )
        except BaseException:
            Path(tmp.name).unlink(missing_ok=True)
            raise
        logger.info("zip built event=%s user=%s photos=%d", event_id, user_id, added)
        return Path(tmp.name)
