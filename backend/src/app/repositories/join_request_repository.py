from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models.join_request import JoinRequest
from app.models.user import User


class JoinRequestRepository:
    """All SQLAlchemy/SQLModel access for the join_requests table."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(self, *, event_id: str, requester_id: str) -> JoinRequest:
        """Create a pending join request. Raises ValueError on duplicate pending."""
        req = JoinRequest(event_id=event_id, requester_id=requester_id)
        self._db.add(req)
        try:
            self._db.commit()
            self._db.refresh(req)
        except IntegrityError:
            self._db.rollback()
            raise ValueError("A pending join request already exists")
        return req

    def get_by_id(self, request_id: str) -> JoinRequest | None:
        return self._db.get(JoinRequest, request_id)

    def get_pending_for_event(self, event_id: str) -> list[JoinRequest]:
        """Pending requests for an event, newest first, with requester info."""
        statement = (
            select(JoinRequest)
            .where(
                JoinRequest.event_id == event_id,
                JoinRequest.status == "pending",
            )
            .order_by(JoinRequest.created_at.desc())
        )
        return list(self._db.scalars(statement))

    def get_requester(self, request_id: str) -> User | None:
        req = self._db.get(JoinRequest, request_id)
        if req is None:
            return None
        return self._db.get(User, req.requester_id)

    def get_by_event_and_requester(
        self, event_id: str, requester_id: str
    ) -> JoinRequest | None:
        return self._db.scalars(
            select(JoinRequest).where(
                JoinRequest.event_id == event_id,
                JoinRequest.requester_id == requester_id,
                JoinRequest.status == "pending",
            )
        ).first()

    def resolve(self, request_id: str, status: str) -> JoinRequest:
        """Set status to approved/denied and record resolved_at."""
        req = self._db.get(JoinRequest, request_id)
        if req is None:
            raise FileNotFoundError(f"JoinRequest {request_id} not found")
        req.status = status
        req.resolved_at = datetime.now(timezone.utc)
        self._db.add(req)
        self._db.commit()
        self._db.refresh(req)
        return req
