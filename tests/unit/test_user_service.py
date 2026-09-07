import pytest
from fastapi import HTTPException

from app.core.security import hash_password
from app.schemas.auth import LoginRequest, RegisterRequest
from app.services.user_service import UserService


@pytest.fixture
def service(user_repo):
    return UserService(user_repo)


def test_register_success(service, user_repo, make_user):
    user_repo.get_by_email.return_value = None
    user_repo.create.return_value = make_user(id="user-1")
    result = service.register(
        RegisterRequest(email="user@example.com", password="password123", display_name="User")
    )
    assert result.id == "user-1"
    user_repo.create.assert_called_once()
    stored = user_repo.create.call_args.kwargs["hashed_password"]
    assert stored != "password123"
    assert "password123" not in stored


def test_register_duplicate_email(service, user_repo, make_user):
    user_repo.get_by_email.return_value = make_user(id="existing")
    with pytest.raises(HTTPException) as exc:
        service.register(
            RegisterRequest(email="user@example.com", password="password123", display_name="User")
        )
    assert exc.value.status_code == 409
    user_repo.create.assert_not_called()


def test_register_db_exception_still_409(service, user_repo):
    user_repo.get_by_email.return_value = None
    user_repo.create.side_effect = Exception("unique constraint violation")
    with pytest.raises(HTTPException) as exc:
        service.register(
            RegisterRequest(email="user@example.com", password="password123", display_name="User")
        )
    assert exc.value.status_code == 409


def test_authenticate_success(service, user_repo, make_user):
    user_repo.get_by_email.return_value = make_user(hashed_password=hash_password("password123"))
    result = service.authenticate(LoginRequest(email="user@example.com", password="password123"))
    assert result.token_type == "bearer"
    assert result.access_token


def test_authenticate_wrong_password(service, user_repo, make_user):
    user_repo.get_by_email.return_value = make_user(hashed_password=hash_password("different"))
    with pytest.raises(HTTPException) as exc:
        service.authenticate(LoginRequest(email="user@example.com", password="password123"))
    assert exc.value.status_code == 401


def test_authenticate_unknown_email(service, user_repo):
    user_repo.get_by_email.return_value = None
    with pytest.raises(HTTPException) as exc:
        service.authenticate(LoginRequest(email="nobody@example.com", password="password123"))
    assert exc.value.status_code == 401


def test_authenticate_email_case_insensitive(service, user_repo, make_user):
    user_repo.get_by_email.return_value = make_user(hashed_password=hash_password("password123"))
    service.authenticate(LoginRequest(email="USER@example.com", password="password123"))
    user_repo.get_by_email.assert_called_with("user@example.com")


def test_get_by_id_found(service, user_repo, make_user):
    user_repo.get_by_id.return_value = make_user()
    assert service.get_by_id("user-1").id == "user-1"


def test_get_by_id_not_found(service, user_repo):
    user_repo.get_by_id.return_value = None
    assert service.get_by_id("missing") is None