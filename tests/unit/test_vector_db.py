import uuid

import pytest
from qdrant_client import QdrantClient

from app.core.vector_db import (
    VECTOR_DIM,
    EventFaceRepository,
    QdrantEmbeddingRepository,
    QdrantProfileRepository,
    _point_id,
)
from app.domain.entities import BoundingBox, FaceEmbedding


@pytest.fixture
def qdrant(monkeypatch):
    """Shared in-memory Qdrant instance so every class under test hits one client.

    The repository classes construct `QdrantClient(url=..., api_key=...)`
    themselves, so we swap the class for one that always returns the same
    in-memory client regardless of the url/api_key args.
    """
    client = QdrantClient(":memory:")

    def _factory(*args, **kwargs):
        return client

    monkeypatch.setattr("app.core.vector_db.QdrantClient", _factory)
    return client


def _vec(index: int) -> list[float]:
    """A unit vector with a single hot dimension (`index` < VECTOR_DIM)."""
    v = [0.0] * VECTOR_DIM
    v[index] = 1.0
    return v


def _face(path: str, index: int, face_score: float = 1.0) -> FaceEmbedding:
    return FaceEmbedding(
        image_path=path,
        embedding=_vec(index),
        bbox=BoundingBox(x1=1, y1=2, x2=3, y2=4),
        face_score=face_score,
    )


def _uid() -> str:
    return str(uuid.uuid4())


def _count(qdrant, collection: str) -> int:
    return qdrant.count(collection_name=collection).count


class TestQdrantProfileRepository:
    def test_has_profile_false_for_missing_user(self, qdrant):
        repo = QdrantProfileRepository()
        assert repo.has_profile(_uid()) is False

    def test_upsert_then_has_profile(self, qdrant):
        repo = QdrantProfileRepository()
        user_id = _uid()
        repo.upsert_profile(user_id, _vec(0))
        assert repo.has_profile(user_id) is True

    def test_rescan_replaces_vector_without_duplicate_point(self, qdrant):
        repo = QdrantProfileRepository()
        user_id = _uid()
        repo.upsert_profile(user_id, _vec(1))
        repo.upsert_profile(user_id, _vec(0))
        assert _count(qdrant, "user_profiles") == 1
        hits = repo.query_similar_restricted(_vec(0), [user_id], threshold=0.9)
        assert hits == [(user_id, pytest.approx(1.0, abs=1e-6))]
        assert repo.query_similar_restricted(_vec(1), [user_id], threshold=0.9) == []

    def test_query_scoped_to_user_ids(self, qdrant):
        repo = QdrantProfileRepository()
        a, b = _uid(), _uid()
        repo.upsert_profile(a, _vec(0))
        repo.upsert_profile(b, _vec(0))
        hits = repo.query_similar_restricted(_vec(0), [b], threshold=0.9)
        ids = {uid for uid, _ in hits}
        assert ids == {b}
        assert a not in ids

    def test_query_respects_threshold(self, qdrant):
        repo = QdrantProfileRepository()
        user_id = _uid()
        repo.upsert_profile(user_id, _vec(0))
        assert len(repo.query_similar_restricted(_vec(0), [user_id], threshold=0.9)) == 1
        assert len(repo.query_similar_restricted(_vec(0), [user_id], threshold=0.5)) == 1

    def test_query_above_threshold_filters_other_vector(self, qdrant):
        repo = QdrantProfileRepository()
        user_id = _uid()
        repo.upsert_profile(user_id, _vec(0))
        assert repo.query_similar_restricted(_vec(1), [user_id], threshold=0.6) == []

    def test_query_empty_user_ids_returns_nothing(self, qdrant):
        repo = QdrantProfileRepository()
        repo.upsert_profile(_uid(), _vec(0))
        assert repo.query_similar_restricted(_vec(0), [], threshold=0.0) == []


class TestEventFaceRepository:
    def test_upsert_faces_returns_count_and_persists(self, qdrant):
        repo = EventFaceRepository()
        event_id, photo_id = _uid(), _uid()
        n = repo.upsert_faces(
            event_id=event_id,
            photo_id=photo_id,
            embeddings=[_face("a.jpg", 0, face_score=0.9), _face("b.jpg", 1, face_score=0.8)],
        )
        assert n == 2
        assert _count(qdrant, "event_faces") == 2

    def test_upsert_faces_empty_returns_zero(self, qdrant):
        repo = EventFaceRepository()
        assert repo.upsert_faces(event_id=_uid(), photo_id=_uid(), embeddings=[]) == 0

    def test_get_faces_for_photo_roundtrip(self, qdrant):
        repo = EventFaceRepository()
        event_id, photo_id = _uid(), _uid()
        repo.upsert_faces(
            event_id=event_id,
            photo_id=photo_id,
            embeddings=[_face("a.jpg", 0, face_score=0.9), _face("b.jpg", 1, face_score=0.8)],
        )
        faces = repo.get_faces_for_photo(photo_id)
        assert [f.bbox for f in faces] == [BoundingBox(1, 2, 3, 4), BoundingBox(1, 2, 3, 4)]
        assert sorted(f.face_score for f in faces) == [0.8, 0.9]
        assert sorted(f.embedding.index(1.0) for f in faces) == [0, 1]

    def test_get_faces_scoped_by_photo(self, qdrant):
        repo = EventFaceRepository()
        pa, pb = _uid(), _uid()
        repo.upsert_faces(event_id=_uid(), photo_id=pa, embeddings=[_face("a.jpg", 0)])
        repo.upsert_faces(event_id=_uid(), photo_id=pb, embeddings=[_face("b.jpg", 1)])
        assert len(repo.get_faces_for_photo(pa)) == 1
        assert len(repo.get_faces_for_photo(pb)) == 1
        assert repo.get_faces_for_photo(_uid()) == []

    def test_point_payload_carries_event_and_photo_ids(self, qdrant):
        repo = EventFaceRepository()
        event_id, photo_id = _uid(), _uid()
        repo.upsert_faces(event_id=event_id, photo_id=photo_id, embeddings=[_face("a.jpg", 0)])
        points, _ = qdrant.scroll(
            collection_name="event_faces",
            scroll_filter=None,
            with_payload=True,
            limit=10,
        )
        assert len(points) == 1
        payload = points[0].payload
        assert payload["event_id"] == event_id
        assert payload["photo_id"] == photo_id


class TestQdrantEmbeddingRepository:
    def test_point_id_is_stable_md5(self):
        assert _point_id("a.jpg") == _point_id("a.jpg")
        assert _point_id("a.jpg") != _point_id("b.jpg")

    def test_upsert_batch_and_load_all(self, qdrant):
        repo = QdrantEmbeddingRepository()
        repo.upsert_batch([_face("photos/a.jpg", 0), _face("photos/b.png", 1)])
        loaded = repo.load_all()
        assert {f.image_path for f in loaded} == {"photos/a.jpg", "photos/b.png"}
        assert {f.embedding.index(1.0) for f in loaded} == {0, 1}

    def test_save_all_full_replace(self, qdrant):
        repo = QdrantEmbeddingRepository()
        repo.upsert_batch([_face("photos/old.jpg", 0)])
        repo.save_all([_face("photos/new.jpg", 1)])
        loaded = repo.load_all()
        assert len(loaded) == 1
        assert loaded[0].image_path == "photos/new.jpg"

    def test_find_similar_returns_hit_with_similarity_and_bbox(self, qdrant):
        repo = QdrantEmbeddingRepository()
        repo.upsert_batch([_face("photos/a.jpg", 0), _face("photos/b.jpg", 1)])
        hits = repo.find_similar(_vec(0), threshold=0.9)
        assert len(hits) == 1
        assert hits[0].image_path == "photos/a.jpg"
        assert hits[0].similarity == pytest.approx(1.0, abs=1e-6)
        assert hits[0].bbox == BoundingBox(1, 2, 3, 4)

    def test_find_similar_below_threshold_filters_out(self, qdrant):
        repo = QdrantEmbeddingRepository()
        repo.upsert_batch([_face("photos/a.jpg", 0)])
        assert repo.find_similar(_vec(1), threshold=0.6) == []

    def test_delete_by_dir_deletes_only_matching_prefix(self, qdrant):
        repo = QdrantEmbeddingRepository()
        repo.upsert_batch(
            [
                _face("photos/2024/x.jpg", 0),
                _face("photos/2025/y.jpg", 1),
                _face("other/z.jpg", 2),
            ]
        )
        assert repo.delete_by_dir("photos/2024") == 1
        remaining = {f.image_path for f in repo.load_all()}
        assert remaining == {"photos/2025/y.jpg", "other/z.jpg"}

    def test_delete_by_dir_empty_matches_returns_zero(self, qdrant):
        repo = QdrantEmbeddingRepository()
        repo.upsert_batch([_face("photos/asd/ok.jpg", 1)])
        assert repo.delete_by_dir("photos/zzz") == 0

    def test_get_indexed_paths(self, qdrant):
        repo = QdrantEmbeddingRepository()
        repo.upsert_batch([_face("photos/2024/x.jpg", 0), _face("other/z.jpg", 1)])
        assert repo.get_indexed_paths("photos/2024") == {"photos/2024/x.jpg"}