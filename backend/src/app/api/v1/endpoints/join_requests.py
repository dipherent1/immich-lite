from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.api.deps import get_current_user, get_join_request_service
from app.models.user import User
from app.schemas.join_request import JoinRequestActionResponse, JoinRequestResponse
from app.services.join_request_service import JoinRequestService

router = APIRouter(prefix="/events", tags=["join-requests"])


def _to_response(req, requester_name: str) -> JoinRequestResponse:
    return JoinRequestResponse(
        id=req.id,
        event_id=req.event_id,
        requester_id=req.requester_id,
        requester_name=requester_name,
        status=req.status,
        created_at=req.created_at,
        resolved_at=req.resolved_at,
    )


@router.post(
    "/{event_id}/join-request",
    response_model=JoinRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
def request_to_join(
    event_id: str,
    current_user: User = Depends(get_current_user),
    service: JoinRequestService = Depends(get_join_request_service),
) -> JoinRequestResponse:
    req = service.request_to_join(current_user, event_id)
    return _to_response(req, current_user.display_name)


@router.get(
    "/{event_id}/join-requests",
    response_model=list[JoinRequestResponse],
    status_code=status.HTTP_200_OK,
)
def list_pending_requests(
    event_id: str,
    current_user: User = Depends(get_current_user),
    service: JoinRequestService = Depends(get_join_request_service),
) -> list[JoinRequestResponse]:
    _event, requests = service.list_pending(current_user.id, event_id)
    return [
        _to_response(req, (service.get_requester_name(req.id) or "Unknown"))
        for req in requests
    ]


@router.patch(
    "/{event_id}/join-requests/{request_id}/approve",
    response_model=JoinRequestActionResponse,
    status_code=status.HTTP_200_OK,
)
def approve_request(
    event_id: str,
    request_id: str,
    current_user: User = Depends(get_current_user),
    service: JoinRequestService = Depends(get_join_request_service),
) -> JoinRequestActionResponse:
    req = service.approve(current_user.id, event_id, request_id)
    return JoinRequestActionResponse(
        request=_to_response(req, service.get_requester_name(req.id) or "Unknown"),
        message="Join request approved",
    )


@router.patch(
    "/{event_id}/join-requests/{request_id}/deny",
    response_model=JoinRequestActionResponse,
    status_code=status.HTTP_200_OK,
)
def deny_request(
    event_id: str,
    request_id: str,
    current_user: User = Depends(get_current_user),
    service: JoinRequestService = Depends(get_join_request_service),
) -> JoinRequestActionResponse:
    req = service.deny(current_user.id, event_id, request_id)
    return JoinRequestActionResponse(
        request=_to_response(req, service.get_requester_name(req.id) or "Unknown"),
        message="Join request denied",
    )
