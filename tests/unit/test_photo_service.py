from datetime import datetime, timedelta, timezone

import pytest
from fastapi import HTTPException

from app.models.photo import Photo
from app.services.photo_service import MAX_UPLOAD_BYTES, PhotoService


@pytest.fixture
def service(event_repo, photo_repo, file_service):
    return PhotoService(event_repo, photo_repo, file_service)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _naive(dt: datetime) -> datetime:
    return dt.replace(tzinfo=None)


def _active_event(event_repo, make_event):
    event = make_event()
    event_repo.get_by_id.return_value = event
    return event


def _inactive_event(event_repo, make_event):
    now = _now()
    event = make_event(
        starts_at=_naive(now - timedelta(hours=2)), expires_at=_naive(now - timedelta(hours=1))
    )
    event_repo.get_by_id.return_value = event
    return event


def _photo(**overrides):
    defaults = {
        "id": "photo-1",
        "event_id": "event-1",
        "uploader_user_id": "user-1",
        "storage_path": "photos/event-1/photo-1.jpg",
        "status": "pending",
        "processed_at": None,
    }
    defaults.update(overrides)
    return Photo(**defaults)


# --- upload ---


def test_upload_over_size_limit(event_repo, make_event, service):
    _active_event(event_repo, make_event)
    with pytest.raises(HTTPException) as exc:
        service.upload("user-1", "event-1", "photo.jpg", b"x" * (MAX_UPLOAD_BYTES + 1))
    assert exc.value.status_code == 413


def test_upload_size_exact_limit_ok(event_repo, photo_repo, file_service, make_event, service, monkeypatch):
    event = make_event()
    event_repo.get_by_id.return_value = event
    event_repo.is_attendee.return_value = True  # owner check below
    file_service.save_upload.return_value = "photos/event-1/photo-1.jpg"
    photo_repo.create.return_value = _photo()
    monkeypatch.setattr("app.services.photo_service.enqueue_photo_processing", lambda pid: None)
    photo = service.upload("user-1", "event-1", "photo.jpg", b"x" * MAX_UPLOAD_BYTES)
    assert photo.id == "photo-1"


def test_upload_event_not_found(service, event_repo):
    event_repo.get_by_id.return_value = None
    with pytest.raises(HTTPException) as exc:
        service.upload("user-1", "event-1", "photo.jpg", b"data")
    assert exc.value.status_code == 404


def test_upload_not_member(event_repo, make_event, service):
    event = make_event(owner_id="user-1")
    event_repo.get_by_id.return_value = event
    event_repo.is_attendee.return_value = False
    with pytest.raises(HTTPException) as exc:
        service.upload("user-99", "event-1", "photo.jpg", b"data")
    assert exc.value.status_code == 403


def test_upload_inactive_event(event_repo, make_event, service):
    _inactive_event(event_repo, make_event)
    event_repo.is_attendee.return_value = True
    with pytest.raises(HTTPException) as exc:
        service.upload("user-1", "event-1", "photo.jpg", b"data")
    assert exc.value.status_code == 410


def test_upload_unsupported_extension(event_repo, make_event, service):
    event = make_event()
    event_repo.get_by_id.return_value = event
    event_repo.is_attendee.return_value = True
    with pytest.raises(HTTPException) as exc:
        service.upload("user-1", "event-1", "photo.exe", b"data")
    assert exc.value.status_code == 422


def test_upload_missing_extension_defaults_to_jpg(event_repo, photo_repo, file_service, make_event, service, monkeypatch):
    event = make_event()
    event_repo.get_by_id.return_value = event
    event_repo.is_attendee.return_value = True
    file_service.save_upload.return_value = "photos/event-1/photo-1.jpg"
    photo_repo.create.return_value = _photo()
    monkeypatch.setattr("app.services.photo_service.enqueue_photo_processing", lambda pid: None)
    service.upload("user-1", "event-1", "photo", b"data")
    args, kwargs = file_service.save_upload.call_args
    assert kwargs["relative"].endswith(".jpg")


def test_upload_success_enqueues(event_repo, photo_repo, file_service, make_event, service, monkeypatch):
    event = make_event()
    event_repo.get_by_id.return_value = event
    event_repo.is_attendee.return_value = True
    file_service.save_upload.return_value = "photos/event-1/photo-1.jpg"
    photo_repo.create.return_value = _photo()
    enqueued = []
    monkeypatch.setattr(
        "app.services.photo_service.enqueue_photo_processing",
        lambda pid: enqueued.append(pid),
    )
    photo = service.upload("user-1", "event-1", "photo.jpg", b"data")
    assert photo.id == "photo-1"
    assert enqueued == ["photo-1"]
    photo_repo.create.assert_called_once_with(
        event_id="event-1", uploader_user_id="user-1", storage_path="photos/event-1/photo-1.jpg"
    )


def test_upload_queue_down_upload_still_succeeds(event_repo, photo_repo, file_service, make_event, service, monkeypatch):
    event = make_event()
    event_repo.get_by_id.return_value = event
    event_repo.is_attendee.return_value = True
    file_service.save_upload.return_value = "photos/event-1/photo-1.jpg"
    photo_repo.create.return_value = _photo()

    def boom(photo_id):
        raise RuntimeError("redis down")

    monkeypatch.setattr("app.services.photo_service.enqueue_photo_processing", boom)
    photo = service.upload("user-1", "event-1", "photo.jpg", b"data")
    assert photo.id == "photo-1"


# --- list_for_event ---


def test_list_for_event_not_member(event_repo, make_event, service):
    event = make_event()
    event_repo.get_by_id.return_value = event
    event_repo.is_attendee.return_value = False
    with pytest.raises(HTTPException) as exc:
        service.list_for_event("user-99", "event-1")
    assert exc.value.status_code == 403


def test_list_for_event_success(event_repo, photo_repo, make_event, service):
    event = make_event()
    event_repo.get_by_id.return_value = event
    event_repo.is_attendee.return_value = True
    photo_repo.list_for_event.return_value = ([_photo()], False)
    photos, has_more = service.list_for_event("user-1", "event-1", offset=0, limit=24)
    assert photos[0].id == "photo-1"
    assert has_more is False


# --- get_photo_file ---


def test_get_photo_file_success(event_repo, photo_repo, file_service, make_event, service):
    event = make_event()
    event_repo.get_by_id.return_value = event
    event_repo.is_attendee.return_value = True
    photo_repo.get_by_id.return_value = _photo()
    file_service.read.return_value = b"image-bytes"
    assert service.get_photo_file("user-1", "event-1", "photo-1") == b"image-bytes"


def test_get_photo_file_not_member(event_repo, make_event, service):
    event = make_event()
    event_repo.get_by_id.return_value = event
    event_repo.is_attendee.return_value = False
    with pytest.raises(HTTPException) as exc:
        service.get_photo_file("user-99", "event-1", "photo-1")
    assert exc.value.status_code == 403


def test_get_photo_file_wrong_event(event_repo, photo_repo, make_event, service):
    event = make_event()
    event_repo.get_by_id.return_value = event
    event_repo.is_attendee.return_value = True
    photo_repo.get_by_id.return_value = _photo(event_id="other-event")
    with pytest.raises(HTTPException) as exc:
        service.get_photo_file("user-1", "event-1", "photo-1")
    assert exc.value.status_code == 404


def test_get_photo_file_missing_on_disk(event_repo, photo_repo, file_service, make_event, service):
    event = make_event()
    event_repo.get_by_id.return_value = event
    event_repo.is_attendee.return_value = True
    photo_repo.get_by_id.return_value = _photo()
    file_service.read.side_effect = FileNotFoundError("no file")
    with pytest.raises(HTTPException) as exc:
        service.get_photo_file("user-1", "event-1", "photo-1")
    assert exc.value.status_code == 404