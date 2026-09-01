from __future__ import annotations

import logging
from functools import lru_cache

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.file_storage import LocalFileService
from app.core.security import decode_access_token
from app.core.vector_db import QdrantProfileRepository
from app.models.user import User
from app.repositories.event_repository import EventRepository
from app.repositories.photo_repository import PhotoRepository
from app.repositories.user_repository import UserRepository
from app.services.embedding_service import InsightFaceEmbeddingService
from app.services.event_service import EventService
from app.services.photo_service import PhotoService
from app.services.profile_service import ProfileService
from app.services.user_service import UserService

logger = logging.getLogger("app.auth")

bearer_scheme = HTTPBearer(auto_error=False)


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_user_service(repository: UserRepository = Depends(get_user_repository)) -> UserService:
    return UserService(repository)


@lru_cache
def get_embedding_service() -> InsightFaceEmbeddingService:
    """Shared, lazily-loaded embedding service (model loads once per process)."""
    settings = get_settings()
    return InsightFaceEmbeddingService(
        model_name=settings.model_name,
        detection_threshold=settings.detection_threshold,
    )


def get_profile_repository() -> QdrantProfileRepository:
    return QdrantProfileRepository(url=get_settings().qdrant_url)


def get_profile_service(
    embedder: InsightFaceEmbeddingService = Depends(get_embedding_service),
    profiles: QdrantProfileRepository = Depends(get_profile_repository),
) -> ProfileService:
    return ProfileService(embedder, profiles)


def get_event_repository(db: Session = Depends(get_db)) -> EventRepository:
    return EventRepository(db)


def get_photo_repository(db: Session = Depends(get_db)) -> PhotoRepository:
    return PhotoRepository(db)


def get_file_service() -> LocalFileService:
    return LocalFileService(root=get_settings().output_root)


def get_photo_service(
    events: EventRepository = Depends(get_event_repository),
    photos: PhotoRepository = Depends(get_photo_repository),
    files: LocalFileService = Depends(get_file_service),
) -> PhotoService:
    return PhotoService(events, photos, files)


def get_event_service(
    repository: EventRepository = Depends(get_event_repository),
    profiles: ProfileService = Depends(get_profile_service),
) -> EventService:
    return EventService(repository, profiles)


def get_current_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    service: UserService = Depends(get_user_service),
) -> User:
    def _unauthorized(log_reason: str) -> HTTPException:
        # Never log the token itself.
        logger.warning("authentication failed on %s %s: %s", request.method, request.url.path, log_reason)
        return HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if credentials is None:
        raise _unauthorized("missing bearer token")
    subject = decode_access_token(credentials.credentials)
    if subject is None:
        raise _unauthorized("invalid or expired token")
    user = service.get_by_id(subject)
    if user is None:
        raise _unauthorized(f"unknown user id={subject}")
    # Expose the user id to the request-logging middleware.
    request.state.user_id = user.id
    return user
