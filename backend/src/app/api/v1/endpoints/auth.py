from __future__ import annotations

from fastapi import APIRouter, Depends, Request, status

from app.api.deps import get_user_service
from app.core.config import get_settings
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse
from app.schemas.user import UserResponse
from app.services.user_service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])

_auth_limit = get_settings().rate_limit_auth


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit(_auth_limit)
def register(
    request: Request,
    payload: RegisterRequest,
    service: UserService = Depends(get_user_service),
) -> User:
    return service.register(payload)


@router.post("/login", response_model=TokenResponse, status_code=status.HTTP_200_OK)
@limiter.limit(_auth_limit)
def login(
    request: Request,
    payload: LoginRequest,
    service: UserService = Depends(get_user_service),
) -> TokenResponse:
    return service.authenticate(payload)
