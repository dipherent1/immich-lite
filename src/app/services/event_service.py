from __future__ import annotations

import logging
import secrets
from datetime import datetime, timezone

from fastapi import HTTPException, status

from app.models.event import Event
from app.models.user import User
from app.repositories.event_repository import EventRepository
from app.schemas.event import EventCreate
from app.services.profile_service import ProfileService

logger = logging.getLogger("app.event")

_TOKEN_BYTES = 16


class EventService:
    """Event lifecycle: creation, join-by-link, and detail/attendee lookup.

    "Active" rule (time window, the simplest option): an event is joinable when
    `starts_at <= now` and either its `expires_at` is null (never expires, e.g.
    left open by the owner) or `now <= expires_at`. Out of scope this phase is
    any owner-toggled `is_open` boolean.
    """

    def __init__(self, repository: EventRepository, profiles: ProfileService) -> None:
        self._repository = repository
        self._profiles = profiles

    @staticmethod
    def _naive_utc(dt: datetime) -> datetime:
        if dt.tzinfo is not None:
            return dt.astimezone(timezone.utc).replace(tzinfo=None)
        return dt

    @classmethod
    def is_active(cls, event: Event, now: datetime | None = None) -> bool:
        # The events columns are `timestamp without time zone` (naive). The app
        # stores UTC wall-clock values, so compare everything in naive UTC.
        now = cls._naive_utc(now or datetime.now(timezone.utc))
        if now < event.starts_at:
            return False
        if event.expires_at is not None and now > event.expires_at:
            return False
        return True

    def generate_join_token(self) -> str:
        # Random slug, unique per event (verified at insert time by the unique index).
        return secrets.token_urlsafe(_TOKEN_BYTES)

    def create(self, owner: User, payload: EventCreate) -> Event:
        # Every event needs the owner's permanent face vector so Phase 5 can match.
        if not self._profiles.has_profile(owner.id):
            logger.info("event create rejected, owner has no face profile id=%s", owner.id)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="You must scan your face profile before creating an event",
            )

        starts_at = self._naive_utc(payload.starts_at)
        expires_at = None
        if payload.expires_at is not None:
            expires_at = self._naive_utc(payload.expires_at)
        if expires_at is not None and expires_at <= starts_at:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="expires_at must be after starts_at",
            )

        event = self._repository.create_event(
            owner_id=owner.id,
            name=payload.name,
            join_token=self.generate_join_token(),
            starts_at=starts_at,
            expires_at=expires_at,
        )
        # The owner joins as an attendee implicitly.
        self._repository.add_attendee(event.id, owner.id)
        logger.info("event created id=%s owner=%s name=%s", event.id, owner.id, event.name)
        return event

    def join(self, user_id: str, join_token: str) -> tuple[Event, bool]:
        event = self._repository.get_by_token(join_token)
        if event is None:
            logger.info("join failed, unknown token for user=%s", user_id)
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )
        if not self.is_active(event):
            logger.info("join rejected, event inactive id=%s user=%s", event.id, user_id)
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="This event link is no longer active",
            )
        added = self._repository.add_attendee(event.id, user_id)
        logger.info("user joined event id=%s user=%s (new=%s)", event.id, user_id, added)
        return event, added

    def get_by_id(self, user_id: str, event_id: str) -> tuple[Event, int]:
        event = self._repository.get_by_id(event_id)
        if event is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Event not found",
            )
        # Only the owner or an attendee may view the event.
        is_owner = event.owner_id == user_id
        is_attendee = self._repository.is_attendee(event.id, user_id)
        if not (is_owner or is_attendee):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You are not a member of this event",
            )
        return event, self._repository.attendee_count(event.id)

    def search(self, name: str) -> list[Event]:
        return self._repository.search_by_name(name)

    def list_for_user(self, user_id: str) -> list[Event]:
        return self._repository.list_for_user(user_id)
