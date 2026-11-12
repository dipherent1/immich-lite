from __future__ import annotations

from functools import lru_cache
import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Project root = backend/src/app/core -> four levels up. Loads .env regardless of CWD.
_PROJECT_ROOT = Path(__file__).resolve().parents[4]
load_dotenv(_PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    app_name: str = "Immich Lite"
    app_version: str = "0.1.0"

    database_url: str = "postgresql+psycopg2://immich:immich@localhost:5433/immich_lite"

    qdrant_url: str = "http://localhost:8190"
    qdrant_api_key: str | None = None
    qdrant_collection_name: str = "face_embeddings"

    # AMQP broker for Celery (job queue) and the worker→API notification exchange.
    # `%2F` is the `/` vhost, spelled explicitly so pika, kombu and aio-pika
    # all parse it the same way (pika treats a bare `//` as an empty vhost).
    rabbitmq_url: str = "amqp://immich:immich@localhost:5672/%2F"

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

    # Event lifetime: every new event is deleted (with its photos, previews and
    # face vectors) this many hours after it is created.
    event_lifetime_hours: int = int(os.getenv("EVENT_LIFETIME_HOURS", "6"))
    # Attendees get an "ending soon" notification this many minutes before deletion.
    event_expiry_warning_minutes: int = int(os.getenv("EVENT_EXPIRY_WARNING_MINUTES", "20"))
    # How often the worker checks for events to warn about / delete.
    event_sweep_interval_seconds: int = int(os.getenv("EVENT_SWEEP_INTERVAL_SECONDS", "60"))

    # Rate limiting. Redis is the shared counter store (required for multi-worker deployments).
    # Falls back to in-memory if REDIS_URL is not set (single-process dev only).
    redis_url: str = os.getenv("REDIS_URL", "memory://")
    # Global limit applied to every route (format: "N/period", period = second|minute|hour).
    rate_limit_global: str = os.getenv("RATE_LIMIT_GLOBAL", "150/minute")
    # Tighter limit for auth endpoints (login, register) to slow brute-force attempts.
    rate_limit_auth: str = os.getenv("RATE_LIMIT_AUTH", "10/minute")


@lru_cache
def get_settings() -> Settings:
    return Settings()
