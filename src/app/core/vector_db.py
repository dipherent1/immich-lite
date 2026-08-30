from __future__ import annotations

import hashlib
import logging
import os

from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, PointStruct, VectorParams

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
