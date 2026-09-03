from __future__ import annotations

import hashlib
import logging
import os
import uuid

from qdrant_client import QdrantClient
from qdrant_client.http.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PointStruct,
    VectorParams,
)

from app.domain.entities import BoundingBox, FaceEmbedding, MatchResult
from app.domain.interfaces import EmbeddingRepository

logger = logging.getLogger(__name__)

VECTOR_DIM = 512
UPSERT_BATCH_SIZE = 100


def _point_id(image_path: str) -> str:
    return hashlib.md5(image_path.encode()).hexdigest()


class QdrantProfileRepository:
    """One point per user in the `user_profiles` collection: id == user_id.

    Built on the same Qdrant client pattern as QdrantEmbeddingRepository but
    for the profile store (a single 512-dim centroid per user). Re-scanning
    simply upserts with the same point id, so the previous vector is replaced.
    """

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection_name: str = "user_profiles",
    ) -> None:
        self._url = url or os.environ.get("QDRANT_URL", "http://localhost:8090")
        self._api_key = api_key or os.environ.get("QDRANT_API_KEY") or None
        self._collection_name = collection_name
        self._client = QdrantClient(url=self._url, api_key=self._api_key)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        collections = self._client.get_collections().collections
        exists = any(c.name == self._collection_name for c in collections)
        if not exists:
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            )
            self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name="user_id",
                field_schema="keyword",
            )
            logger.info("Created Qdrant collection: %s", self._collection_name)
        else:
            logger.debug("Qdrant collection already exists: %s", self._collection_name)

    def upsert_profile(self, user_id: str, vector: list[float]) -> None:
        self._client.upsert(
            collection_name=self._collection_name,
            points=[
                PointStruct(
                    id=user_id,
                    vector=vector,
                    payload={"user_id": user_id},
                )
            ],
        )
        logger.info("Upserted face profile for user id=%s", user_id)

    def has_profile(self, user_id: str) -> bool:
        points = self._client.retrieve(collection_name=self._collection_name, ids=[user_id])
        return len(points) > 0

    def query_similar_restricted(
        self,
        query: list[float],
        user_ids: list[str],
        *,
        threshold: float,
        limit: int = 10,
    ) -> list[tuple[str, float]]:
        """Search profiles but only among `user_ids`.

        Matching (Phase 5) must never scan the whole `user_profiles` collection —
        it restricts the search to the current event's attendees first, then does
        the similarity search. Returns `(user_id, similarity)` for hits above
        `threshold`.
        """
        if not user_ids:
            return []
        query_filter = Filter(
            must=[FieldCondition(key="user_id", match=MatchAny(any=user_ids))]
        )
        response = self._client.query_points(
            collection_name=self._collection_name,
            query=query,
            query_filter=query_filter,
            limit=limit,
            score_threshold=threshold,
            with_payload=True,
            with_vectors=False,
        )
        results = [
            (str(point.payload.get("user_id", "")), point.score)
            for point in response.points
            if point.payload and point.payload.get("user_id")
        ]
        logger.debug(
            "restricted profile search among %d ids found %d above %.2f",
            len(user_ids),
            len(results),
            threshold,
        )
        return results


class EventFaceRepository:
    """Qdrant collection of per-face vectors from event photos.

    One point per detected face in an uploaded photo. The point id is a fresh
    UUID per face (a single photo can hold several faces), and every point's
    payload carries the Postgres ids it belongs to (`event_id`, `photo_id`)
    plus the face bounding box. Matching (Phase 5) filters on `event_id` then
    searches for attendee vectors — it never scans the whole collection.
    """

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection_name: str = "event_faces",
    ) -> None:
        self._url = url or os.environ.get("QDRANT_URL", "http://localhost:8090")
        self._api_key = api_key or os.environ.get("QDRANT_API_KEY") or None
        self._collection_name = collection_name or os.environ.get("QDRANT_EVENT_FACES_COLLECTION", "event_faces")
        self._client = QdrantClient(url=self._url, api_key=self._api_key)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        collections = self._client.get_collections().collections
        exists = any(c.name == self._collection_name for c in collections)
        if not exists:
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            )
            self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name="event_id",
                field_schema="keyword",
            )
            self._client.create_payload_index(
                collection_name=self._collection_name,
                field_name="photo_id",
                field_schema="keyword",
            )
            logger.info("Created Qdrant collection: %s", self._collection_name)
        else:
            logger.debug("Qdrant event_faces collection already exists: %s", self._collection_name)

    def upsert_faces(
        self,
        *,
        event_id: str,
        photo_id: str,
        embeddings: list[FaceEmbedding],
    ) -> int:
        """Upsert one point per face. Returns the number of faces stored.

        Each face gets a fresh UUID point id so one photo can contribute several
        points without overwriting each other. The same photo only ever produces
        a single set of points (Photo.status flips to `processed` after this).
        """
        points = [
            PointStruct(
                id=str(uuid.uuid4()),
                vector=emb.embedding,
                payload={
                    "event_id": event_id,
                    "photo_id": photo_id,
                    "bbox_x1": emb.bbox.x1,
                    "bbox_y1": emb.bbox.y1,
                    "bbox_x2": emb.bbox.x2,
                    "bbox_y2": emb.bbox.y2,
                    "face_score": emb.face_score,
                },
            )
            for emb in embeddings
        ]
        if not points:
            return 0
        self._client.upsert(collection_name=self._collection_name, points=points)
        logger.info("Upserted %d face point(s) event=%s photo=%s", len(points), event_id, photo_id)
        return len(points)

    def get_faces_for_photo(self, photo_id: str) -> list[FaceEmbedding]:
        """Return every face vector (with bbox) stored for a single photo.

        Used by matching (Phase 5): after ingestion upserts a photo's faces here,
        matching reads them back and, for each face vector, searches `user_profiles`
        restricted to the event's attendees.
        """
        query_filter = Filter(
            must=[FieldCondition(key="photo_id", match=MatchValue(value=photo_id))]
        )
        faces: list[FaceEmbedding] = []
        offset = None
        while True:
            page, offset = self._client.scroll(
                collection_name=self._collection_name,
                scroll_filter=query_filter,
                limit=1000,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            for point in page:
                p = point.payload or {}
                faces.append(
                    FaceEmbedding(
                        image_path="",
                        embedding=list(point.vector or []),
                        bbox=BoundingBox(
                            x1=int(p.get("bbox_x1", 0)),
                            y1=int(p.get("bbox_y1", 0)),
                            x2=int(p.get("bbox_x2", 0)),
                            y2=int(p.get("bbox_y2", 0)),
                        ),
                        face_score=float(p.get("face_score", 0.0)),
                    )
                )
            if offset is None:
                break
        logger.debug("loaded %d face(s) for photo=%s", len(faces), photo_id)
        return faces


class QdrantEmbeddingRepository(EmbeddingRepository):
    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        collection_name: str = "face_embeddings",
    ) -> None:
        self._url = url or os.environ.get("QDRANT_URL", "http://localhost:8090")
        self._api_key = api_key or os.environ.get("QDRANT_API_KEY") or None
        self._collection_name = collection_name or os.environ.get("QDRANT_COLLECTION_NAME", "face_embeddings")
        self._client = QdrantClient(url=self._url, api_key=self._api_key)
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        collections = self._client.get_collections().collections
        exists = any(c.name == self._collection_name for c in collections)
        if not exists:
            self._client.create_collection(
                collection_name=self._collection_name,
                vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
            )
            logger.info("Created Qdrant collection: %s", self._collection_name)
        else:
            logger.info("Qdrant collection already exists: %s", self._collection_name)

    def _to_point(self, emb: FaceEmbedding) -> PointStruct:
        return PointStruct(
            id=_point_id(emb.image_path),
            vector=emb.embedding,
            payload={
                "image_path": emb.image_path,
                "bbox_x1": emb.bbox.x1,
                "bbox_y1": emb.bbox.y1,
                "bbox_x2": emb.bbox.x2,
                "bbox_y2": emb.bbox.y2,
                "face_score": emb.face_score,
            },
        )

    def save_all(self, embeddings: list[FaceEmbedding]) -> None:
        self._client.recreate_collection(
            collection_name=self._collection_name,
            vectors_config=VectorParams(size=VECTOR_DIM, distance=Distance.COSINE),
        )
        self.upsert_batch(embeddings)
        logger.info("Saved %d embeddings (full replace) to Qdrant", len(embeddings))

    def upsert_batch(self, embeddings: list[FaceEmbedding]) -> None:
        for i in range(0, len(embeddings), UPSERT_BATCH_SIZE):
            batch = embeddings[i : i + UPSERT_BATCH_SIZE]
            points = [self._to_point(emb) for emb in batch]
            self._client.upsert(collection_name=self._collection_name, points=points)
        logger.debug("Upserted %d embeddings to Qdrant", len(embeddings))

    def delete_by_dir(self, dir_path: str) -> int:
        from qdrant_client.http.models import Filter, FieldCondition, MatchValue

        dir_path_norm = dir_path.replace("\\", "/").rstrip("/")

        all_ids = []
        offset = None
        while True:
            page, offset = self._client.scroll(
                collection_name=self._collection_name,
                limit=1000,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in page:
                p = point.payload or {}
                img = p.get("image_path", "").replace("\\", "/").rstrip("/")
                if img.startswith(dir_path_norm):
                    all_ids.append(point.id)
            if offset is None:
                break

        if all_ids:
            self._client.delete(
                collection_name=self._collection_name,
                points_selector=all_ids,
            )
        logger.info("Deleted %d embeddings for directory: %s", len(all_ids), dir_path)
        return len(all_ids)

    def get_indexed_paths(self, dir_path: str) -> set[str]:
        dir_path_norm = dir_path.replace("\\", "/").rstrip("/")
        paths = set()
        offset = None
        while True:
            page, offset = self._client.scroll(
                collection_name=self._collection_name,
                limit=1000,
                offset=offset,
                with_payload=True,
                with_vectors=False,
            )
            for point in page:
                p = point.payload or {}
                img = p.get("image_path", "").replace("\\", "/").rstrip("/")
                if img.startswith(dir_path_norm):
                    paths.add(p.get("image_path", ""))
            if offset is None:
                break
        return paths

    def load_all(self) -> list[FaceEmbedding]:
        results: list[FaceEmbedding] = []
        offset = None
        while True:
            page, offset = self._client.scroll(
                collection_name=self._collection_name,
                limit=1000,
                offset=offset,
                with_payload=True,
                with_vectors=True,
            )
            for point in page:
                p = point.payload or {}
                results.append(
                    FaceEmbedding(
                        image_path=p.get("image_path", ""),
                        embedding=list(point.vector or []),
                        bbox=BoundingBox(
                            x1=p.get("bbox_x1", 0),
                            y1=p.get("bbox_y1", 0),
                            x2=p.get("bbox_x2", 0),
                            y2=p.get("bbox_y2", 0),
                        ),
                        face_score=p.get("face_score", 0.0),
                    )
                )
            if offset is None:
                break
        logger.info("Loaded %d embeddings from Qdrant", len(results))
        return results

    def find_similar(self, query: list[float], threshold: float) -> list[MatchResult]:
        response = self._client.query_points(
            collection_name=self._collection_name,
            query=query,
            limit=10000,
            score_threshold=threshold,
        )
        results = [
            MatchResult(
                image_path=point.payload.get("image_path", ""),
                similarity=point.score,
                bbox=BoundingBox(
                    x1=point.payload.get("bbox_x1", 0),
                    y1=point.payload.get("bbox_y1", 0),
                    x2=point.payload.get("bbox_x2", 0),
                    y2=point.payload.get("bbox_y2", 0),
                ),
            )
            for point in response.points
        ]
        logger.debug("Found %d matches above threshold %.2f", len(results), threshold)
        return results
