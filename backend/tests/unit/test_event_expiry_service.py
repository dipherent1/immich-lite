from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from app.models.event import Event
from app.services.event_expiry_service import EventExpiryService

NOW = datetime(2026, 11, 12, 12, 0, 0, tzinfo=timezone.utc)  # SQLModel needs aware datetimes


def _event(minutes_left: float, **kw) -> Event:
    return Event(
        id=kw.pop("id", "event-1"),
        owner_id="owner",
        name=kw.pop("name", "Party"),
        join_token="tok",
        starts_at=NOW - timedelta(hours=3),
        # The DB hands back naive UTC; the service must cope with that.
        expires_at=(NOW + timedelta(minutes=minutes_left)).replace(tzinfo=None),
        **kw,
    )


@pytest.fixture
def deps():
    events, notifs, faces, files = MagicMock(), MagicMock(), MagicMock(), MagicMock()
    publish = MagicMock(return_value=True)
    events.list_attendee_ids.return_value = ["u1", "u2"]
    events.list_expiring_unwarned.return_value = []
    events.list_expired.return_value = []
    return events, notifs, faces, files, publish


@pytest.fixture
def service(deps):
    events, notifs, faces, files, publish = deps
    return EventExpiryService(events, notifs, faces, files, publish, warning_minutes=20)


def test_warning_window_is_passed_to_repository(service, deps):
    service.warn_expiring(NOW)
    deps[0].list_expiring_unwarned.assert_called_once_with(NOW, timedelta(minutes=20))


def test_warn_notifies_every_attendee_and_marks_event(service, deps):
    events, _, _, _, publish = deps
    events.list_expiring_unwarned.return_value = [_event(19.5)]
    assert service.warn_expiring(NOW) == 1
    assert publish.call_count == 2
    kwargs = publish.call_args.kwargs
    assert kwargs["type"] == "event_expiring"
    assert kwargs["subject_type"] == "event" and kwargs["subject_id"] == "event-1"
    assert "19 minutes" in kwargs["body"] and "Party" in kwargs["body"]
    events.mark_warned.assert_called_once_with("event-1", NOW)


def test_warn_retries_when_publish_fails(service, deps):
    events, _, _, _, publish = deps
    events.list_expiring_unwarned.return_value = [_event(10)]
    publish.return_value = False
    assert service.warn_expiring(NOW) == 0
    events.mark_warned.assert_not_called()  # stays unwarned -> next sweep retries


def test_warn_failure_on_one_event_does_not_block_others(service, deps):
    events, _, _, _, publish = deps
    events.list_expiring_unwarned.return_value = [_event(10, id="a"), _event(10, id="b")]
    events.list_attendee_ids.side_effect = [RuntimeError("db"), ["u1"]]
    assert service.warn_expiring(NOW) == 1
    events.mark_warned.assert_called_once_with("b", NOW)


def test_purge_removes_everything_in_safe_order(service, deps):
    events, notifs, faces, files, _ = deps
    events.list_expired.return_value = [_event(-1)]
    order = MagicMock()
    order.attach_mock(faces.delete_by_event, "faces")
    order.attach_mock(files.delete_directory, "files")
    order.attach_mock(notifs.delete_for_subject, "notifs")
    order.attach_mock(events.delete_event, "row")
    assert service.purge_expired(NOW) == 1
    names = [c[0] for c in order.mock_calls]
    assert names == ["faces", "files", "files", "notifs", "row"]  # DB row last
    assert [c.args[0] for c in files.delete_directory.call_args_list] == [
        "photos/event-1",
        "previews/event-1",
    ]
    notifs.delete_for_subject.assert_called_once_with("event", "event-1")


def test_purge_keeps_row_if_qdrant_fails_so_it_retries(service, deps):
    events, _, faces, files, _ = deps
    events.list_expired.return_value = [_event(-1)]
    faces.delete_by_event.side_effect = RuntimeError("qdrant down")
    assert service.purge_expired(NOW) == 0
    events.delete_event.assert_not_called()
    files.delete_directory.assert_not_called()


def test_purge_failure_on_one_event_does_not_block_others(service, deps):
    events, _, faces, _, _ = deps
    events.list_expired.return_value = [_event(-1, id="a"), _event(-5, id="b")]
    faces.delete_by_event.side_effect = [RuntimeError("boom"), None]
    assert service.purge_expired(NOW) == 1
    events.delete_event.assert_called_once_with("b")


def test_sweep_reports_counts(service, deps):
    events, *_ = deps
    events.list_expiring_unwarned.return_value = [_event(10, id="a")]
    events.list_expired.return_value = [_event(-1, id="b")]
    assert service.sweep(NOW) == {"warned": 1, "deleted": 1}


def test_naive_now_is_treated_as_utc(service, deps):
    service.warn_expiring(NOW.replace(tzinfo=None))
    deps[0].list_expiring_unwarned.assert_called_once_with(NOW, timedelta(minutes=20))


def test_queries_always_use_aware_datetimes(service, deps):
    service.sweep()
    for call in (deps[0].list_expiring_unwarned.call_args, deps[0].list_expired.call_args):
        assert call.args[0].tzinfo is not None
