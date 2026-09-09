from __future__ import annotations

from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from app.models.user import User


class UserRepository:
    """All SQLAlchemy/SQLModel access for the users table lives here."""

    def __init__(self, db: Session) -> None:
        self._db = db

    def get_by_id(self, user_id: str) -> User | None:
        return self._db.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        return self._db.scalars(select(User).where(User.email == email)).first()

    def create(self, *, email: str, hashed_password: str, display_name: str) -> User:
        user = User(
            email=email.lower(),
            hashed_password=hashed_password,
            display_name=display_name,
        )
        self._db.add(user)
        try:
            self._db.commit()
        except IntegrityError:
            self._db.rollback()
            raise
        self._db.refresh(user)
        return user
