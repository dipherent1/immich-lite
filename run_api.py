#!/usr/bin/env python3
"""
FastAPI server for face matching.

Usage:
    python run_api.py [--embeddings <path>] [--output <dir>] [--threshold <float>]
                      [--host <host>] [--port <port>]

Examples:
    python run_api.py
    python run_api.py --embeddings ./data/embeddings.json --threshold 0.5 --port 8000
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from lite_ml_service.main import run_api  # noqa: E402

if __name__ == "__main__":
    run_api(sys.argv[1:])
