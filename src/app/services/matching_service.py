from __future__ import annotations

import logging

from app.core.vector_db import EventFaceRepository, QdrantProfileRepository
from app.models.event import Event
from app.models.photo import Photo
from app.models.photo_match import PhotoMatch
from app.repositories.event_repository import EventRepository
from app.repositories.photo_match_repository import PhotoMatchRepository

logger = logging.getLogger("app.matching")


class MatchingService:
    """Matches a processed photo's faces to the event's attendee profiles.

    Scoped like everything else: matching never scans the whole `user_profiles`
    store. It (1) reads the event's attendee user ids, (2) reads the photo's
    face vectors back from Qdrant `event_faces`, (3) for each face queries
    `user_profiles` restricted to those attendee ids above the similarity
    threshold, and (4) writes one `PhotoMatch` per (photo, user) pair, keeping
    the best similarity.

    Kept as a separate, independently testable service so it can be called from
    the worker (after ingestion) or re-run on demand.
    """

    def __init__(
        self,
        events: EventRepository,
        faces: EventFaceRepository,
        profiles: QdrantProfileRepository,
        matches: PhotoMatchRepository,
        *,
        similarity_threshold: float = 0.5,
    ) -> None:
        self._events = events
        self._faces = faces
        self._profiles = profiles
        self._matches = matches
        self._similarity_threshold = similarity_threshold

    def match_photo(self, photo: Photo) -> int:
        """Match one already-processed photo. Returns the number of match rows added."""
        attendee_ids = self._events.list_attendee_ids(photo.event_id)
        if not attendee_ids:
            logger.info("no attendees to match against event=%s photo=%s", photo.event_id, photo.id)
            return 0

        faces = self._faces.get_faces_for_photo(photo.id)
        if not faces:
            logger.info("no faces stored for photo=%s, nothing to match", photo.id)
            return 0

        written = 0
        for face in faces:
            if not face.embedding:
                continue
            hits = self._profiles.query_similar_restricted(
                face.embedding,
                attendee_ids,
                threshold=self._similarity_threshold,
            )
            for user_id, similarity in hits:
                self._matches.upsert_best(
                    photo_id=photo.id,
                    user_id=user_id,
                    similarity=similarity,
                    bbox={
                        "x1": face.bbox.x1,
                        "y1": face.bbox.y1,
                        "x2": face.bbox.x2,
                        "y2": face.bbox.y2,
                    },
                )
                written += 1

        logger.info(
            "photo matched event=%s photo=%s faces=%d matches=%d",
            photo.event_id,
            photo.id,
            len(faces),
            written,
        )
        return written

    def feed(
        self,
        user_id: str,
        *,
        offset: int = 0,
        limit: int = 24,
    ) -> tuple[list[tuple[PhotoMatch, Event]], bool]:
        """A user's matched-photo delivery feed, newest first (owner only)."""
        return self._matches.list_feed_for_user(user_id, offset=offset, limit=limit)
