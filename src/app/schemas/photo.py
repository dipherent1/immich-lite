from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PhotoUploadResponse(BaseModel):
    """What a client sees right after uploading a photo to an event.

    Never leaks the uploader's user id. `status` starts as `pending`; it moves to
    `processed`/`failed` once the background worker runs embedding against it.
    """

    id: str
    event_id: str
    storage_path: str
    status: str
    uploaded_at: datetime


class PhotoResponse(BaseModel):
    """A single photo as surfaced to a member of the event.

    Deliberately omits the internal `storage_path` and the uploader's id. The
    client builds the image URL from `file_url` (member-authenticated).
    """

    id: str
    event_id: str
    status: str
    uploaded_at: datetime
    file_url: str


class PhotoListResponse(BaseModel):
    """Paginated slice of an event's photos, newest first."""

    items: list[PhotoResponse]
    has_more: bool
    next_offset: int
