from __future__ import annotations

import logging
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from tqdm import tqdm

from lite_ml_service.domain.entities import IndexerConfig, MatcherConfig, MatchResult
from lite_ml_service.domain.interfaces import EmbeddingProvider, EmbeddingRepository, FileService

logger = logging.getLogger(__name__)

EMBED_BATCH_SIZE = 32


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

    def run(self, overwrite: bool = True) -> int:
        image_paths = self._file_service.collect_images(
            str(self._config.source_dir), self._config.image_extensions
        )
        if not image_paths:
            logger.warning("No images found in %s", self._config.source_dir)
            return 0

        dir_path = str(self._config.source_dir)
        if overwrite:
            deleted = self._repository.delete_by_dir(dir_path)
            if deleted:
                logger.info("Cleared %d old embeddings for %s", deleted, dir_path)
        else:
            indexed = self._repository.get_indexed_paths(dir_path)
            before = len(image_paths)
            image_paths = [p for p in image_paths if p not in indexed]
            skipped_existing = before - len(image_paths)
            if skipped_existing:
                logger.info("Skipping %d already-indexed images in %s", skipped_existing, dir_path)
            if not image_paths:
                logger.info("All images already indexed in %s", dir_path)
                return 0

        all_embeddings: list = []
        skipped = 0
        batch: list = []

        pbar = tqdm(image_paths, desc=f"Embedding {Path(dir_path).name}", unit="img")
        for img_path in pbar:
            try:
                image_bytes = Path(img_path).read_bytes()
                faces = self._embedder.detect_and_embed(image_bytes)
            except Exception:
                logger.exception("Failed to process %s", img_path)
                skipped += 1
                continue

            for emb in faces:
                emb.image_path = img_path
            batch.extend(faces)
            all_embeddings.extend(faces)

            if len(batch) >= EMBED_BATCH_SIZE:
                self._repository.upsert_batch(batch)
                batch.clear()

            pbar.set_postfix(faces=len(all_embeddings), skip=skipped)

        if batch:
            self._repository.upsert_batch(batch)

        pbar.close()

        processed = len(image_paths) - skipped
        logger.info(
            "Indexing complete: %d images processed, %d faces indexed, %d skipped",
            processed,
            len(all_embeddings),
            skipped,
        )
        return len(all_embeddings)


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

        meta_path = self._write_metadata(matches_dir, name, source_path, match_results)
        zip_path = self._create_zip(matches_dir, name, source_path, meta_path)

        logger.info(
            "Matched %d images for '%s' (threshold=%.2f)",
            len(match_results),
            name,
            self._config.similarity_threshold,
        )

        return {
            "name": name,
            "source_image": source_path,
            "zip_file": zip_path,
            "metadata_file": meta_path,
            "matches": match_results,
            "matched_count": len(match_results),
        }

    def _write_metadata(self, matches_dir: Path, name: str, source_path: str, match_results: list[dict]) -> str:
        meta_path = str(matches_dir.parent / f"{name}_metadata.txt")
        lines = [
            f"Match Results for: {name}",
            f"Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC')}",
            f"Source Image: {source_path}",
            f"Total Matches: {len(match_results)}",
            f"Similarity Threshold: {self._config.similarity_threshold}",
            "",
            "=" * 70,
            "",
        ]
        for i, m in enumerate(match_results, 1):
            pct = round(m["similarity"] * 100, 2)
            bbox = m["bounding_box"]
            lines.extend([
                f"[{i}] {pct}%",
                f"    File: {Path(m['image_path']).name}",
                f"    Absolute Path: {m['image_path']}",
                f"    Bounding Box: ({bbox['x1']}, {bbox['y1']}) - ({bbox['x2']}, {bbox['y2']})",
                "",
            ])
        Path(meta_path).write_text("\n".join(lines), encoding="utf-8")
        logger.info("Created metadata: %s", meta_path)
        return meta_path

    def _create_zip(self, matches_dir: Path, name: str, source_path: str, meta_path: str) -> str:
        zip_path = str(matches_dir.parent / f"{name}.zip")
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            zf.write(source_path, "source/source.jpg")
            zf.write(meta_path, f"{name}_metadata.txt")
            for m in matches_dir.iterdir():
                if m.is_file() and m.suffix.lower() in {
                    ".jpg", ".jpeg", ".png", ".webp", ".bmp",
                    ".heic", ".heif", ".tiff", ".tif", ".gif", ".avif",
                }:
                    zf.write(str(m), f"matches/{m.name}")
        logger.info("Created zip: %s", zip_path)
        return zip_path

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
