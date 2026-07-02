from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from lite_ml_service.domain.entities import IndexerConfig, MatcherConfig, MatchResult
from lite_ml_service.domain.interfaces import EmbeddingProvider, EmbeddingRepository, FileService

logger = logging.getLogger(__name__)


class IndexerService:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        repository: EmbeddingRepository,
        file_service: FileService,
        config: IndexerConfig,
    ) -> None:
        self._embedder = embedding_provider
        self._repository = repository
        self._file_service = file_service
        self._config = config

    def run(self) -> int:
        image_paths = self._file_service.collect_images(
            str(self._config.source_dir), self._config.image_extensions
        )
        if not image_paths:
            logger.warning("No images found in %s", self._config.source_dir)
            return 0

        skipped = 0
        all_embeddings: list = []

        for img_path in image_paths:
            try:
                image_bytes = Path(img_path).read_bytes()
                embeddings = self._embedder.detect_and_embed(image_bytes)
            except Exception:
                logger.exception("Failed to process %s", img_path)
                skipped += 1
                continue

            for emb in embeddings:
                emb.image_path = img_path
            all_embeddings.extend(embeddings)
            logger.info("Indexed %s: %d face(s)", img_path, len(embeddings))

        self._repository.save_all(all_embeddings)
        total_faces = len(all_embeddings)
        processed = len(image_paths) - skipped
        logger.info(
            "Indexing complete: %d images processed, %d faces indexed, %d skipped",
            processed,
            total_faces,
            skipped,
        )
        return total_faces


class MatcherService:
    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        repository: EmbeddingRepository,
        file_service: FileService,
        config: MatcherConfig,
    ) -> None:
        self._embedder = embedding_provider
        self._repository = repository
        self._file_service = file_service
        self._config = config

    def _build_response(self, matches: list[MatchResult], name: str, source_path: str) -> dict:
        matches_dir = self._config.output_root / name / "matches"
        self._file_service.ensure_directory(str(matches_dir))

        match_results = []
        for m in matches:
            dst = str(matches_dir / Path(m.image_path).name)
            self._file_service.copy_image(m.image_path, dst)
            match_results.append(
                {
                    "image_path": m.image_path,
                    "copied_to": dst,
                    "similarity": round(m.similarity, 4),
                    "bounding_box": {
                        "x1": m.bbox.x1,
                        "y1": m.bbox.y1,
                        "x2": m.bbox.x2,
                        "y2": m.bbox.y2,
                    },
                }
            )

        match_results.sort(key=lambda r: r["similarity"], reverse=True)

        logger.info(
            "Matched %d images for '%s' (threshold=%.2f)",
            len(match_results),
            name,
            self._config.similarity_threshold,
        )

        return {
            "name": name,
            "source_image": source_path,
            "matches": match_results,
            "matched_count": len(match_results),
        }

    def match(self, image_bytes: bytes, name: str) -> dict:
        output_dir = self._config.output_root / name
        source_dir = output_dir / "source"
        self._file_service.ensure_directory(str(source_dir))

        source_path = str(source_dir / "source.jpg")
        self._file_service.save_upload(image_bytes, source_path)

        query_embeddings = self._embedder.detect_and_embed(image_bytes)
        if not query_embeddings:
            return {
                "name": name,
                "source_image": source_path,
                "matches": [],
                "matched_count": 0,
                "error": "No face detected in the uploaded image",
            }

        query_emb = query_embeddings[0]

        matches: list[MatchResult] = self._repository.find_similar(
            query_emb.embedding, self._config.similarity_threshold
        )

        return self._build_response(matches, name, source_path)

    def match_multiple(self, all_image_bytes: list[bytes], name: str) -> dict:
        output_dir = self._config.output_root / name
        source_dir = output_dir / "source"
        self._file_service.ensure_directory(str(source_dir))

        source_path = str(source_dir / "source.jpg")

        all_vectors: list[list[float]] = []
        total_faces = 0
        for i, image_bytes in enumerate(all_image_bytes):
            if i == 0:
                self._file_service.save_upload(image_bytes, source_path)

            faces = self._embedder.detect_and_embed(image_bytes)
            for f in faces:
                all_vectors.append(f.embedding)
                total_faces += 1

        if not all_vectors:
            return {
                "name": name,
                "source_image": source_path,
                "matches": [],
                "matched_count": 0,
                "error": "No face detected in any of the uploaded images",
            }

        centroid = np.mean(all_vectors, axis=0).tolist()

        matches: list[MatchResult] = self._repository.find_similar(
            centroid, self._config.similarity_threshold
        )

        return self._build_response(matches, name, source_path)
