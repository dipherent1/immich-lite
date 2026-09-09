#!/usr/bin/env python3
"""
CLI indexer: scans directories of images, detects faces, and extracts embeddings.

Usage:
    python run_indexer.py [<source_dir> ...] [--add] [--embeddings <path>] [--threshold <float>]

    If no source_dir is provided, uses image_paths from config.yml.

    --add    Additive mode: don't clear existing embeddings for each directory.

Examples:
    python run_indexer.py
    python run_indexer.py ./my_photos
    python run_indexer.py --add ./new_photos
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lite_ml_service.main import run_indexer  # noqa: E402

if __name__ == "__main__":
    run_indexer(sys.argv[1:])
