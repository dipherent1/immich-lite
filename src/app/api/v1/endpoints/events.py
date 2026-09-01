from __future__ import annotations

from fastapi import APIRouter, Depends, File, Query, Response, UploadFile, status

from app.api.deps import get_current_user, get_event_service, get_photo_service
from app.models.event import Event
from app.models.user import User
from app.schemas.event import (
    EventCreate,
    EventDetailResponse,
    EventJoinResponse,
    EventPublicResponse,
    EventResponse,
)
from app.schemas.photo import PhotoListResponse, PhotoResponse, PhotoUploadResponse
from app.services.event_service import EventService
from app.services.photo_service import PhotoService

router = APIRouter(prefix="/events", tags=["events"])


def _to_response(event: Event) -> EventResponse:
    return EventResponse(
        id=event.id,
        name=event.name,
        join_token=event.join_token,
        starts_at=event.starts_at,
        expires_at=event.expires_at,
        created_at=event.created_at,
        active=EventService.is_active(event),
    )


def _to_public_response(event: Event) -> EventPublicResponse:
    # Public view: no join_token (and no image refs once photos ship in Phase 4).
    return EventPublicResponse(
        id=event.id,
        name=event.name,
        starts_at=event.starts_at,
        expires_at=event.expires_at,
        created_at=event.created_at,
        active=EventService.is_active(event),
    )


@router.post("", response_model=EventResponse, status_code=status.HTTP_201_CREATED)
def create_event(
    payload: EventCreate,
    current_user: User = Depends(get_current_user),
    service: EventService = Depends(get_event_service),
) -> EventResponse:
    event = service.create(current_user, payload)
    return _to_response(event)


@router.get("", response_model=list[EventResponse], status_code=status.HTTP_200_OK)
def list_my_events(
    current_user: User = Depends(get_current_user),
    service: EventService = Depends(get_event_service),
) -> list[EventResponse]:
    return [_to_response(event) for event in service.list_for_user(current_user.id)]


@router.get("/search", response_model=list[EventPublicResponse], status_code=status.HTTP_200_OK)
def search_events(
    q: str = Query(..., min_length=1, description="Partial name to search for"),
    current_user: User = Depends(get_current_user),
    service: EventService = Depends(get_event_service),
) -> list[EventPublicResponse]:
    return [_to_public_response(event) for event in service.search(q)]


@router.get("/join/{join_token}", response_model=EventJoinResponse, status_code=status.HTTP_200_OK)
def join_event(
    join_token: str,
    current_user: User = Depends(get_current_user),
    service: EventService = Depends(get_event_service),
) -> EventJoinResponse:
    event, added = service.join(current_user.id, join_token)
    return EventJoinResponse(event=_to_response(event), joined=added)


@router.get("/{event_id}", response_model=EventDetailResponse, status_code=status.HTTP_200_OK)
def get_event(
    event_id: str,
    current_user: User = Depends(get_current_user),
    service: EventService = Depends(get_event_service),
) -> EventDetailResponse:
    event, attendee_count = service.get_by_id(current_user.id, event_id)
    return EventDetailResponse(
        **_to_response(event).model_dump(),
        attendee_count=attendee_count,
    )


@router.post(
    "/{event_id}/photos",
    response_model=PhotoUploadResponse,
    status_code=status.HTTP_201_CREATED,
)
def upload_photo(
    event_id: str,
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    service: PhotoService = Depends(get_photo_service),
) -> PhotoUploadResponse:
    photo = service.upload(current_user.id, event_id, file.filename or "photo", file.file.read())
    return PhotoUploadResponse(
        id=photo.id,
        event_id=photo.event_id,
        storage_path=photo.storage_path,
        status=photo.status,
        uploaded_at=photo.uploaded_at,
    )


@router.get(
    "/{event_id}/photos",
    response_model=PhotoListResponse,
    status_code=status.HTTP_200_OK,
)
def list_event_photos(
    event_id: str,
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: PhotoService = Depends(get_photo_service),
) -> PhotoListResponse:
    photos, has_more = service.list_for_event(current_user.id, event_id, offset=offset, limit=limit)
    items = [
        PhotoResponse(
            id=p.id,
            event_id=p.event_id,
            status=p.status,
            uploaded_at=p.uploaded_at,
            file_url=f"/api/v1/events/{event_id}/photos/{p.id}/file",
        )
        for p in photos
    ]
    return PhotoListResponse(items=items, has_more=has_more, next_offset=offset + len(photos))


@router.get(
    "/{event_id}/photos/{photo_id}/file",
    status_code=status.HTTP_200_OK,
)
def get_event_photo_file(
    event_id: str,
    photo_id: str,
    current_user: User = Depends(get_current_user),
    service: PhotoService = Depends(get_photo_service),
) -> Response:
    data = service.get_photo_file(current_user.id, event_id, photo_id)
    return Response(content=data, media_type="image/jpeg")
