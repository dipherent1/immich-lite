from __future__ import annotations

import logging

from app.models.notification import Notification
from app.repositories.notification_repository import NotificationRepository

logger = logging.getLogger("app.notifications")


class NotificationService:
    """Creates notifications (persisted to Postgres) and fanning them out to the
    user's live SSE connection via the shared manager.

    Persist + dispatch run together: if the SSE dispatch is momentarily down we
    still return the row so the frontend's poll fallback sees it; the row is the
    source of truth, the live push is an optimization.
    """

    def __init__(self, repository: NotificationRepository) -> None:
        self._repository = repository

    def create(
        self,
        *,
        user_id: str,
        type: str,
        title: str,
        body: str,
        subject_type: str | None = None,
        subject_id: str | None = None,
        dispatch: bool = True,
    ) -> Notification:
        notif = self._repository.create(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        if dispatch:
            # Relay to any live SSE connection for this user (best-effort).
            try:
                from app.core.sse import _notification_payload, sse_manager

                sse_manager.dispatch(user_id, notif, _notification_payload(notif))
            except Exception:
                logger.exception(
                    "failed to dispatch SSE notification user=%s type=%s",
                    user_id,
                    type,
                )
        logger.info(
            "notification created",
            extra={"extra_fields": {"user_id": user_id, "type": type, "id": notif.id}},
        )
        return notif

    def list_for_user(
        self, user_id: str, *, offset: int = 0, limit: int = 24
    ) -> tuple[list[Notification], bool]:
        return self._repository.list_for_user(user_id, offset=offset, limit=limit)

    def unread_count(self, user_id: str) -> int:
        return self._repository.unread_count(user_id)

    def get_by_id(self, notification_id: str, user_id: str):
        """Fetch a notification, but only if it belongs to this user."""
        return self._repository.get_by_id(notification_id, user_id)

    def mark_read(self, notification_id: str, user_id: str) -> None:
        self._repository.mark_read(notification_id, user_id)

    def mark_all_read(self, user_id: str) -> None:
        self._repository.mark_all_read(user_id)

    def create_match_notifications(
        self,
        *,
        user_id: str,
        event_id: str,
        event_name: str,
        matched_photo_ids: set[str],
    ) -> None:
        """Notify an attendee about existing photos that matched them.

        Used by attendee backfill (join / join-request approval) — same payload
        shape the worker publishes for upload-time matches, so the frontend
        renders them identically.
        """
        for _ in sorted(matched_photo_ids):
            self.create(
                user_id=user_id,
                type="photo_matched",
                title="New match found!",
                body=f"A photo in {event_name} matches your face",
                subject_type="event",
                subject_id=event_id,
            )
