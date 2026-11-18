"""Public (no login) view of an event, addressed by its share-link token.

These routes are unauthenticated by design: the join token is the credential, so
nothing here accepts an event id, a user id, or a session. They expose only
processed photos as small previews and never the originals. They have their own
per-IP limit because previews are CPU work an anonymous caller can trigger.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Request, Response, status

from app.api.deps import get_public_event_service
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.schemas.public import PublicEventView, PublicPhoto, PublicPhotoList
from app.services.public_event_service import PublicEventService

router = APIRouter(prefix="/public/events", tags=["public"])

_public_limit = get_settings().rate_limit_public


@router.get("/{join_token}", response_model=PublicEventView, status_code=status.HTTP_200_OK)
@limiter.limit(_public_limit)
def get_public_event(
    request: Request,
    join_token: str,
    service: PublicEventService = Depends(get_public_event_service),
) -> PublicEventView:
    event, photo_count = service.event_view(join_token)
    return PublicEventView(name=event.name, expires_at=event.expires_at, photo_count=photo_count)


@router.get(
    "/{join_token}/photos",
    response_model=PublicPhotoList,
    status_code=status.HTTP_200_OK,
)
@limiter.limit(_public_limit)
def list_public_photos(
    request: Request,
    join_token: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    service: PublicEventService = Depends(get_public_event_service),
) -> PublicPhotoList:
    photos, has_more = service.list_photos(join_token, offset=offset, limit=limit)
    return PublicPhotoList(
        items=[PublicPhoto(id=p.id) for p in photos],
        has_more=has_more,
        next_offset=offset + len(photos),
    )


@router.get("/{join_token}/photos/{photo_id}/preview", status_code=status.HTTP_200_OK)
@limiter.limit(_public_limit)
def get_public_photo_preview(
    request: Request,
    join_token: str,
    photo_id: str,
    service: PublicEventService = Depends(get_public_event_service),
) -> Response:
    data = service.preview(join_token, photo_id)
    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "private, max-age=3600"},
    )
