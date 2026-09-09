from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class JoinRequestResponse(BaseModel):
    id: str
    event_id: str
    requester_id: str
    requester_name: str
    status: str
    created_at: datetime
    resolved_at: datetime | None


class JoinRequestActionResponse(BaseModel):
    request: JoinRequestResponse
    message: str
