from __future__ import annotations

from datetime import datetime, timedelta

from sqlmodel import Session, delete, func, select, update

from app.models.event import Event
from app.models.event_attendee import EventAttendee


class EventRepository:
    """All SQLAlchemy/SQLModel access for the events and event_attendees tables."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create_event(
        self,
        *,
        owner_id: str,
        name: str,
        join_token: str,
        starts_at: datetime,
        expires_at: datetime | None,
    ) -> Event:
        event = Event(
            owner_id=owner_id,
            name=name,
            join_token=join_token,
            starts_at=starts_at,
            expires_at=expires_at,
        )
        self._db.add(event)
        self._db.commit()
        self._db.refresh(event)
        return event

    def list_expiring_unwarned(self, now: datetime, window: timedelta) -> list[Event]:
        """Events that end within `window` (but haven't ended) and whose
        "ending soon" notification hasn't been sent. `now` must be timezone-aware UTC."""
        return list(
            self._db.scalars(
                select(Event).where(
                    Event.expires_at.is_not(None),  # type: ignore[union-attr]
                    Event.expires_at > now,  # type: ignore[operator]
                    Event.expires_at <= now + window,  # type: ignore[operator]
                    Event.expiry_warned_at.is_(None),  # type: ignore[union-attr]
                )
            )
        )

    def mark_warned(self, event_id: str, now: datetime) -> None:
        self._db.execute(
            update(Event).where(Event.id == event_id).values(expiry_warned_at=now)
        )
        self._db.commit()

    def list_expired(self, now: datetime) -> list[Event]:
        """Events whose expiry has passed. `now` must be timezone-aware UTC. Legacy events
        (expires_at NULL) are never returned."""
        return list(
            self._db.scalars(
                select(Event).where(
                    Event.expires_at.is_not(None),  # type: ignore[union-attr]
                    Event.expires_at <= now,  # type: ignore[operator]
                )
            )
        )

    def delete_event(self, event_id: str) -> None:
        """Delete the event row. Photos, attendees, join requests and (via
        photos) matches go with it through ON DELETE CASCADE."""
        self._db.execute(delete(Event).where(Event.id == event_id))
        self._db.commit()

    def get_by_id(self, event_id: str) -> Event | None:
        return self._db.get(Event, event_id)

    def get_by_token(self, join_token: str) -> Event | None:
        return self._db.scalars(select(Event).where(Event.join_token == join_token)).first()

    def is_attendee(self, event_id: str, user_id: str) -> bool:
        return self._db.scalars(
            select(EventAttendee).where(
                EventAttendee.event_id == event_id,
                EventAttendee.user_id == user_id,
            )
        ).first() is not None

    def add_attendee(self, event_id: str, user_id: str) -> bool:
        """Upsert an attendee row. Returns True if newly added, False if already present."""
        if self.is_attendee(event_id, user_id):
            return False
        self._db.add(EventAttendee(event_id=event_id, user_id=user_id))
        self._db.commit()
        return True

    def attendee_count(self, event_id: str) -> int:
        return self._db.scalar(
            select(func.count()).select_from(EventAttendee).where(EventAttendee.event_id == event_id)
        ) or 0

    def list_attendee_ids(self, event_id: str) -> list[str]:
        """All attendee user ids for an event (used to scope matching, Phase 5)."""
        rows = list(
            self._db.scalars(
                select(EventAttendee.user_id).where(EventAttendee.event_id == event_id)
            )
        )
        return list(dict.fromkeys(rows))

    def search_by_name(self, name: str) -> list[Event]:
        """Partial, case-insensitive name match, newest first."""
        return list(
            self._db.scalars(
                select(Event)
                .where(Event.name.ilike(f"%{name}%"))
                .order_by(Event.created_at.desc())
            )
        )

    def list_for_user(self, user_id: str) -> list[Event]:
        """Events the user owns or attends, newest first (deduped)."""
        owned = select(Event).where(Event.owner_id == user_id)
        attended = (
            select(Event)
            .join(EventAttendee, EventAttendee.event_id == Event.id)
            .where(EventAttendee.user_id == user_id)
        )
        seen: set[str] = set()
        events: list[Event] = []
        for event in list(self._db.scalars(owned)) + list(self._db.scalars(attended)):
            if event.id not in seen:
                seen.add(event.id)
                events.append(event)
        events.sort(key=lambda e: e.created_at, reverse=True)
        return events

    def set_cover_photo_if_unset(self, event_id: str, photo_id: str) -> bool:
        """Set cover_photo_id only when the event has none yet (first image wins).

        Uses an atomic conditional UPDATE so concurrent batch uploads never race.
        """
        result = self._db.execute(
            update(Event)
            .where(Event.id == event_id, Event.cover_photo_id.is_(None))
            .values(cover_photo_id=photo_id),
            execution_options={"synchronize_session": "fetch"},
        )
        self._db.commit()
        return (result.rowcount or 0) > 0

    def set_cover_photo(self, event_id: str, photo_id: str) -> Event | None:
        """Explicitly set an event's cover_photo_id (creator-only in the service)."""
        event = self._db.get(Event, event_id)
        if event is None:
            return None
        event.cover_photo_id = photo_id
        self._db.add(event)
        self._db.commit()
        self._db.refresh(event)
        return event
