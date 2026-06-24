from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

from lite_ml_service.domain.entities import BoundingBox, FaceEmbedding, MatchResult
from lite_ml_service.domain.interfaces import EmbeddingRepository

logger = logging.getLogger(__name__)


class JsonEmbeddingRepository(EmbeddingRepository):
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)

    def save_all(self, embeddings: list[FaceEmbedding]) -> None:
        data = [
            {
                "image_path": emb.image_path,
                "embedding": emb.embedding,
                "bbox": [emb.bbox.x1, emb.bbox.y1, emb.bbox.x2, emb.bbox.y2],
                "face_score": emb.face_score,
            }
            for emb in embeddings
        ]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.info("Saved %d embeddings to %s", len(embeddings), self._path)

    def load_all(self) -> list[FaceEmbedding]:
        if not self._path.exists():
            logger.warning("Embeddings file not found: %s", self._path)
            return []

        data = json.loads(self._path.read_text(encoding="utf-8"))
        results = [
            FaceEmbedding(
                image_path=item["image_path"],
                embedding=item["embedding"],
                bbox=BoundingBox(*item["bbox"]),
                face_score=item["face_score"],
            )
            for item in data
        ]
        logger.info("Loaded %d embeddings from %s", len(results), self._path)
        return results

    def find_similar(self, query: list[float], threshold: float) -> list[MatchResult]:
        all_embeddings = self.load_all()
        if not all_embeddings:
            return []

        query_vec = np.array(query, dtype=np.float64)
        query_norm = query_vec / (np.linalg.norm(query_vec) + 1e-12)

        results: list[MatchResult] = []
        for emb in all_embeddings:
            stored_vec = np.array(emb.embedding, dtype=np.float64)
            stored_norm = stored_vec / (np.linalg.norm(stored_vec) + 1e-12)
            similarity = float(np.dot(query_norm, stored_norm))
            if similarity >= threshold:
                results.append(MatchResult(image_path=emb.image_path, similarity=similarity, bbox=emb.bbox))

        results.sort(key=lambda r: r.similarity, reverse=True)
        logger.debug("Found %d matches above threshold %.2f", len(results), threshold)
        return results
