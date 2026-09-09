from __future__ import annotations

from sqlmodel import Session, func, select

from app.models.notification import Notification


class NotificationRepository:
    """All SQLAlchemy/SQLModel access for the notifications table."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def create(
        self,
        *,
        user_id: str,
        type: str,
        title: str,
        body: str,
        subject_type: str | None = None,
        subject_id: str | None = None,
    ) -> Notification:
        notif = Notification(
            user_id=user_id,
            type=type,
            title=title,
            body=body,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        self._db.add(notif)
        self._db.commit()
        self._db.refresh(notif)
        return notif

    def list_for_user(
        self,
        user_id: str,
        *,
        offset: int = 0,
        limit: int = 24,
    ) -> tuple[list[Notification], bool]:
        statement = (
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .offset(offset)
            .limit(limit + 1)
        )
        rows = list(self._db.scalars(statement))
        has_more = len(rows) > limit
        return rows[:limit], has_more

    def unread_count(self, user_id: str) -> int:
        return self._db.scalar(
            select(func.count())
            .select_from(Notification)
            .where(
                Notification.user_id == user_id,
                Notification.is_read == False,  # noqa: E712
            )
        ) or 0

    def get_by_id(self, notification_id: str, user_id: str) -> Notification | None:
        notif = self._db.get(Notification, notification_id)
        if notif is None or notif.user_id != user_id:
            return None
        return notif

    def mark_read(self, notification_id: str, user_id: str) -> None:
        notif = self._db.get(Notification, notification_id)
        if notif is not None and notif.user_id == user_id:
            notif.is_read = True
            self._db.add(notif)
            self._db.commit()

    def mark_all_read(self, user_id: str) -> None:
        statement = select(Notification).where(
            Notification.user_id == user_id,
            Notification.is_read == False,  # noqa: E712
        )
        for notif in self._db.scalars(statement):
            notif.is_read = True
            self._db.add(notif)
        self._db.commit()
