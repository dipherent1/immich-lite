from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.models.photo import Photo
from app.services.public_event_service import PUBLIC_PREVIEW_PX, PublicEventService


@pytest.fixture
def service(event_repo, photo_repo, file_service):
    return PublicEventService(event_repo, photo_repo, file_service)


def _photo(**kw):
    defaults = {
        "id": "photo-1",
        "event_id": "event-1",
        "uploader_user_id": "u",
        "storage_path": "photos/event-1/photo-1.jpg",
        "status": "processed",
    }
    defaults.update(kw)
    return Photo(**defaults)


def test_unknown_token_404(service, event_repo):
    event_repo.get_by_token.return_value = None
    with pytest.raises(HTTPException) as exc:
        service.event_view("nope")
    assert exc.value.status_code == 404


def test_ended_event_410(service, event_repo, make_event):
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    event_repo.get_by_token.return_value = make_event(expires_at=now - timedelta(minutes=1))
    with pytest.raises(HTTPException) as exc:
        service.list_photos("tok")
    assert exc.value.status_code == 410


def test_event_view_counts_only_processed(service, event_repo, photo_repo, make_event):
    event_repo.get_by_token.return_value = make_event()
    photo_repo.count_for_event.return_value = 3
    event, count = service.event_view("tok")
    assert count == 3
    photo_repo.count_for_event.assert_called_once_with("event-1", status="processed")


def test_list_requests_processed_only(service, event_repo, photo_repo, make_event):
    event_repo.get_by_token.return_value = make_event()
    photo_repo.list_for_event.return_value = ([_photo()], False)
    service.list_photos("tok", offset=5, limit=10)
    photo_repo.list_for_event.assert_called_once_with(
        "event-1", offset=5, limit=10, status="processed"
    )


@pytest.mark.parametrize(
    "photo",
    [None, _photo(status="pending"), _photo(status="failed"), _photo(event_id="other")],
)
def test_preview_rejects_missing_unprocessed_or_foreign_photo(
    service, event_repo, photo_repo, make_event, photo
):
    event_repo.get_by_token.return_value = make_event()
    photo_repo.get_by_id.return_value = photo
    with pytest.raises(HTTPException) as exc:
        service.preview("tok", "photo-1")
    assert exc.value.status_code == 404


def test_preview_generates_at_public_size_then_caches(
    service, event_repo, photo_repo, file_service, make_event, monkeypatch
):
    event_repo.get_by_token.return_value = make_event()
    photo_repo.get_by_id.return_value = _photo()
    file_service.read.side_effect = [FileNotFoundError("no cache"), b"original"]
    seen = {}

    def fake_preview(data, max_px):
        seen["args"] = (data, max_px)
        return b"small"

    monkeypatch.setattr("app.services.public_event_service._to_preview_jpeg", fake_preview)
    assert service.preview("tok", "photo-1") == b"small"
    assert seen["args"] == (b"original", PUBLIC_PREVIEW_PX) and PUBLIC_PREVIEW_PX == 800
    file_service.save_upload.assert_called_once_with(
        data=b"small", relative="previews/event-1/public-photo-1.jpg"
    )


def test_preview_uses_cache_without_touching_original(
    service, event_repo, photo_repo, file_service, make_event, monkeypatch
):
    event_repo.get_by_token.return_value = make_event()
    photo_repo.get_by_id.return_value = _photo()
    file_service.read.return_value = b"cached"
    boom = MagicMock(side_effect=AssertionError("must not re-render"))
    monkeypatch.setattr("app.services.public_event_service._to_preview_jpeg", boom)
    assert service.preview("tok", "photo-1") == b"cached"
    file_service.save_upload.assert_not_called()


def test_preview_missing_original_is_404(
    service, event_repo, photo_repo, file_service, make_event
):
    event_repo.get_by_token.return_value = make_event()
    photo_repo.get_by_id.return_value = _photo()
    file_service.read.side_effect = FileNotFoundError("gone")
    with pytest.raises(HTTPException) as exc:
        service.preview("tok", "photo-1")
    assert exc.value.status_code == 404


def test_preview_undecodable_original_is_422(
    service, event_repo, photo_repo, file_service, make_event, monkeypatch
):
    event_repo.get_by_token.return_value = make_event()
    photo_repo.get_by_id.return_value = _photo()
    file_service.read.side_effect = [FileNotFoundError("no cache"), b"junk"]
    monkeypatch.setattr(
        "app.services.public_event_service._to_preview_jpeg",
        MagicMock(side_effect=ValueError("bad image")),
    )
    with pytest.raises(HTTPException) as exc:
        service.preview("tok", "photo-1")
    assert exc.value.status_code == 422
