from __future__ import annotations

from fastapi import HTTPException, status

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User
from app.repositories.user_repository import UserRepository
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse


class UserService:
    def __init__(self, repository: UserRepository) -> None:
        self._repository = repository

    def register(self, payload: RegisterRequest) -> User:
        if self._repository.get_by_email(payload.email) is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )
        try:
            return self._repository.create(
                email=payload.email,
                hashed_password=hash_password(payload.password),
                display_name=payload.display_name,
            )
        except Exception:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="An account with this email already exists",
            )

    def authenticate(self, payload: LoginRequest) -> TokenResponse:
        user = self._repository.get_by_email(payload.email.lower())
        if user is None or not verify_password(payload.password, user.hashed_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect email or password",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return TokenResponse(access_token=create_access_token(str(user.id)))

    def get_by_id(self, user_id: str) -> User | None:
        return self._repository.get_by_id(user_id)
