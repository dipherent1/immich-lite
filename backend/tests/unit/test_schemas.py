import pytest
from pydantic import ValidationError

from app.models.photo_match import PhotoMatch
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.event import EventCreate


def test_register_request_valid():
    req = RegisterRequest(email="user@example.com", password="password123", display_name="User")
    assert req.email == "user@example.com"


def test_register_request_invalid_email():
    with pytest.raises(ValidationError):
        RegisterRequest(email="not-an-email", password="password123", display_name="User")


def test_register_request_short_password():
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password="short", display_name="User")


def test_register_request_empty_display_name():
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password="password123", display_name="")


def test_register_request_long_display_name():
    with pytest.raises(ValidationError):
        RegisterRequest(email="user@example.com", password="password123", display_name="x" * 101)


def test_login_request_accepts_any_password_length():
    req = LoginRequest(email="user@example.com", password="abc")
    assert req.password == "abc"


def test_event_create_name_required():
    with pytest.raises(ValidationError):
        EventCreate(name="")


def test_event_create_name_too_long():
    with pytest.raises(ValidationError):
        EventCreate(name="x" * 121)


def test_event_create_defaults():
    event = EventCreate(name="Party")
    assert event.expires_at is None


def test_photo_match_bbox_dict_valid():
    m = PhotoMatch(
        photo_id="p1",
        user_id="u1",
        similarity=0.9,
        bbox='{"x1":0,"y1":1,"x2":2,"y2":3}',
    )
    assert m.bbox_dict == {"x1": 0, "y1": 1, "x2": 2, "y2": 3}


def test_photo_match_bbox_dict_invalid_json():
    m = PhotoMatch(photo_id="p1", user_id="u1", similarity=0.9, bbox="not-json")
    assert m.bbox_dict == {}


def test_photo_match_bbox_dict_none():
    m = PhotoMatch(photo_id="p1", user_id="u1", similarity=0.9, bbox=None)
    assert m.bbox_dict == {}