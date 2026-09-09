import json
from datetime import datetime, timedelta, timezone

from sqlmodel import select

from app.models.photo_match import PhotoMatch
from app.repositories.event_repository import EventRepository
from app.repositories.photo_match_repository import PhotoMatchRepository
from app.repositories.photo_repository import PhotoRepository
from app.repositories.user_repository import UserRepository


def _seed(db_session):
    user = UserRepository(db_session).create(
        email="user@example.com", hashed_password="h", display_name="U"
    )
    other = UserRepository(db_session).create(
        email="other@example.com", hashed_password="h", display_name="O"
    )
    now = datetime.now(timezone.utc)
    event = EventRepository(db_session).create_event(
        owner_id=user.id,
        name="Party",
        join_token="tok",
        starts_at=now - timedelta(hours=1),
        expires_at=now + timedelta(hours=1),
    )
    repo = PhotoRepository(db_session)
    p1 = repo.create(event_id=event.id, uploader_user_id=user.id, storage_path="p1.jpg")
    p2 = repo.create(event_id=event.id, uploader_user_id=user.id, storage_path="p2.jpg")
    return user, other, event, p1, p2


def _all_matches(db_session):
    return db_session.scalars(select(PhotoMatch)).all()


def test_upsert_best_inserts_new_row(db_session):
    user, other, event, p1, p2 = _seed(db_session)
    repo = PhotoMatchRepository(db_session)
    repo.upsert_best(photo_id=p1.id, user_id=user.id, similarity=0.8, bbox={"x1": 1, "y1": 2, "x2": 3, "y2": 4})
    rows = _all_matches(db_session)
    assert len(rows) == 1
    assert rows[0].similarity == 0.8
    assert json.loads(rows[0].bbox) == {"x1": 1, "y1": 2, "x2": 3, "y2": 4}


def test_upsert_best_keeps_higher_similarity(db_session):
    user, other, event, p1, p2 = _seed(db_session)
    repo = PhotoMatchRepository(db_session)
    repo.upsert_best(photo_id=p1.id, user_id=user.id, similarity=0.8, bbox={"x1": 0, "y1": 0, "x2": 1, "y2": 1})
    repo.upsert_best(photo_id=p1.id, user_id=user.id, similarity=0.95, bbox={"x1": 9, "y1": 8, "x2": 7, "y2": 6})
    rows = _all_matches(db_session)
    assert len(rows) == 1
    assert rows[0].similarity == 0.95
    assert json.loads(rows[0].bbox) == {"x1": 9, "y1": 8, "x2": 7, "y2": 6}


def test_upsert_best_ignores_lower_similarity(db_session):
    user, other, event, p1, p2 = _seed(db_session)
    repo = PhotoMatchRepository(db_session)
    repo.upsert_best(photo_id=p1.id, user_id=user.id, similarity=0.95, bbox={"x1": 9, "y1": 8, "x2": 7, "y2": 6})
    repo.upsert_best(photo_id=p1.id, user_id=user.id, similarity=0.8, bbox={"x1": 0, "y1": 0, "x2": 1, "y2": 1})
    rows = _all_matches(db_session)
    assert len(rows) == 1
    assert rows[0].similarity == 0.95
    assert json.loads(rows[0].bbox) == {"x1": 9, "y1": 8, "x2": 7, "y2": 6}


def test_upsert_best_no_duplicate_per_pair(db_session):
    user, other, event, p1, p2 = _seed(db_session)
    repo = PhotoMatchRepository(db_session)
    for _ in range(5):
        repo.upsert_best(photo_id=p1.id, user_id=user.id, similarity=0.9, bbox={})
    assert len(_all_matches(db_session)) == 1


def test_list_for_user_scoped_and_newest_first(db_session):
    user, other, event, p1, p2 = _seed(db_session)
    repo = PhotoMatchRepository(db_session)
    db_session.add(PhotoMatch(photo_id=p2.id, user_id=user.id, similarity=0.7, bbox="{}", created_at=datetime(2026, 1, 2, tzinfo=timezone.utc)))
    db_session.add(PhotoMatch(photo_id=p1.id, user_id=user.id, similarity=0.8, bbox="{}", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    db_session.add(PhotoMatch(photo_id=p1.id, user_id=other.id, similarity=0.99, bbox="{}", created_at=datetime(2026, 1, 1, tzinfo=timezone.utc)))
    db_session.commit()

    matches, _ = repo.list_for_user(user.id)
    assert [m.photo_id for m in matches] == [p2.id, p1.id]
    assert repo.list_for_user(other.id)[0][0].user_id == other.id


def test_list_for_user_pagination_with_has_more(db_session):
    user, other, event, p1, p2 = _seed(db_session)
    repo = PhotoMatchRepository(db_session)
    photo = p1
    for i in range(25):
        if i >= 1:
            new_photo = PhotoRepository(db_session).create(
                event_id=event.id, uploader_user_id=user.id, storage_path=f"pextra{i}.jpg"
            )
            photo = new_photo
        db_session.add(
            PhotoMatch(
                photo_id=photo.id,
                user_id=user.id,
                similarity=0.5,
                bbox="{}",
                created_at=datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(minutes=i),
            )
        )
        db_session.commit()

    page1, has_more = repo.list_for_user(user.id, offset=0, limit=24)
    assert len(page1) == 24
    assert has_more is True
    page2, has_more2 = repo.list_for_user(user.id, offset=24, limit=24)
    assert len(page2) == 1
    assert has_more2 is False


def test_list_feed_for_user_joins_event(db_session):
    user, other, event, p1, p2 = _seed(db_session)
    repo = PhotoMatchRepository(db_session)
    db_session.add(
        PhotoMatch(
            photo_id=p1.id,
            user_id=user.id,
            similarity=0.9,
            bbox="{}",
            created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        )
    )
    db_session.add(
        PhotoMatch(
            photo_id=p2.id,
            user_id=user.id,
            similarity=0.75,
            bbox="{}",
            created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
    )
    db_session.commit()

    feed, has_more = repo.list_feed_for_user(user.id)
    assert has_more is False
    assert [(m.photo_id, e.id) for m, e in feed] == [(p2.id, event.id), (p1.id, event.id)]
    assert all(e.name == "Party" for _, e in feed)


def test_list_feed_for_user_only_matches_for_joined_events(db_session):
    user, other, event, p1, p2 = _seed(db_session)
    unmatched_event = EventRepository(db_session).create_event(
        owner_id=other.id,
        name="Unattended",
        join_token="tok-other",
        starts_at=datetime.now(timezone.utc) - timedelta(hours=1),
        expires_at=None,
    )
    unmatched_photo = PhotoRepository(db_session).create(
        event_id=unmatched_event.id, uploader_user_id=other.id, storage_path="outside.jpg"
    )
    repo = PhotoMatchRepository(db_session)
    repo.upsert_best(photo_id=unmatched_photo.id, user_id=user.id, similarity=0.6, bbox={})

    feed, _ = repo.list_feed_for_user(user.id)
    assert len(feed) == 1
    assert feed[0][0].photo_id == unmatched_photo.id
    assert feed[0][1].name == "Unattended"


def test_bbox_dict_property(db_session):
    user, other, event, p1, p2 = _seed(db_session)
    repo = PhotoMatchRepository(db_session)
    repo.upsert_best(photo_id=p1.id, user_id=user.id, similarity=0.8, bbox={"x1": 1, "y1": 2, "x2": 3, "y2": 4})
    rows = _all_matches(db_session)
    assert rows[0].bbox_dict == {"x1": 1, "y1": 2, "x2": 3, "y2": 4}


def test_bbox_dict_property_invalid_json(db_session):
    match = PhotoMatch(photo_id="p", user_id="u", similarity=0.5, bbox="not json")
    assert match.bbox_dict == {}