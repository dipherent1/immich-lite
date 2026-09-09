from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class JoinRequest(SQLModel, table=True):
    """A request from a user to join an event (created via search, not share link).

    Status lifecycle: pending → approved | denied.
    Approved → an EventAttendee row is created for the requester.
    """

    __tablename__ = "join_requests"

    id: str = Field(default_factory=_uuid, primary_key=True, index=True)
    event_id: str = Field(foreign_key="events.id", index=True)
    requester_id: str = Field(foreign_key="users.id", index=True)
    status: str = Field(default="pending")  # pending | approved | denied
    created_at: datetime = Field(default_factory=_utcnow)
    resolved_at: datetime | None = None
