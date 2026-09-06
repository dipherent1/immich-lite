from __future__ import annotations

import logging

from fastapi import HTTPException, status

from app.models.event import Event
from app.models.join_request import JoinRequest
from app.models.user import User
from app.repositories.event_repository import EventRepository
from app.repositories.join_request_repository import JoinRequestRepository
from app.services.event_service import EventService
from app.services.notification_service import NotificationService

logger = logging.getLogger("app.join_request")


class JoinRequestService:
    """Join-request lifecycle: a user requests to join an event, the owner
    approves (making them an attendee) or denies. Share links remain an instant
    join — this is the approval-gated path for search-discovered events.
    """

    def __init__(
        self,
        requests: JoinRequestRepository,
        events: EventRepository,
        notifications: NotificationService,
    ) -> None:
        self._requests = requests
        self._events = events
        self._notifications = notifications

    def request_to_join(self, requester: User, event_id: str) -> JoinRequest:
        event = self._events.get_by_id(event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )
        if not EventService.is_active(event):
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This event link is no longer active",
            )
        if self._events.is_attendee(event_id, requester.id) or event.owner_id == requester.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You are already a member of this event",
            )
        if self._requests.get_by_event_and_requester(event_id, requester.id) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have a pending join request for this event",
            )
        try:
            req = self._requests.create(event_id=event_id, requester_id=requester.id)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="You already have a pending join request for this event",
            )

        owner = self._events.get_by_id(event_id).owner_id
        self._notifications.create(
            user_id=owner,
            type="join_request",
            title="New join request",
            body=f"{requester.display_name} wants to join {event.name}",
            subject_type="event",
            subject_id=event_id,
        )
        logger.info(
            "join request created",
            extra={
                "extra_fields": {
                    "event_id": event_id,
                    "requester_id": requester.id,
                    "request_id": req.id,
                }
            },
        )
        return req

    def _get_own_event(self, owner_id: str, event_id: str) -> Event:
        event = self._events.get_by_id(event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )
        if event.owner_id != owner_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the event owner can manage join requests",
            )
        return event

    def get_requester_name(self, request_id: str) -> str | None:
        user = self._requests.get_requester(request_id)
        return user.display_name if user is not None else None

    def list_pending(self, owner_id: str, event_id: str) -> tuple[Event, list[JoinRequest]]:
        event = self._get_own_event(owner_id, event_id)
        return event, self._requests.get_pending_for_event(event_id)

    def _get_pending(self, owner_id: str, event_id: str, request_id: str) -> tuple[Event, JoinRequest]:
        event = self._get_own_event(owner_id, event_id)
        req = self._requests.get_by_id(request_id)
        if req is None or req.event_id != event_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Join request not found",
            )
        if req.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="This join request has already been resolved",
            )
        return event, req

    def approve(self, owner_id: str, event_id: str, request_id: str) -> JoinRequest:
        event, req = self._get_pending(owner_id, event_id, request_id)
        # The requester becomes an attendee; idempotent in case they already joined
        # via a share-link meanwhile.
        added = self._events.add_attendee(req.event_id, req.requester_id)
        resolved = self._requests.resolve(request_id, "approved")
        requester = self._requests.get_requester(request_id)
        if requester is not None:
            self._notifications.create(
                user_id=requester.id,
                type="join_approved",
                title="Join request approved",
                body=f"You can now access {event.name}",
                subject_type="event",
                subject_id=event.id,
            )
        logger.info(
            "join request approved",
            extra={
                "extra_fields": {
                    "request_id": request_id,
                    "event_id": event_id,
                    "added": added,
                }
            },
        )
        return resolved

    def deny(self, owner_id: str, event_id: str, request_id: str) -> JoinRequest:
        event, _req = self._get_pending(owner_id, event_id, request_id)
        resolved = self._requests.resolve(request_id, "denied")
        requester = self._requests.get_requester(request_id)
        if requester is not None:
            self._notifications.create(
                user_id=requester.id,
                type="join_denied",
                title="Join request denied",
                body=f"Your request to join {event.name} was declined",
                subject_type="event",
                subject_id=event.id,
            )
        logger.info(
            "join request denied",
            extra={"extra_fields": {"request_id": request_id, "event_id": event_id}},
        )
        return resolved
