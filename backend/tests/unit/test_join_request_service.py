import pytest
from fastapi import HTTPException

from app.models.join_request import JoinRequest
from app.services.join_request_service import JoinRequestService


@pytest.fixture
def service(join_request_repo, event_repo, notifications, matching):
    matching.match_new_attendee.return_value = set()
    return JoinRequestService(join_request_repo, event_repo, notifications, matching)


def _make_request(event_id="event-1", requester_id="user-2", status="pending"):
    return JoinRequest(
        id="req-1",
        event_id=event_id,
        requester_id=requester_id,
        status=status,
    )


# --- approve ---


def test_approve_backfills_existing_photos(service, event_repo, join_request_repo, matching, notifications, make_event):
    event_repo.get_by_id.return_value = make_event()
    join_request_repo.get_by_id.return_value = _make_request()
    join_request_repo.get_requester.return_value = None  # skip join_approved notification
    event_repo.add_attendee.return_value = True
    join_request_repo.resolve.return_value = _make_request(status="approved")
    matching.match_new_attendee.return_value = {"photo-a", "photo-b"}

    resolved = service.approve("user-1", "event-1", "req-1")

    assert resolved.status == "approved"
    event_repo.add_attendee.assert_called_once_with("event-1", "user-2")
    matching.match_new_attendee.assert_called_once_with("event-1", "user-2")
    notifications.create_match_notifications.assert_called_once_with(
        user_id="user-2",
        event_id="event-1",
        event_name="Test Event",
        matched_photo_ids={"photo-a", "photo-b"},
    )


def test_approve_skips_backfill_for_already_member(service, event_repo, join_request_repo, matching, notifications, make_event):
    event_repo.get_by_id.return_value = make_event()
    join_request_repo.get_by_id.return_value = _make_request()
    join_request_repo.get_requester.return_value = None
    event_repo.add_attendee.return_value = False  # joined via share link meanwhile
    join_request_repo.resolve.return_value = _make_request(status="approved")

    service.approve("user-1", "event-1", "req-1")

    matching.match_new_attendee.assert_not_called()
    notifications.create_match_notifications.assert_not_called()


def test_approve_backfill_failure_is_best_effort(service, event_repo, join_request_repo, matching, make_event):
    event_repo.get_by_id.return_value = make_event()
    join_request_repo.get_by_id.return_value = _make_request()
    join_request_repo.get_requester.return_value = None
    event_repo.add_attendee.return_value = True
    join_request_repo.resolve.return_value = _make_request(status="approved")
    matching.match_new_attendee.side_effect = Exception("qdrant down")

    resolved = service.approve("user-1", "event-1", "req-1")

    assert resolved.status == "approved"


def test_approve_non_owner_forbidden(service, event_repo, join_request_repo, make_event):
    event_repo.get_by_id.return_value = make_event(owner_id="user-1")
    with pytest.raises(HTTPException) as exc:
        service.approve("user-99", "event-1", "req-1")
    assert exc.value.status_code == 403
    event_repo.add_attendee.assert_not_called()


# --- deny ---


def test_deny_resolves_and_notifies(service, event_repo, join_request_repo, notifications, make_event, make_user):
    event_repo.get_by_id.return_value = make_event()
    join_request_repo.get_by_id.return_value = _make_request()
    join_request_repo.resolve.return_value = _make_request(status="denied")
    join_request_repo.get_requester.return_value = make_user(id="user-2")

    resolved = service.deny("user-1", "event-1", "req-1")

    assert resolved.status == "denied"
    join_request_repo.resolve.assert_called_once_with("req-1", "denied")
    notifications.create.assert_called_once()
    assert notifications.create.call_args.kwargs["type"] == "join_denied"
    assert notifications.create.call_args.kwargs["user_id"] == "user-2"