from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class EventCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    starts_at: datetime = Field(default_factory=_utcnow)
    expires_at: datetime | None = None


class EventResponse(BaseModel):
    id: str
    name: str
    join_token: str
    starts_at: datetime
    expires_at: datetime | None
    created_at: datetime
    active: bool


class EventPublicResponse(BaseModel):
    """Details visible to anyone searching for an event.

    Deliberately excludes the private `join_token` (and, once photos exist,
    any image references) so a searcher can discover the event but not join it.
    A join-by-request flow will be added later.
    """

    id: str
    name: str
    starts_at: datetime
    expires_at: datetime | None
    created_at: datetime
    active: bool


class EventDetailResponse(EventResponse):
    attendee_count: int


class EventJoinResponse(BaseModel):
    event: EventResponse
    joined: bool
