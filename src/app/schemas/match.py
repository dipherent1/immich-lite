from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class MatchFeedItemResponse(BaseModel):
    """One matched photo in the current user's delivery feed.

    `file_url` points at the existing authenticating photo endpoint
    (`/api/v1/events/{event_id}/photos/{photo_id}/file`) — matching reuses the
    same delivery path, it never duplicates the stored image.
    """

    photo_id: str
    event_id: str
    event_name: str
    similarity: float
    bbox: dict
    file_url: str
    created_at: datetime


class MatchFeedResponse(BaseModel):
    """Paginated slice of a user's matched-photo feed, newest first."""

    items: list[MatchFeedItemResponse]
    has_more: bool
    next_offset: int
