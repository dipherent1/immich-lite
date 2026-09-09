from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlmodel import Field, SQLModel


def _uuid() -> str:
    return str(uuid.uuid4())


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(SQLModel, table=True):
    __tablename__ = "users"

    id: str = Field(default_factory=_uuid, primary_key=True, index=True)
    email: str = Field(unique=True, index=True)
    hashed_password: str
    display_name: str
    created_at: datetime = Field(default_factory=_utcnow)
