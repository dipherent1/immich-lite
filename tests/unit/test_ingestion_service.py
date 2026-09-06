import pytest

from app.models.photo import Photo
from app.services.ingestion_service import IngestionService


@pytest.fixture
def service(embedder, photo_repo, event_face_repo, file_service):
    return IngestionService(embedder, photo_repo, event_face_repo, file_service)


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


def test_process_success(embedder, event_face_repo, photo_repo, file_service, service):
    file_service.read.return_value = b"bytes"
    embedder.detect_and_embed.return_value = ["face-a", "face-b"]  # 2 faces
    event_face_repo.upsert_faces.return_value = 2

    count = service.process(_photo())

    assert count == 2
    event_face_repo.upsert_faces.assert_called_once_with(
        event_id="event-1", photo_id="photo-1", embeddings=["face-a", "face-b"]
    )
    photo_repo.set_status.assert_called_once_with("photo-1", "processed", processed=True)


def test_process_no_faces_marks_processed(embedder, event_face_repo, photo_repo, file_service, service):
    file_service.read.return_value = b"bytes"
    embedder.detect_and_embed.return_value = []
    event_face_repo.upsert_faces.return_value = 0
    assert service.process(_photo()) == 0
    photo_repo.set_status.assert_called_once_with("photo-1", "processed", processed=True)


def test_process_embedder_failure_marks_failed(embedder, photo_repo, file_service, service):
    file_service.read.return_value = b"bytes"
    embedder.detect_and_embed.side_effect = RuntimeError("model exploded")
    with pytest.raises(RuntimeError):
        service.process(_photo())
    photo_repo.set_status.assert_called_once_with("photo-1", "failed")


def test_process_missing_file_marks_failed(file_service, photo_repo, service):
    file_service.read.side_effect = FileNotFoundError("no such file")
    with pytest.raises(FileNotFoundError):
        service.process(_photo())
    photo_repo.set_status.assert_called_once_with("photo-1", "failed")


def test_process_by_id_success(embedder, photo_repo, file_service, service):
    file_service.read.return_value = b"bytes"
    embedder.detect_and_embed.return_value = []
    photo = _photo()
    photo_repo.get_by_id.return_value = photo
    result = service.process_by_id("photo-1")
    assert result.id == "photo-1"


def test_process_by_id_not_found(photo_repo, service):
    photo_repo.get_by_id.return_value = None
    with pytest.raises(FileNotFoundError):
        service.process_by_id("missing")