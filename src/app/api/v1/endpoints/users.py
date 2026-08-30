from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from app.api.deps import get_current_user, get_profile_repository, get_profile_service
from app.core.vector_db import QdrantProfileRepository
from app.models.user import User
from app.schemas.profile import ScanResponse
from app.schemas.user import UserResponse
from app.services.profile_service import ProfileService

router = APIRouter(prefix="/users", tags=["users"])

_MIN_IMAGES = 1
_MAX_IMAGES = 3


@router.get("/me", response_model=UserResponse, status_code=status.HTTP_200_OK)
def get_me(
    current_user: User = Depends(get_current_user),
    profiles: QdrantProfileRepository = Depends(get_profile_repository),
) -> UserResponse:
    return UserResponse(
        email=current_user.email,
        display_name=current_user.display_name,
        created_at=current_user.created_at,
        has_face_profile=profiles.has_profile(current_user.id),
    )


@router.post("/me/scan", response_model=ScanResponse, status_code=status.HTTP_200_OK)
def scan_me(
    files: list[UploadFile] = File(...),
    current_user: User = Depends(get_current_user),
    service: ProfileService = Depends(get_profile_service),
) -> ScanResponse:
    if not (_MIN_IMAGES <= len(files) <= _MAX_IMAGES):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Submit between {_MIN_IMAGES} and {_MAX_IMAGES} image(s)",
        )

    images = [file.file.read() for file in files]
    faces_found = service.enroll(current_user.id, images)

    return ScanResponse(images_processed=len(files), faces_found=faces_found)
