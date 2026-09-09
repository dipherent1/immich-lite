from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Event(SQLModel, table=True):
    __tablename__ = "events"

    id: str = Field(default_factory=_uuid, primary_key=True, index=True)
    owner_id: str = Field(foreign_key="users.id", index=True)
    name: str
    join_token: str = Field(unique=True, index=True)
    starts_at: datetime
    expires_at: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)
