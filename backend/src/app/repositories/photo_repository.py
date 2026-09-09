from __future__ import annotations

from sqlmodel import Session, select

from app.models.photo import Photo


class PhotoRepository:
    """All SQLModel/SQLAlchemy access for the photos table."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        event_id: str,
        uploader_user_id: str,
        storage_path: str,
    ) -> Photo:
        photo = Photo(
            event_id=event_id,
            uploader_user_id=uploader_user_id,
            storage_path=storage_path,
            status="pending",
        )
        self._db.add(photo)
        self._db.commit()
        self._db.refresh(photo)
        return photo

    def get_by_id(self, photo_id: str) -> Photo | None:
        return self._db.get(Photo, photo_id)

    def set_status(self, photo_id: str, status: str, *, processed: bool = False) -> None:
        photo = self._db.get(Photo, photo_id)
        if photo is None:
            return
        photo.status = status
        if processed:
            from datetime import datetime, timezone

            photo.processed_at = datetime.now(timezone.utc)
        self._db.add(photo)
        self._db.commit()

    def list_pending(self, limit: int = 100) -> list[Photo]:
        return list(
            self._db.scalars(
                select(Photo).where(Photo.status == "pending").order_by(Photo.uploaded_at).limit(limit)
            )
        )

    def list_for_event(
        self,
        event_id: str,
        *,
        offset: int = 0,
        limit: int = 24,
    ) -> tuple[list[Photo], bool]:
        """Paginated list for an event, newest first.

        Returns (photos, has_more). `limit + 1` is fetched so the caller can tell
        whether another page exists without a separate count query.
        """
        rows = list(
            self._db.scalars(
                select(Photo)
                .where(Photo.event_id == event_id)
                .order_by(Photo.uploaded_at.desc())
                .offset(offset)
                .limit(limit + 1)
            )
        )
        has_more = len(rows) > limit
        return rows[:limit], has_more
