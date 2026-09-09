from datetime import datetime, timedelta

from sqlmodel import select

from app.models.photo import Photo
from app.repositories.photo_repository import PhotoRepository


def _make_user(db_session, email="u@example.com"):
    from app.repositories.user_repository import UserRepository

    return UserRepository(db_session).create(
        email=email, hashed_password="h", display_name="U"
    )


def _make_event(db_session, owner_id, name="Party", token="tok"):
    from datetime import timezone

    from app.repositories.event_repository import EventRepository

    return EventRepository(db_session).create_event(
        owner_id=owner_id,
        name=name,
        join_token=token,
        starts_at=datetime.now(timezone.utc) - timedelta(hours=1),
        expires_at=None,
    )


def test_create_photo_starts_pending(db_session):
    user = _make_user(db_session)
    event = _make_event(db_session, user.id)
    photo = PhotoRepository(db_session).create(
        event_id=event.id,
        uploader_user_id=user.id,
        storage_path="photos/evt/p.jpg",
    )
    assert photo.status == "pending"
    assert photo.processed_at is None
    assert photo.storage_path == "photos/evt/p.jpg"


def test_get_by_id_roundtrip(db_session):
    user = _make_user(db_session)
    event = _make_event(db_session, user.id)
    repo = PhotoRepository(db_session)
    created = repo.create(event_id=event.id, uploader_user_id=user.id, storage_path="s")
    assert repo.get_by_id(created.id).id == created.id


def test_get_by_id_not_found(db_session):
    assert PhotoRepository(db_session).get_by_id("missing") is None


def test_set_status_processed_sets_processed_at(db_session):
    user = _make_user(db_session)
    event = _make_event(db_session, user.id)
    repo = PhotoRepository(db_session)
    photo = repo.create(event_id=event.id, uploader_user_id=user.id, storage_path="s")
    repo.set_status(photo.id, "processed", processed=True)
    refreshed = repo.get_by_id(photo.id)
    assert refreshed.status == "processed"
    assert refreshed.processed_at is not None


def test_set_status_failed_leaves_processed_at_none(db_session):
    user = _make_user(db_session)
    event = _make_event(db_session, user.id)
    repo = PhotoRepository(db_session)
    photo = repo.create(event_id=event.id, uploader_user_id=user.id, storage_path="s")
    repo.set_status(photo.id, "failed")
    refreshed = repo.get_by_id(photo.id)
    assert refreshed.status == "failed"
    assert refreshed.processed_at is None


def test_set_status_missing_photo_is_noop(db_session):
    PhotoRepository(db_session).set_status("missing", "processed", processed=True)


def test_list_pending_only_pending_oldest_first(db_session):
    user = _make_user(db_session)
    event = _make_event(db_session, user.id)
    repo = PhotoRepository(db_session)
    base = datetime(2026, 1, 1)
    for i in range(3):
        db_session.add(
            Photo(
                event_id=event.id,
                uploader_user_id=user.id,
                storage_path=f"p{i}",
                status="pending",
                uploaded_at=base + timedelta(minutes=i),
            )
        )
        db_session.commit()
    pending = [p.storage_path for p in repo.list_pending()]
    assert pending == ["p0", "p1", "p2"]

    for photo in db_session.scalars(select(Photo)).all():
        if photo.storage_path == "p1":
            repo.set_status(photo.id, "processed", processed=True)
    assert [p.storage_path for p in repo.list_pending()] == ["p0", "p2"]


def test_list_pending_respects_limit(db_session):
    user = _make_user(db_session)
    event = _make_event(db_session, user.id)
    repo = PhotoRepository(db_session)
    for i in range(5):
        repo.create(event_id=event.id, uploader_user_id=user.id, storage_path=f"p{i}")
    assert len(repo.list_pending(limit=2)) == 2


def test_list_for_event_newest_first_and_pagination(db_session):
    user = _make_user(db_session)
    event = _make_event(db_session, user.id)
    repo = PhotoRepository(db_session)
    base = datetime(2026, 1, 1)
    for i in range(25):
        db_session.add(
            Photo(
                event_id=event.id,
                uploader_user_id=user.id,
                storage_path=f"p{i}",
                status="pending",
                uploaded_at=base + timedelta(minutes=i),
            )
        )
        db_session.commit()

    page1, has_more = repo.list_for_event(event.id, offset=0, limit=24)
    assert len(page1) == 24
    assert has_more is True
    assert page1[0].uploaded_at == base + timedelta(minutes=24)

    page2, has_more2 = repo.list_for_event(event.id, offset=24, limit=24)
    assert len(page2) == 1
    assert has_more2 is False
    assert page2[0].uploaded_at == base


def test_list_for_event_scoped_to_event(db_session):
    u1 = _make_user(db_session, "u1@example.com")
    u2 = _make_user(db_session, "u2@example.com")
    event_a = _make_event(db_session, u1.id, name="A", token="tok-a")
    event_b = _make_event(db_session, u2.id, name="B", token="tok-b")
    repo = PhotoRepository(db_session)
    repo.create(event_id=event_a.id, uploader_user_id=u1.id, storage_path="a1")
    repo.create(event_id=event_b.id, uploader_user_id=u2.id, storage_path="b1")
    photos, _ = repo.list_for_event(event_a.id)
    assert [p.storage_path for p in photos] == ["a1"]