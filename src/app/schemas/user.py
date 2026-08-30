from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class UserResponse(BaseModel):
    email: str
    display_name: str
    created_at: datetime
    has_face_profile: bool = False
