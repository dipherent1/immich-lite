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

    def match_photo(self, photo: Photo) -> set[str]:
        """Match one already-processed photo.

        Returns the set of attendee user ids the photo matched (for the worker to
        notify). A photo matching multiple people yields multiple ids.
        """
        attendee_ids = self._events.list_attendee_ids(photo.event_id)
        if not attendee_ids:
            logger.info("no attendees to match against event=%s photo=%s", photo.event_id, photo.id)
            return set()

        faces = self._faces.get_faces_for_photo(photo.id)
        if not faces:
            logger.info("no faces stored for photo=%s, nothing to match", photo.id)
            return set()

        matched_user_ids: set[str] = set()
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
                matched_user_ids.add(user_id)

        logger.info(
            "photo matched event=%s photo=%s faces=%d matches=%d",
            photo.event_id,
            photo.id,
            len(faces),
            written,
        )
        return matched_user_ids

    def match_new_attendee(self, event_id: str, attendee_id: str) -> set[str]:
        """Backfill matching for a newly-joined attendee.

        Photos are only matched once, at upload time, against the attendees that
        exist then. When a user joins (share link) or is approved (join request)
        *after* photos already exist, this re-runs matching for them over the
        event's stored faces — so they get the same `PhotoMatch` rows (and thus
        notifications/feed entries) they would have gotten had they been a member
        when each photo was uploaded.

        Returns the set of photo ids the attendee matched. A user with no face
        profile matches nothing and returns empty. Callers should treat failures
        as best-effort: a Qdrant hiccup here must never break join/approve.
        """
        if not self._profiles.has_profile(attendee_id):
            logger.info(
                "backfill skipped, attendee has no profile event=%s user=%s",
                event_id,
                attendee_id,
            )
            return set()

        faces = self._faces.get_faces_for_event(event_id)
        if not faces:
            logger.info(
                "backfill skipped, no existing faces event=%s user=%s",
                event_id,
                attendee_id,
            )
            return set()

        matched_photo_ids: set[str] = set()
        written = 0
        for photo_id, face in faces:
            if not photo_id or not face.embedding:
                continue
            hits = self._profiles.query_similar_restricted(
                face.embedding,
                [attendee_id],
                threshold=self._similarity_threshold,
            )
            for matched_user_id, similarity in hits:
                if matched_user_id != attendee_id:
                    continue
                self._matches.upsert_best(
                    photo_id=photo_id,
                    user_id=attendee_id,
                    similarity=similarity,
                    bbox={
                        "x1": face.bbox.x1,
                        "y1": face.bbox.y1,
                        "x2": face.bbox.x2,
                        "y2": face.bbox.y2,
                    },
                )
                written += 1
                matched_photo_ids.add(photo_id)

        logger.info(
            "attendee backfill matched event=%s user=%s photo_ids=%d",
            event_id,
            attendee_id,
            len(matched_photo_ids),
        )
        return matched_photo_ids

    def feed(
        self,
        user_id: str,
        *,
        offset: int = 0,
        limit: int = 24,
    ) -> tuple[list[tuple[PhotoMatch, Event]], bool]:
        """A user's matched-photo delivery feed, newest first (owner only)."""
        return self._matches.list_feed_for_user(user_id, offset=offset, limit=limit)
