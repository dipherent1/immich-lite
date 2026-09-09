from __future__ import annotations

from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventAttendee(SQLModel, table=True):
    __tablename__ = "event_attendees"

    event_id: str = Field(foreign_key="events.id", primary_key=True)
    user_id: str = Field(foreign_key="users.id", primary_key=True)
    joined_at: datetime = Field(default_factory=_utcnow)
