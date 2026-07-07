#!/usr/bin/env python3
"""
CLI indexer: scans a directory of images, detects faces, and extracts embeddings.

Usage:
    python run_indexer.py [<source_dir> ...] [--embeddings <path>] [--threshold <float>]

    If no source_dir is provided, uses IMAGE_PATHS from .env (semicolon-separated).

Examples:
    python run_indexer.py ./my_photos
    python run_indexer.py ./photos1 ./photos2 --threshold 0.5
    python run_indexer.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lite_ml_service.main import run_indexer  # noqa: E402

if __name__ == "__main__":
    run_indexer(sys.argv[1:])
