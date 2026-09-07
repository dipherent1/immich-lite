from datetime import datetime, timedelta, timezone

from app.repositories.event_repository import EventRepository
from app.repositories.user_repository import UserRepository


def _make_user(db_session, email, display_name="U"):
    return UserRepository(db_session).create(
        email=email, hashed_password="h", display_name=display_name
    )


def _create_event(
    repo,
    owner_id,
    name="Party",
    token="tok-abc",
    starts_days_ago=1,
    expires_days_ahead=1,
):
    now = datetime.now(timezone.utc)
    return repo.create_event(
        owner_id=owner_id,
        name=name,
        join_token=token,
        starts_at=now - timedelta(days=starts_days_ago),
        expires_at=now + timedelta(days=expires_days_ahead),
    )


def test_create_event_persists(db_session):
    user = _make_user(db_session, "owner@example.com")
    repo = EventRepository(db_session)
    event = _create_event(repo, user.id, name="Birthday Bash", token="tok-1")
    assert repo.get_by_id(event.id).name == "Birthday Bash"
    assert repo.get_by_token("tok-1").id == event.id
    assert event.owner_id == user.id


def test_get_by_id_not_found(db_session):
    assert EventRepository(db_session).get_by_id("missing") is None


def test_get_by_token_not_found(db_session):
    assert EventRepository(db_session).get_by_token("nope") is None


def test_add_attendee_and_is_attendee(db_session):
    user = _make_user(db_session, "owner@example.com")
    repo = EventRepository(db_session)
    event = _create_event(repo, user.id)
    assert repo.add_attendee(event.id, user.id) is True
    assert repo.is_attendee(event.id, user.id) is True


def test_add_attendee_duplicate_returns_false(db_session):
    user = _make_user(db_session, "owner@example.com")
    repo = EventRepository(db_session)
    event = _create_event(repo, user.id)
    assert repo.add_attendee(event.id, user.id) is True
    assert repo.add_attendee(event.id, user.id) is False
    assert repo.attendee_count(event.id) == 1


def test_attendee_count_zero_when_nobody_joined(db_session):
    user = _make_user(db_session, "owner@example.com")
    repo = EventRepository(db_session)
    event = _create_event(repo, user.id)
    assert repo.attendee_count(event.id) == 0


def test_list_attendee_ids_returns_distinct_ids(db_session):
    owner = _make_user(db_session, "owner@example.com")
    a = _make_user(db_session, "a@example.com")
    b = _make_user(db_session, "b@example.com")
    repo = EventRepository(db_session)
    event = _create_event(repo, owner.id)
    repo.add_attendee(event.id, a.id)
    repo.add_attendee(event.id, b.id)
    repo.add_attendee(event.id, a.id)
    ids = repo.list_attendee_ids(event.id)
    assert set(ids) == {a.id, b.id}
    assert len(ids) == 2


def test_search_by_name_partial_case_insensitive(db_session):
    owner = _make_user(db_session, "owner@example.com")
    repo = EventRepository(db_session)
    _create_event(repo, owner.id, name="Summer Party", token="tok-a")
    _create_event(repo, owner.id, name="Winter Gala", token="tok-b")
    assert [e.name for e in repo.search_by_name("summer")] == ["Summer Party"]
    assert [e.name for e in repo.search_by_name("party")] == ["Summer Party"]
    assert [e.name for e in repo.search_by_name("gala")] == ["Winter Gala"]
    assert repo.search_by_name("zzz") == []


def test_search_by_name_newest_first(db_session):
    owner = _make_user(db_session, "owner@example.com")
    repo = EventRepository(db_session)
    older = _create_event(repo, owner.id, name="Alpha Party", token="tok-a")
    newer = _create_event(repo, owner.id, name="Beta Party", token="tok-b")
    results = repo.search_by_name("party")
    assert [e.id for e in results] == [newer.id, older.id]


def test_list_for_user_owned_and_attended_deduped(db_session):
    owner = _make_user(db_session, "owner@example.com")
    guest = _make_user(db_session, "guest@example.com")
    repo = EventRepository(db_session)
    owned = _create_event(repo, owner.id, name="Owned", token="tok-a")
    attended = _create_event(repo, guest.id, name="Attended", token="tok-b")
    also_attended = _create_event(repo, guest.id, name="Owned By Guest", token="tok-c")
    repo.add_attendee(attended.id, owner.id)
    repo.add_attendee(also_attended.id, owner.id)
    repo.add_attendee(owned.id, guest.id)

    ids = {e.id for e in repo.list_for_user(owner.id)}
    assert ids == {owned.id, attended.id, also_attended.id}

    guest_ids = {e.id for e in repo.list_for_user(guest.id)}
    assert guest_ids == {owned.id, attended.id, also_attended.id}


def test_list_for_user_newest_first(db_session):
    owner = _make_user(db_session, "owner@example.com")
    repo = EventRepository(db_session)
    first = _create_event(repo, owner.id, name="First", token="tok-a")
    second = _create_event(repo, owner.id, name="Second", token="tok-b")
    assert [e.id for e in repo.list_for_user(owner.id)] == [second.id, first.id]