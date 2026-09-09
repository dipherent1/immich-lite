import os
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

# Ensure a JWT secret exists before any app module reads settings. `config.py`
# calls load_dotenv() at import time, which won't override an env var that is
# already present, so tests get a deterministic secret regardless of .env.
os.environ.setdefault("JWT_SECRET", "test-secret-for-tests-that-is-at-least-32-bytes-long")

from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel, Session, create_engine

from app.core.file_storage import LocalFileService
from app.core.vector_db import EventFaceRepository, QdrantProfileRepository
from app.domain.interfaces import EmbeddingProvider
from app.models.event import Event
from app.models.user import User
from app.repositories.event_repository import EventRepository
from app.repositories.join_request_repository import JoinRequestRepository
from app.repositories.notification_repository import NotificationRepository
from app.repositories.photo_match_repository import PhotoMatchRepository
from app.repositories.photo_repository import PhotoRepository
from app.repositories.user_repository import UserRepository
from app.services.matching_service import MatchingService
from app.services.notification_service import NotificationService
from app.services.profile_service import ProfileService


def _naive_utc(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)


@pytest.fixture
def db_session():
    """Fresh in-memory SQLite session with all tables created for a single test."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    SQLModel.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def user_repo():
    return MagicMock(spec=UserRepository)


@pytest.fixture
def event_repo():
    return MagicMock(spec=EventRepository)


@pytest.fixture
def photo_repo():
    return MagicMock(spec=PhotoRepository)


@pytest.fixture
def match_repo():
    return MagicMock(spec=PhotoMatchRepository)


@pytest.fixture
def file_service():
    return MagicMock(spec=LocalFileService)


@pytest.fixture
def embedder():
    return MagicMock(spec=EmbeddingProvider)


@pytest.fixture
def profile_repo():
    return MagicMock(spec=QdrantProfileRepository)


@pytest.fixture
def event_face_repo():
    return MagicMock(spec=EventFaceRepository)


@pytest.fixture
def profiles():
    return MagicMock(spec=ProfileService)


@pytest.fixture
def matching():
    return MagicMock(spec=MatchingService)


@pytest.fixture
def notifications():
    return MagicMock(spec=NotificationService)


@pytest.fixture
def notification_repo():
    return MagicMock(spec=NotificationRepository)


@pytest.fixture
def join_request_repo():
    return MagicMock(spec=JoinRequestRepository)


@pytest.fixture
def make_user():
    def _make_user(
        id="user-1",
        email="user@example.com",
        display_name="Test User",
        hashed_password="hashed-placeholder",
    ):
        return User(
            id=id,
            email=email,
            display_name=display_name,
            hashed_password=hashed_password,
        )

    return _make_user


@pytest.fixture
def make_event():
    def _make_event(**overrides):
        now = datetime.now(timezone.utc)
        defaults = {
            "id": "event-1",
            "owner_id": "user-1",
            "name": "Test Event",
            "join_token": "token-abc",
            "starts_at": _naive_utc(now - timedelta(hours=1)),
            "expires_at": _naive_utc(now + timedelta(hours=1)),
            "created_at": _naive_utc(now),
        }
        defaults.update(overrides)
        return Event(**defaults)

    return _make_event