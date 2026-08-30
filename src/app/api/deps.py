from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlmodel import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.services.user_service import UserService

logger = logging.getLogger("app.auth")

bearer_scheme = HTTPBearer(auto_error=False)


def get_user_repository(db: Session = Depends(get_db)) -> UserRepository:
    return UserRepository(db)


def get_user_service(repository: UserRepository = Depends(get_user_repository)) -> UserService:
    return UserService(repository)


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
