from __future__ import annotations

import logging

import numpy as np
from fastapi import HTTPException, status

from app.core.vector_db import QdrantProfileRepository
from app.domain.interfaces import EmbeddingProvider

logger = logging.getLogger("app.profile")


class ProfileService:
    """Face-profile enrollment for a single authenticated user.

    Takes 1..N face images, detects+embeds every face across all of them, and
    upserts the centroid (mean) as the user's permanent profile vector into the
    `user_profiles` Qdrant collection (id == user_id, so re-scanning replaces
    the previous vector). Detecting/embedding is CPU-bound; callers should use a
    plain `def` endpoint so FastAPI runs it on a worker thread.
    """

    def __init__(self, embedder: EmbeddingProvider, profiles: QdrantProfileRepository) -> None:
        self._embedder = embedder
        self._profiles = profiles

    def enroll(self, user_id: str, images: list[bytes]) -> int:
        """Enroll every face found across `images` as the user's profile.

        Returns the number of faces detected. Raises 422 if no face is found
        or an image cannot be decoded.
        """
        vectors: list[list[float]] = []
        total_faces = 0
        for image_bytes in images:
            try:
                faces = self._embedder.detect_and_embed(image_bytes)
            except ValueError as exc:  # corrupt / unsupported image
                logger.warning("profile scan failed to decode image for user=%s: %s", user_id, exc)
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="One of the submitted images could not be decoded",
                ) from exc
            for face in faces:
                vectors.append(face.embedding)
                total_faces += 1

        if not vectors:
            logger.info("profile scan found no face for user=%s", user_id)
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No face detected in the submitted image(s)",
            )

        centroid = np.mean(vectors, axis=0).tolist()
        self._profiles.upsert_profile(user_id, centroid)
        logger.info("user enrolled face profile id=%s faces=%d", user_id, total_faces)
        return total_faces

    def has_profile(self, user_id: str) -> bool:
        return self._profiles.has_profile(user_id)
