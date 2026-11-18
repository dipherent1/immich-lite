from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status

from app.api.deps import get_current_user, get_matching_service
from app.models.user import User
from app.schemas.match import (
    MatchEventListResponse,
    MatchEventResponse,
    MatchFeedItemResponse,
    MatchFeedResponse,
)
from app.services.matching_service import MatchingService

router = APIRouter(prefix="/matches", tags=["matches"])


@router.get("/me", response_model=MatchFeedResponse, status_code=status.HTTP_200_OK)
def my_matches(
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    event_id: str | None = Query(None),
    current_user: User = Depends(get_current_user),
    service: MatchingService = Depends(get_matching_service),
) -> MatchFeedResponse:
    """The current user's matched-photo feed, newest first. Pass `event_id` to
    see just one event's photos (an album)."""
    rows, has_more = service.feed(
        current_user.id, offset=offset, limit=limit, event_id=event_id
    )
    items = [
        MatchFeedItemResponse(
            photo_id=match.photo_id,
            event_id=event.id,
            event_name=event.name,
            event_expires_at=event.expires_at,
            similarity=match.similarity,
            bbox=match.bbox_dict,
            file_url=f"/api/v1/events/{event.id}/photos/{match.photo_id}/file",
            created_at=match.created_at,
        )
        for match, event in rows
    ]
    return MatchFeedResponse(items=items, has_more=has_more, next_offset=offset + len(items))


@router.get("/me/events", response_model=MatchEventListResponse, status_code=status.HTTP_200_OK)
def my_match_events(
    current_user: User = Depends(get_current_user),
    service: MatchingService = Depends(get_matching_service),
) -> MatchEventListResponse:
    """The current user's photo "albums": events they have matched photos in,
    newest event first, each with a photo count and cover photo."""
    return MatchEventListResponse(
        items=[
            MatchEventResponse(
                event_id=event.id,
                event_name=event.name,
                event_expires_at=event.expires_at,
                photo_count=count,
                cover_photo_id=cover,
            )
            for event, count, cover in service.event_summaries(current_user.id)
        ]
    )
