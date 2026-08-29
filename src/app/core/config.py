from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
