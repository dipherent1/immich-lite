import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials

from app.api.deps import (
    bearer_scheme,
    get_current_user,
    get_notification_service,
    get_user_service,
)
from app.core.security import decode_access_token
from app.models.user import User
from app.schemas.notification import (
    NotificationListResponse,
    NotificationResponse,
    UnreadCountResponse,
)
from app.services.notification_service import NotificationService
from app.services.user_service import UserService

router = APIRouter(prefix="/notifications", tags=["notifications"])


def _to_response(n) -> NotificationResponse:
    return NotificationResponse(
        id=n.id,
        type=n.type,
        title=n.title,
        body=n.body,
        subject_type=n.subject_type,
        subject_id=n.subject_id,
        is_read=n.is_read,
        created_at=n.created_at,
    )


async def _user_from_header_or_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    token: str | None = Query(None, description="JWT (SSE convenience)"),
    service: UserService = Depends(get_user_service),
) -> User:
    """Resolve the authenticated user from the bearer header or a `token` query
    param. EventSource can't set an Authorization header, so the SSE stream
    passes the JWT as a query param; the header takes precedence when present."""
    raw = credentials.credentials if credentials is not None else token
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    subject = decode_access_token(raw)
    if subject is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
    user = service.get_by_id(subject)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Unknown user")
    return user


@router.get(
    "/stream",
    status_code=status.HTTP_200_OK,
    response_class=StreamingResponse,
)
async def stream_notifications(
    current_user: User = Depends(_user_from_header_or_token),
) -> StreamingResponse:
    """Server-Sent Events stream of new notifications for the current user.

    The connection stays open; each notification arrives as an
    `event: notification` message. Periodic `: keepalive` comments prevent
    proxies from timing the connection out.
    """
    from app.core.sse import sse_manager

    user_id = str(current_user.id)
    queue: asyncio.Queue = asyncio.Queue()
    sse_manager.add_client(user_id, queue)

    async def event_stream():
        import json

        try:
            while True:
                try:
                    payload = await asyncio.wait_for(queue.get(), timeout=15)
                    yield f"event: notification\ndata: {json.dumps(payload)}\n\n"
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            sse_manager.remove_client(user_id, queue)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("", response_model=NotificationListResponse, status_code=status.HTTP_200_OK)
def list_notifications(
    offset: int = Query(0, ge=0),
    limit: int = Query(24, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationListResponse:
    items, has_more = service.list_for_user(current_user.id, offset=offset, limit=limit)
    return NotificationListResponse(
        items=[_to_response(n) for n in items],
        has_more=has_more,
        next_offset=offset + len(items),
    )


@router.get(
    "/unread-count",
    response_model=UnreadCountResponse,
    status_code=status.HTTP_200_OK,
)
def unread_count(
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> UnreadCountResponse:
    return UnreadCountResponse(count=service.unread_count(current_user.id))


@router.patch(
    "/{notification_id}/read",
    response_model=NotificationResponse,
    status_code=status.HTTP_200_OK,
)
def mark_notification_read(
    notification_id: str,
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> NotificationResponse:
    notif = service.get_by_id(notification_id, current_user.id)
    if notif is None:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail="Notification not found")
    service.mark_read(notification_id, current_user.id)
    return _to_response(notif)


@router.patch("/read-all", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_notifications_read(
    current_user: User = Depends(get_current_user),
    service: NotificationService = Depends(get_notification_service),
) -> None:
    service.mark_all_read(current_user.id)
