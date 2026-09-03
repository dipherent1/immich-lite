from __future__ import annotations

import json

from sqlmodel import Session, select

from app.models.event import Event
from app.models.photo import Photo
from app.models.photo_match import PhotoMatch


class PhotoMatchRepository:
    """All SQLModel/SQLAlchemy access for the photo_matches table."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def _find(self, photo_id: str, user_id: str) -> PhotoMatch | None:
        return self._db.scalars(
            select(PhotoMatch).where(
                PhotoMatch.photo_id == photo_id,
                PhotoMatch.user_id == user_id,
            )
        ).first()

    def upsert_best(
        self,
        *,
        photo_id: str,
        user_id: str,
        similarity: float,
        bbox: dict,
    ) -> None:
        """Record a photo->user match, keeping the best similarity.

        The unique constraint on (photo_id, user_id) guarantees one row per pair;
        a face can appear several times in a photo, so when a later face scores
        higher we update instead of adding a duplicate row.
        """
        existing = self._find(photo_id, user_id)
        if existing is not None:
            if similarity > existing.similarity:
                existing.similarity = similarity
                existing.bbox = json.dumps(bbox)
                self._db.add(existing)
                self._db.commit()
            return
        self._db.add(
            PhotoMatch(
                photo_id=photo_id,
                user_id=user_id,
                similarity=similarity,
                bbox=json.dumps(bbox),
            )
        )
        self._db.commit()

    def list_for_user(
        self,
        user_id: str,
        *,
        offset: int = 0,
        limit: int = 24,
    ) -> tuple[list[PhotoMatch], bool]:
        """A user's matches across all their events, newest first."""
        rows = list(
            self._db.scalars(
                select(PhotoMatch)
                .where(PhotoMatch.user_id == user_id)
                .order_by(PhotoMatch.created_at.desc())
                .offset(offset)
                .limit(limit + 1)
            )
        )
        has_more = len(rows) > limit
        return rows[:limit], has_more

    def list_feed_for_user(
        self,
        user_id: str,
        *,
        offset: int = 0,
        limit: int = 24,
    ) -> tuple[list[tuple[PhotoMatch, Event]], bool]:
        """A user's match feed (match + its event) newest first, 1 query per page.

        Joins PhotoMatch -> Photo -> Event so the endpoint has the photo's
        `event_id` and the event's `name` for `file_url`/display without N+1.
        """
        statement = (
            select(PhotoMatch, Event)
            .join(Photo, Photo.id == PhotoMatch.photo_id)
            .join(Event, Event.id == Photo.event_id)
            .where(PhotoMatch.user_id == user_id)
            .order_by(PhotoMatch.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )
        result = self._db.execute(statement)
        rows = [tuple(row) for row in result.all()]
        has_more = len(rows) > limit
        return rows[:limit], has_more
