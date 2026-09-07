import numpy as np
import pytest
from fastapi import HTTPException

from app.domain.entities import BoundingBox, FaceEmbedding
from app.services.profile_service import ProfileService


@pytest.fixture
def service(embedder, profile_repo):
    return ProfileService(embedder, profile_repo)


def _face(vector):
    return FaceEmbedding(
        image_path="",
        embedding=vector,
        bbox=BoundingBox(0, 0, 10, 10),
        face_score=1.0,
    )


def test_enroll_success(embedder, profile_repo, service):
    embedder.detect_and_embed.return_value = [_face([1.0, 0.0])]
    count = service.enroll("user-1", [b"image1"])
    assert count == 1
    profile_repo.upsert_profile.assert_called_once()
    stored = profile_repo.upsert_profile.call_args.args[1]
    assert np.allclose(stored, [1.0, 0.0])


def test_enroll_multi_image_centroid(embedder, profile_repo, service):
    embedder.detect_and_embed.side_effect = [
        [_face([1.0, 2.0, 3.0])],
        [_face([2.0, 4.0, 6.0])],
    ]
    count = service.enroll("user-1", [b"image1", b"image2"])
    assert count == 2
    profile_repo.upsert_profile.assert_called_once()
    stored = profile_repo.upsert_profile.call_args.args[1]
    assert np.allclose(stored, [1.5, 3.0, 4.5])


def test_enroll_deduplicates_face_found(embedder, profile_repo, service):
    # 2 images, one with 2 faces and one with 1 face => centroid of all 3 vectors
    embedder.detect_and_embed.side_effect = [
        [_face([0.0, 0.0]), _face([10.0, 10.0])],
        [_face([2.0, 2.0])],
    ]
    count = service.enroll("user-1", [b"image1", b"image2"])
    assert count == 3
    stored = profile_repo.upsert_profile.call_args.args[1]
    assert np.allclose(stored, [4.0, 4.0])


def test_enroll_no_faces(embedder, profile_repo, service):
    embedder.detect_and_embed.return_value = []
    with pytest.raises(HTTPException) as exc:
        service.enroll("user-1", [b"image1"])
    assert exc.value.status_code == 422
    assert "No face detected" in exc.value.detail
    profile_repo.upsert_profile.assert_not_called()


def test_enroll_corrupt_image(embedder, profile_repo, service):
    embedder.detect_and_embed.side_effect = ValueError("cannot decode")
    with pytest.raises(HTTPException) as exc:
        service.enroll("user-1", [b"not-an-image"])
    assert exc.value.status_code == 422
    assert "could not be decoded" in exc.value.detail
    profile_repo.upsert_profile.assert_not_called()


def test_has_profile_true(profile_repo, service):
    profile_repo.has_profile.return_value = True
    assert service.has_profile("user-1") is True


def test_has_profile_false(profile_repo, service):
    profile_repo.has_profile.return_value = False
    assert service.has_profile("user-1") is False