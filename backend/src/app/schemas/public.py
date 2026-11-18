from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PublicEventView(BaseModel):
    """What anyone holding an event's share link may see about it.

    Deliberately minimal: no ids, no owner, no join token, no attendee list.
    `photo_count` counts only photos that finished processing.
    """

    name: str
    expires_at: datetime | None
    photo_count: int


class PublicPhoto(BaseModel):
    """A photo visible through the public view (opaque id, nothing else)."""

    id: str


class PublicPhotoList(BaseModel):
    items: list[PublicPhoto]
    has_more: bool
    next_offset: int
