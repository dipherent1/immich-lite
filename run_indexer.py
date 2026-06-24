#!/usr/bin/env python3
"""
CLI indexer: scans a directory of images, detects faces, and extracts embeddings.

Usage:
    python run_indexer.py <source_dir> [--embeddings <path>] [--threshold <float>]

Examples:
    python run_indexer.py ./my_photos
    python run_indexer.py ./my_photos --embeddings ./data/embeddings.json --threshold 0.5
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lite_ml_service.main import run_indexer  # noqa: E402

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    run_indexer(sys.argv[1:])
