from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.core.vector_db import EventFaceRepository, QdrantProfileRepository
from app.services.profile_service import ProfileService

API_PREFIX = "/api/v1"


@pytest.fixture
def profile_repo():
    repo = MagicMock(spec=QdrantProfileRepository)
    repo.has_profile.return_value = True
    return repo


@pytest.fixture
def face_repo():
    return MagicMock(spec=EventFaceRepository)


@pytest.fixture
def profile_service():
    return MagicMock(spec=ProfileService)


@pytest.fixture
def client(db_session, tmp_path, profile_repo, face_repo, profile_service):
    """TestClient wired to in-memory SQLite and mocked Qdrant dependencies.

    Every request shares one SQLite session, and the Qdrant-backed repositories
    are swapped for mocks so nothing ever touches a real Qdrant server. The file
    service writes to a per-test temp dir instead of the real output root.
    """
    from app.api import deps
    from app.core.database import get_db
    from app.core.file_storage import LocalFileService
    from app.main import app

    def _override_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_db
    app.dependency_overrides[deps.get_profile_repository] = lambda: profile_repo
    app.dependency_overrides[deps.get_event_face_repository] = lambda: face_repo
    app.dependency_overrides[deps.get_profile_service] = lambda: profile_service
    app.dependency_overrides[deps.get_file_service] = lambda: LocalFileService(root=str(tmp_path))

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def register_user(
    client,
    email="user@example.com",
    password="password123",
    display_name="Test User",
):
    return client.post(
        f"{API_PREFIX}/auth/register",
        json={"email": email, "password": password, "display_name": display_name},
    )


def login(client, email="user@example.com", password="password123"):
    return client.post(
        f"{API_PREFIX}/auth/login",
        json={"email": email, "password": password},
    )


def auth_header(client, email="user@example.com", password="password123"):
    response = login(client, email, password)
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def make_event(client, headers, name="Test Event", extra=None):
    payload = {"name": name}
    if extra:
        payload.update(extra)
    return client.post(f"{API_PREFIX}/events", json=payload, headers=headers)