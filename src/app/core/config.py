from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = src/app/core -> three levels up. Loads .env regardless of CWD.
_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = "Immich Lite"
    app_version: str = "0.1.0"

    database_url: str = "postgresql+psycopg2://immich:immich@localhost:5433/immich_lite"

    qdrant_url: str = "http://localhost:8090"
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "face_embeddings"

    model_name: str = "buffalo_l"
    detection_threshold: float = 0.5
    similarity_threshold: float = 0.5

    output_root: str = "output"

    # Comma-separated list of allowed browser origins for CORS (e.g. the Next.js frontend).
    cors_origins: str = "http://localhost:3000"

    # Logging. log_level is one of DEBUG/INFO/WARNING/ERROR; "" disables structured callbacks.
    log_level: str = "INFO"
    log_file: str = "logs/app.log"
    log_max_bytes: int = 5 * 1024 * 1024
    log_backup_count: int = 3

    # Loaded from the JWT_SECRET env var / .env. None means "not configured" —
    # callers should refuse or use a dev-only fallback, never a hardcoded secret here.
    jwt_secret: str | None = os.getenv("JWT_SECRET")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expires_minutes: int = int(os.getenv("JWT_EXPIRES_MINUTES", 60 * 24 * 7))  # 7 days


@lru_cache
def get_settings() -> Settings:
    return Settings()
