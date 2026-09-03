from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class PhotoMatch(SQLModel, table=True):
    """A face in a photo matched to an attendee of the same event.

    One row per (photo, user) pair — a single photo matched to a person yields
    exactly one row no matter how many of that person's faces appear in it. The
    unique constraint on `(photo_id, user_id)` enforces this; when a photo is
    re-processed the larger similarity wins (see `PhotoMatchRepository`).

    `bbox` is the face's bounding box as a JSON object string, serialized from
    the Qdrant `event_faces` point that produced this match.
    """

    __tablename__ = "photo_matches"

    id: str = Field(default_factory=_uuid, primary_key=True, index=True)
    photo_id: str = Field(foreign_key="photos.id", index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    similarity: float
    bbox: str  # JSON object string, e.g. '{"x1":..,"y1":..,"x2":..,"y2":..}'
    created_at: datetime = Field(default_factory=_utcnow)

    @property
    def bbox_dict(self) -> dict:
        try:
            return json.loads(self.bbox)
        except (TypeError, ValueError):
            return {}
