from __future__ import annotations

from pydantic import BaseModel


class ScanResponse(BaseModel):
    images_processed: int
    faces_found: int
    profile_upserted: bool = True
