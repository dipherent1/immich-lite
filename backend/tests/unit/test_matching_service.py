from unittest.mock import MagicMock

import pytest

from app.domain.entities import BoundingBox, FaceEmbedding
from app.models.photo import Photo
from app.services.matching_service import MatchingService


@pytest.fixture
def service(event_repo, event_face_repo, profile_repo, match_repo):
    return MatchingService(event_repo, event_face_repo, profile_repo, match_repo)


def _face(vector=(0.1,) * 512, bbox=None):
    return FaceEmbedding(
        image_path="",
        embedding=list(vector),
        bbox=bbox or BoundingBox(1, 2, 3, 4),
        face_score=0.9,
    )


def _photo(event_id="event-1"):
    return Photo(
        id="photo-1",
        event_id=event_id,
        uploader_user_id="user-1",
        storage_path="photos/event-1/photo-1.jpg",
        status="processed",
        processed_at=None,
    )


def test_match_photo_no_attendees(service, event_repo):
    event_repo.list_attendee_ids.return_value = []
    assert service.match_photo(_photo()) == set()


def test_match_photo_no_faces(service, event_repo, event_face_repo):
    event_repo.list_attendee_ids.return_value = ["user-1", "user-2"]
    event_face_repo.get_faces_for_photo.return_value = []
    assert service.match_photo(_photo()) == set()


def test_match_photo_success(service, event_repo, event_face_repo, profile_repo, match_repo):
    event_repo.list_attendee_ids.return_value = ["user-1", "user-2"]
    event_face_repo.get_faces_for_photo.return_value = [_face()]
    profile_repo.query_similar_restricted.return_value = [("user-2", 0.95)]

    matched = service.match_photo(_photo())

    assert matched == {"user-2"}
    profile_repo.query_similar_restricted.assert_called_once()
    args, kwargs = profile_repo.query_similar_restricted.call_args
    assert set(args[1]) == {"user-1", "user-2"}
    assert kwargs["threshold"] == 0.5
    match_repo.upsert_best.assert_called_once_with(
        photo_id="photo-1",
        user_id="user-2",
        similarity=0.95,
        bbox={"x1": 1, "y1": 2, "x2": 3, "y2": 4},
    )


def test_match_photo_below_threshold(service, event_repo, event_face_repo, profile_repo, match_repo):
    event_repo.list_attendee_ids.return_value = ["user-1"]
    event_face_repo.get_faces_for_photo.return_value = [_face()]
    profile_repo.query_similar_restricted.return_value = []  # filter already applied
    assert service.match_photo(_photo()) == set()
    match_repo.upsert_best.assert_not_called()


def test_match_photo_multiple_faces_same_person(service, event_repo, event_face_repo, profile_repo, match_repo):
    event_repo.list_attendee_ids.return_value = ["user-1"]
    face_a = _face(vector=(0.1,) * 512, bbox=BoundingBox(1, 1, 2, 2))
    face_b = _face(vector=(0.2,) * 512, bbox=BoundingBox(3, 3, 4, 4))
    event_face_repo.get_faces_for_photo.return_value = [face_a, face_b]
    profile_repo.query_similar_restricted.side_effect = [
        [("user-1", 0.6)],
        [("user-1", 0.9)],
    ]

    matched = service.match_photo(_photo())

    # Same person from two faces → one user id in the returned set.
    assert matched == {"user-1"}
    assert match_repo.upsert_best.call_count == 2
    # upsert_best itself keeps the higher similarity per (photo, user)


def test_match_photo_empty_embedding_skipped(service, event_repo, event_face_repo, profile_repo, match_repo):
    event_repo.list_attendee_ids.return_value = ["user-1"]
    empty = FaceEmbedding(image_path="", embedding=[], bbox=BoundingBox(1, 1, 2, 2), face_score=0.9)
    event_face_repo.get_faces_for_photo.return_value = [empty]
    assert service.match_photo(_photo()) == set()
    profile_repo.query_similar_restricted.assert_not_called()


def test_match_photo_scoped_to_attendees(service, event_repo, event_face_repo, profile_repo):
    # A high-similarity non-attendee must never be reached: the query is filtered
    # to the attendee ids, so we only see hits the profile repo returns.
    event_repo.list_attendee_ids.return_value = ["user-1"]
    event_face_repo.get_faces_for_photo.return_value = [_face()]
    profile_repo.query_similar_restricted.return_value = []
    assert service.match_photo(_photo()) == set()


# --- match_new_attendee (join/approve backfill) ---


def test_match_new_attendee_no_profile(service, event_face_repo, profile_repo, match_repo):
    profile_repo.has_profile.return_value = False
    assert service.match_new_attendee("event-1", "user-9") == set()
    event_face_repo.get_faces_for_event.assert_not_called()
    match_repo.upsert_best.assert_not_called()


def test_match_new_attendee_no_faces(service, event_face_repo, profile_repo, match_repo):
    profile_repo.has_profile.return_value = True
    event_face_repo.get_faces_for_event.return_value = []
    assert service.match_new_attendee("event-1", "user-9") == set()
    profile_repo.query_similar_restricted.assert_not_called()


def test_match_new_attendee_success(service, event_face_repo, profile_repo, match_repo):
    profile_repo.has_profile.return_value = True
    event_face_repo.get_faces_for_event.return_value = [
        ("photo-a", _face(vector=(0.1,) * 512, bbox=BoundingBox(1, 0, 2, 1))),
        ("photo-b", _face(vector=(0.2,) * 512, bbox=BoundingBox(3, 0, 4, 1))),
    ]
    profile_repo.query_similar_restricted.return_value = [("user-9", 0.85)]

    matched = service.match_new_attendee("event-1", "user-9")

    assert matched == {"photo-a", "photo-b"}
    assert match_repo.upsert_best.call_count == 2
    match_repo.upsert_best.assert_any_call(
        photo_id="photo-a",
        user_id="user-9",
        similarity=0.85,
        bbox={"x1": 1, "y1": 0, "x2": 2, "y2": 1},
    )


def test_match_new_attendee_below_threshold(service, event_face_repo, profile_repo, match_repo):
    profile_repo.has_profile.return_value = True
    event_face_repo.get_faces_for_event.return_value = [("photo-a", _face())]
    profile_repo.query_similar_restricted.return_value = []
    assert service.match_new_attendee("event-1", "user-9") == set()
    match_repo.upsert_best.assert_not_called()


def test_match_new_attendee_ignores_other_users(service, event_face_repo, profile_repo, match_repo):
    # A hit for someone else (non-determinism in the limited-scope query) must
    # never be written for the new attendee.
    profile_repo.has_profile.return_value = True
    event_face_repo.get_faces_for_event.return_value = [("photo-a", _face())]
    profile_repo.query_similar_restricted.return_value = [("someone-else", 0.9)]
    assert service.match_new_attendee("event-1", "user-9") == set()
    match_repo.upsert_best.assert_not_called()


def test_match_new_attendee_empty_embedding_skipped(service, event_face_repo, profile_repo, match_repo):
    profile_repo.has_profile.return_value = True
    empty = FaceEmbedding(image_path="", embedding=[], bbox=BoundingBox(1, 1, 2, 2), face_score=0.9)
    event_face_repo.get_faces_for_event.return_value = [("photo-a", empty)]
    assert service.match_new_attendee("event-1", "user-9") == set()
    profile_repo.query_similar_restricted.assert_not_called()


def test_feed_delegates(service, match_repo):
    match = MagicMock()
    event = MagicMock()
    match_repo.list_feed_for_user.return_value = ([(match, event)], False)
    result, has_more = service.feed("user-1")
    assert result == [(match, event)]
    assert has_more is False
    match_repo.list_feed_for_user.assert_called_once_with("user-1", offset=0, limit=24)