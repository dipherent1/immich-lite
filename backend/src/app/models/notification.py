from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Notification(SQLModel, table=True):
    """An in-app notification for a user.

    Types:
      - join_request:   someone requested to join your event
      - join_approved:  your join request was approved
      - join_denied:    your join request was denied
      - photo_matched:  a photo in an event you attend matches your face
      - photo_processed: a photo you uploaded finished processing

    subject_type + subject_id let the frontend navigate to the relevant entity
    (e.g. "event" + event_id → /events/{id}).
    """

    __tablename__ = "notifications"

    id: str = Field(default_factory=_uuid, primary_key=True, index=True)
    user_id: str = Field(foreign_key="users.id", index=True)
    type: str = Field(index=True)
    title: str
    body: str
    subject_type: str | None = None  # "event" | "photo" | "join_request"
    subject_id: str | None = None
    is_read: bool = Field(default=False)
    created_at: datetime = Field(default_factory=_utcnow)
