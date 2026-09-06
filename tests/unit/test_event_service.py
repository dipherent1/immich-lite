from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.schemas.event import EventCreate
from app.services.event_service import EventService


@pytest.fixture
def service(event_repo, profiles):
    return EventService(event_repo, profiles)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)


# --- is_active (time-window rule) ---


def test_is_active_within_window(make_event):
    now = _now()
    event = make_event()
    assert EventService.is_active(event, now=now)


def test_is_active_before_start(make_event):
    now = _now()
    event = make_event(starts_at=_naive(now + timedelta(minutes=10)))
    assert not EventService.is_active(event, now=now)


def test_is_active_at_exact_start(make_event):
    now = _now()
    event = make_event(starts_at=_naive(now))
    assert EventService.is_active(event, now=now)


def test_is_active_after_expiry(make_event):
    now = _now()
    event = make_event(expires_at=_naive(now - timedelta(minutes=1)))
    assert not EventService.is_active(event, now=now)


def test_is_active_at_exact_expiry(make_event):
    # `now == expires_at` is still active; only `now > expires_at` closes it.
    now = _now()
    event = make_event(expires_at=_naive(now))
    assert EventService.is_active(event, now=now)


def test_is_active_null_expiry(make_event):
    now = _now()
    event = make_event(expires_at=None)
    assert EventService.is_active(event, now=now)


def test_is_active_naive_event_fields_tz_aware_now(make_event):
    # The DB columns are naive UTC; `now` may come in tz-aware. The service
    # normalizes `now` to naive UTC so the comparison never raises.
    now = _now()
    event = make_event(starts_at=_naive(now - timedelta(hours=1)), expires_at=_naive(now + timedelta(hours=1)))
    assert EventService.is_active(event, now=now)


def test_is_active_naive_default_now(make_event):
    event = make_event()  # active relative to the current instant
    assert EventService.is_active(event)


# --- create ---


def test_create_requires_face_profile(service, event_repo, profiles, make_user):
    profiles.has_profile.return_value = False
    with pytest.raises(HTTPException) as exc:
        service.create(make_user(), EventCreate(name="Party"))
    assert exc.value.status_code == 400
    event_repo.create_event.assert_not_called()


def test_create_success(service, event_repo, profiles, make_user, make_event):
    profiles.has_profile.return_value = True
    created = make_event()
    event_repo.create_event.return_value = created
    owner = make_user(id="user-1")
    event = service.create(owner, EventCreate(name="Party"))
    assert event.id == "event-1"
    event_repo.add_attendee.assert_called_once_with("event-1", owner.id)


def test_create_invalid_window(service, event_repo, profiles, make_user):
    profiles.has_profile.return_value = True
    now = _now()
    payload = EventCreate(name="Party", starts_at=now, expires_at=now - timedelta(hours=1))
    with pytest.raises(HTTPException) as exc:
        service.create(make_user(), payload)
    assert exc.value.status_code == 422
    event_repo.create_event.assert_not_called()


def test_create_join_token_is_unique_random(service):
    tokens = {service.generate_join_token() for _ in range(100)}
    assert len(tokens) == 100


# --- join ---


def test_join_unknown_token(service, event_repo):
    event_repo.get_by_token.return_value = None
    with pytest.raises(HTTPException) as exc:
        service.join("user-2", "token-abc")
    assert exc.value.status_code == 404


def test_join_inactive_event(service, event_repo, make_event):
    now = _now()
    event_repo.get_by_token.return_value = make_event(
        starts_at=_naive(now - timedelta(hours=2)), expires_at=_naive(now - timedelta(hours=1))
    )
    with pytest.raises(HTTPException) as exc:
        service.join("user-2", "token-abc")
    assert exc.value.status_code == 410


def test_join_success(service, event_repo, make_event):
    event_repo.get_by_token.return_value = make_event()
    event_repo.add_attendee.return_value = True
    event, added = service.join("user-2", "token-abc")
    assert event.id == "event-1"
    assert added is True
    event_repo.add_attendee.assert_called_once_with("event-1", "user-2")


def test_join_already_attendee(service, event_repo, make_event):
    event_repo.get_by_token.return_value = make_event()
    event_repo.add_attendee.return_value = False
    _, added = service.join("user-2", "token-abc")
    assert added is False


# --- get_by_id ---


def test_get_by_id_not_found(service, event_repo):
    event_repo.get_by_id.return_value = None
    with pytest.raises(HTTPException) as exc:
        service.get_by_id("user-1", "event-1")
    assert exc.value.status_code == 404


def test_get_by_id_not_member(service, event_repo, make_event):
    event_repo.get_by_id.return_value = make_event(owner_id="user-1")
    event_repo.is_attendee.return_value = False
    with pytest.raises(HTTPException) as exc:
        service.get_by_id("user-99", "event-1")
    assert exc.value.status_code == 403


def test_get_by_id_owner(service, event_repo, make_event):
    event_repo.get_by_id.return_value = make_event(owner_id="user-1")
    event_repo.attendee_count.return_value = 5
    event, count = service.get_by_id("user-1", "event-1")
    assert event.id == "event-1"
    assert count == 5


def test_get_by_id_attendee(service, event_repo, make_event):
    event_repo.get_by_id.return_value = make_event(owner_id="user-1")
    event_repo.is_attendee.return_value = True
    event_repo.attendee_count.return_value = 2
    _, count = service.get_by_id("user-2", "event-1")
    assert count == 2


# --- search / list ---


def test_search_delegates(service, event_repo, make_event):
    results = [make_event(name="Parade")]
    event_repo.search_by_name.return_value = results
    assert service.search("par") == results
    event_repo.search_by_name.assert_called_once_with("par")


def test_list_for_user_delegates(service, event_repo, make_event):
    results = [make_event()]
    event_repo.list_for_user.return_value = results
    assert service.list_for_user("user-1") == results
    event_repo.list_for_user.assert_called_once_with("user-1")