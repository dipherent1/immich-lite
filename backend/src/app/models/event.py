from __future__ import annotations

import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
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
    cover_photo_id: str | None = Field(
        default=None,
        sa_column=sa.Column(
            sa.String(),
            sa.ForeignKey(
                "photos.id",
                use_alter=True,
                name="fk_events_cover_photo_id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )
