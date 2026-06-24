from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from lite_ml_service.application.services import IndexerService, MatcherService
from lite_ml_service.domain.entities import IndexerConfig, MatcherConfig
from lite_ml_service.domain.interfaces import EmbeddingRepository
from lite_ml_service.infrastructure.embedding import InsightFaceEmbeddingProvider
from lite_ml_service.infrastructure.file_io import LocalFileService
from lite_ml_service.infrastructure.storage import JsonEmbeddingRepository
from lite_ml_service.presentation.api import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("lite_ml_service")

load_dotenv()


def create_repository(embeddings_path: str) -> EmbeddingRepository:
    database_url = os.environ.get("DATABASE_URL")
    if database_url:
        try:
            from lite_ml_service.infrastructure.postgres_storage import (
                PostgresEmbeddingRepository,
            )

            logger.info("Using PostgreSQL storage")
            return PostgresEmbeddingRepository(database_url)
        except Exception:
            logger.exception(
                "Failed to connect to PostgreSQL at %s", database_url, exc_info=True
            )
            logger.warning("Falling back to JSON file storage")

    logger.info("Using JSON file storage: %s", embeddings_path)
    return JsonEmbeddingRepository(embeddings_path)


def build_indexer(source_dir: str, embeddings_path: str, threshold: float = 0.5) -> IndexerService:
    return IndexerService(
        embedding_provider=InsightFaceEmbeddingProvider(detection_threshold=threshold),
        repository=create_repository(embeddings_path),
        file_service=LocalFileService(),
        config=IndexerConfig(
            source_dir=Path(source_dir),
            embeddings_path=Path(embeddings_path),
            detection_threshold=threshold,
        ),
    )


def build_matcher(
    embeddings_path: str,
    output_root: str,
    similarity_threshold: float = 0.5,
    detection_threshold: float = 0.5,
) -> tuple[MatcherService, object]:
    embedder = InsightFaceEmbeddingProvider(detection_threshold=detection_threshold)
    repo = create_repository(embeddings_path)
    file_svc = LocalFileService()

    config = MatcherConfig(
        indexed_embeddings_path=Path(embeddings_path),
        output_root=Path(output_root),
        similarity_threshold=similarity_threshold,
        detection_threshold=detection_threshold,
    )

    svc = MatcherService(
        embedding_provider=embedder,
        repository=repo,
        file_service=file_svc,
        config=config,
    )
    return svc, embedder


def run_indexer(args: list[str]) -> None:
    if len(args) < 1:
        print("Usage: python -m lite_ml_service index <source_dir> [--embeddings <path>] [--threshold <float>]")
        sys.exit(1)

    source_dir = args[0]
    embeddings_path = "embeddings.json"
    threshold = 0.5

    i = 1
    while i < len(args):
        if args[i] == "--embeddings" and i + 1 < len(args):
            embeddings_path = args[i + 1]
            i += 2
        elif args[i] == "--threshold" and i + 1 < len(args):
            threshold = float(args[i + 1])
            i += 2
        else:
            i += 1

    indexer = build_indexer(source_dir, embeddings_path, threshold)
    total = indexer.run()
    print(f"Indexed {total} faces from {source_dir}")


def run_api(args: list[str]) -> None:
    import uvicorn

    embeddings_path = "embeddings.json"
    output_root = "output"
    similarity_threshold = 0.5
    host = "0.0.0.0"
    port = 8000

    i = 0
    while i < len(args):
        if args[i] == "--embeddings" and i + 1 < len(args):
            embeddings_path = args[i + 1]
            i += 2
        elif args[i] == "--output" and i + 1 < len(args):
            output_root = args[i + 1]
            i += 2
        elif args[i] == "--threshold" and i + 1 < len(args):
            similarity_threshold = float(args[i + 1])
            i += 2
        elif args[i] == "--host" and i + 1 < len(args):
            host = args[i + 1]
            i += 2
        elif args[i] == "--port" and i + 1 < len(args):
            port = int(args[i + 1])
            i += 2
        else:
            i += 1

    matcher_svc, _ = build_matcher(embeddings_path, output_root, similarity_threshold)
    app = create_app(matcher_svc)
    logger.info("Starting API on %s:%d (embeddings=%s, output=%s)", host, port, embeddings_path, output_root)
    uvicorn.run(app, host=host, port=port)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python -m lite_ml_service [index|api] <args>")
        print("  index <source_dir>  -- Index faces from a directory")
        print("  api                 -- Start the matching API server")
        sys.exit(1)

    command = sys.argv[1]
    if command == "index":
        run_indexer(sys.argv[2:])
    elif command == "api":
        run_api(sys.argv[1:])
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
