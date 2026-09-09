import pytest
from sqlalchemy.exc import IntegrityError

from app.repositories.user_repository import UserRepository


def test_create_lowercases_email(db_session):
    user = UserRepository(db_session).create(
        email="User@Example.com",
        hashed_password="hashed",
        display_name="Test User",
    )
    assert user.email == "user@example.com"
    assert user.display_name == "Test User"
    assert user.hashed_password == "hashed"


def test_get_by_id_roundtrip(db_session):
    repo = UserRepository(db_session)
    created = repo.create(email="user@example.com", hashed_password="h", display_name="U")
    fetched = repo.get_by_id(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.email == "user@example.com"


def test_get_by_id_not_found(db_session):
    assert UserRepository(db_session).get_by_id("missing") is None


def test_get_by_email_found(db_session):
    repo = UserRepository(db_session)
    created = repo.create(email="user@example.com", hashed_password="h", display_name="U")
    assert repo.get_by_email("user@example.com").id == created.id


def test_get_by_email_case_sensitive_lookup(db_session):
    repo = UserRepository(db_session)
    created = repo.create(email="user@example.com", hashed_password="h", display_name="U")
    assert repo.get_by_email("USER@EXAMPLE.COM") is None
    assert repo.get_by_email("user@example.com").id == created.id


def test_get_by_email_not_found(db_session):
    assert UserRepository(db_session).get_by_email("nobody@example.com") is None


def test_create_duplicate_email_raises_integrity_error(db_session):
    repo = UserRepository(db_session)
    repo.create(email="user@example.com", hashed_password="h", display_name="U1")
    with pytest.raises(IntegrityError):
        repo.create(email="user@example.com", hashed_password="h2", display_name="U2")


def test_session_still_usable_after_integrity_error(db_session):
    repo = UserRepository(db_session)
    repo.create(email="dup@example.com", hashed_password="h", display_name="U1")
    with pytest.raises(IntegrityError):
        repo.create(email="dup@example.com", hashed_password="h", display_name="U2")
    assert repo.get_by_email("dup@example.com").display_name == "U1"