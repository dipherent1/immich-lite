from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Callable

from app.core.file_storage import LocalFileService
from app.core.vector_db import EventFaceRepository
from app.models.event import Event
from app.repositories.event_repository import EventRepository
from app.repositories.notification_repository import NotificationRepository

logger = logging.getLogger("app.event_expiry")

EVENT_EXPIRING_NOTIFICATION = "event_expiring"


class EventExpiryService:
    """Warns attendees shortly before an event ends, then deletes it.

    Run periodically by the worker (see `sweep_expired_events`). Deleting an event
    removes, in this order:
      1. its face vectors in Qdrant (no FKs there, so explicit),
      2. its photo files and cached previews on disk,
      3. notifications pointing at it (soft ids, so explicit),
      4. the `events` row — photos, attendees, join requests and matches follow
         through ON DELETE CASCADE.
    External stores go first and are idempotent; if any step fails the event row
    survives and the next sweep simply retries.
    """

    def __init__(
        self,
        events: EventRepository,
        notifications: NotificationRepository,
        faces: EventFaceRepository,
        files: LocalFileService,
        publish: Callable[..., bool],
        *,
        warning_minutes: int = 20,
    ) -> None:
        self._events = events
        self._notifications = notifications
        self._faces = faces
        self._files = files
        self._publish = publish
        self._warning = timedelta(minutes=warning_minutes)

    @staticmethod
    def _utc(dt: datetime) -> datetime:
        """Normalise to aware UTC. SQLModel only accepts aware datetimes as query
        parameters, but values read back from the DB may be naive (stored as UTC)."""
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @classmethod
    def _now_utc(cls, now: datetime | None) -> datetime:
        return cls._utc(now or datetime.now(timezone.utc))

    def warn_expiring(self, now: datetime | None = None) -> int:
        """Send the "ending soon" notification for events inside the warning
        window. Returns the number of events warned."""
        now = self._now_utc(now)
        warned = 0
        for event in self._events.list_expiring_unwarned(now, self._warning):
            try:
                if self._warn(event, now):
                    warned += 1
            except Exception:
                logger.exception("expiry warning failed event=%s", event.id)
        return warned

    def _warn(self, event: Event, now: datetime) -> bool:
        assert event.expires_at is not None
        minutes_left = max(1, int((self._utc(event.expires_at) - now).total_seconds() // 60))
        body = (
            f'"{event.name}" and all its photos will be deleted in about '
            f"{minutes_left} minutes. Download anything you want to keep now."
        )
        all_sent = True
        for user_id in self._events.list_attendee_ids(event.id):
            ok = self._publish(
                user_id=user_id,
                type=EVENT_EXPIRING_NOTIFICATION,
                title="Event ending soon",
                body=body,
                subject_type="event",
                subject_id=event.id,
            )
            all_sent = all_sent and ok
        if not all_sent:
            # Broker trouble: leave the flag unset so the next sweep retries.
            logger.warning("expiry warning not fully sent event=%s, will retry", event.id)
            return False
        self._events.mark_warned(event.id, now)
        logger.info("expiry warning sent event=%s", event.id)
        return True

    def purge_expired(self, now: datetime | None = None) -> int:
        """Delete every event whose expiry has passed. Returns the number deleted."""
        now = self._now_utc(now)
        deleted = 0
        for event in self._events.list_expired(now):
            try:
                self._purge(event)
                deleted += 1
            except Exception:
                logger.exception("event deletion failed event=%s, will retry", event.id)
        return deleted

    def _purge(self, event: Event) -> None:
        self._faces.delete_by_event(event.id)
        self._files.delete_directory(f"photos/{event.id}")
        self._files.delete_directory(f"previews/{event.id}")
        self._notifications.delete_for_subject("event", event.id)
        self._events.delete_event(event.id)
        logger.info("event deleted (expired) id=%s name=%s", event.id, event.name)

    def sweep(self, now: datetime | None = None) -> dict[str, int]:
        """One full pass: warn events entering the warning window, then delete
        the ones that have ended (the two sets never overlap)."""
        return {
            "warned": self.warn_expiring(now),
            "deleted": self.purge_expired(now),
        }
