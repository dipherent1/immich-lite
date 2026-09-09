from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_user, get_matching_service
from app.models.user import User
from app.schemas.match import MatchFeedItemResponse, MatchFeedResponse
from app.services.matching_service import MatchingService

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("/me", response_model=MatchFeedResponse, status_code=status.HTTP_200_OK)
def my_matches(
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: MatchingService = Depends(get_matching_service),
) -> MatchFeedResponse:
    """The current user's matched-photo feed across all events they attended,
    newest first."""
    rows, has_more = service.feed(current_user.id, offset=offset, limit=limit)
    items = [
        MatchFeedItemResponse(
            photo_id=match.photo_id,
            event_id=event.id,
            event_name=event.name,
            similarity=match.similarity,
            bbox=match.bbox_dict,
            file_url=f"/api/v1/events/{event.id}/photos/{match.photo_id}/file",
            created_at=match.created_at,
        )
        for match, event in rows
    ]
    return MatchFeedResponse(items=items, has_more=has_more, next_offset=offset + len(items))
