from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Photo(SQLModel, table=True):
    __tablename__ = "photos"

    id: str = Field(default_factory=_uuid, primary_key=True, index=True)
    event_id: str = Field(foreign_key="events.id", index=True)
    uploader_user_id: str = Field(foreign_key="users.id", index=True)

    # Relative path under the storage root (e.g. "photos/{event}/{photo_id}.jpg").
    # The matching/recipient code always references this same path — never copies it.
    storage_path: str

    # status: pending / processed / failed
    status: str = Field(default="pending")
    uploaded_at: datetime = Field(default_factory=_utcnow)
    processed_at: datetime | None = None
