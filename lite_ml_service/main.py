from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

from lite_ml_service.application.services import IndexerService, MatcherService
from lite_ml_service.domain.entities import IndexerConfig, MatcherConfig
from lite_ml_service.domain.interfaces import EmbeddingRepository
from lite_ml_service.infrastructure.embedding import InsightFaceEmbeddingProvider
from lite_ml_service.infrastructure.file_io import LocalFileService
from lite_ml_service.infrastructure.qdrant_storage import QdrantEmbeddingRepository
from lite_ml_service.infrastructure.storage import JsonEmbeddingRepository
from lite_ml_service.presentation.api import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("lite_ml_service")

load_dotenv()

CONFIG_FILE = Path(__file__).resolve().parent.parent / "config.yml"


def load_config() -> dict:
    if CONFIG_FILE.exists():
        with open(CONFIG_FILE, encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}


config = load_config()


def create_repository(embeddings_path: str) -> EmbeddingRepository:
    qdrant_url = os.environ.get("QDRANT_URL")
    if qdrant_url:
        try:
            collection = os.environ.get("QDRANT_COLLECTION_NAME", config.get("qdrant_collection_name", "face_embeddings"))
            logger.info("Using Qdrant storage: %s", qdrant_url)
            return QdrantEmbeddingRepository(url=qdrant_url, collection_name=collection)
        except Exception:
            logger.exception("Failed to connect to Qdrant at %s", qdrant_url, exc_info=True)
            logger.warning("Falling back to JSON file storage")

    logger.info("Using JSON file storage: %s", embeddings_path)
    return JsonEmbeddingRepository(embeddings_path)


def build_indexer(source_dir: str, embeddings_path: str, threshold: float = 0.5) -> IndexerService:
    model_name = os.environ.get("MODEL_NAME", config.get("model_name", "buffalo_l"))
    return IndexerService(
        embedding_provider=InsightFaceEmbeddingProvider(model_name=model_name, detection_threshold=threshold),
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
    model_name = os.environ.get("MODEL_NAME", config.get("model_name", "buffalo_l"))
    embedder = InsightFaceEmbeddingProvider(model_name=model_name, detection_threshold=detection_threshold)
    repo = create_repository(embeddings_path)
    file_svc = LocalFileService()

    matcher_config = MatcherConfig(
        indexed_embeddings_path=Path(embeddings_path),
        output_root=Path(output_root),
        similarity_threshold=similarity_threshold,
        detection_threshold=detection_threshold,
    )

    svc = MatcherService(
        embedding_provider=embedder,
        repository=repo,
        file_service=file_svc,
        config=matcher_config,
    )
    return svc, embedder


def run_indexer(args: list[str]) -> None:
    embeddings_path = "embeddings.json"
    threshold = 0.5
    source_dirs: list[str] = []

    i = 0
    while i < len(args):
        if args[i] == "--embeddings" and i + 1 < len(args):
            embeddings_path = args[i + 1]
            i += 2
        elif args[i] == "--threshold" and i + 1 < len(args):
            threshold = float(args[i + 1])
            i += 2
        else:
            source_dirs.append(args[i])
            i += 1

    if not source_dirs:
        image_paths = config.get("image_paths", [])
        if image_paths:
            source_dirs = [str(p) for p in image_paths]

    if not source_dirs:
        print("Usage: python -m lite_ml_service index <source_dir> [<source_dir2> ...] [--embeddings <path>] [--threshold <float>]")
        print("  Or set image_paths in config.yml")
        sys.exit(1)

    total = 0
    for source_dir in source_dirs:
        logger.info("Indexing: %s", source_dir)
        indexer = build_indexer(source_dir, embeddings_path, threshold)
        count = indexer.run()
        print(f"Indexed {count} faces from {source_dir}")
        total += count

    print(f"Total: {total} faces indexed from {len(source_dirs)} directory(ies)")


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
        print("  index <source_dir> [<source_dir2> ...]  -- Index faces from directory(ies)")
        print("  api                                      -- Start the matching API server")
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
