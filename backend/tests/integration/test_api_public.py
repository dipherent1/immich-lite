"""The public (no login) event view, addressed by the share-link token."""

import io
from datetime import datetime, timedelta, timezone

import pytest
from PIL import Image

from app.repositories.photo_repository import PhotoRepository
from conftest import API_PREFIX, auth_header, make_event, register_user

PUBLIC = f"{API_PREFIX}/public/events"


@pytest.fixture(autouse=True)
def _no_enqueue(monkeypatch):
    monkeypatch.setattr(
        "app.services.photo_service.enqueue_photo_processing", lambda photo_id: None
    )


def _image(fmt: str = "JPEG", size=(8, 8), color="red") -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, fmt)
    return buf.getvalue()


def _upload(client, headers, event_id, data=None, filename="pic.jpg"):
    return client.post(
        f"{API_PREFIX}/events/{event_id}/photos",
        headers=headers,
        files={"file": (filename, data or _image(), "image/jpeg")},
    )


@pytest.fixture
def event_with_photos(client, db_session):
    """A host, one event, and photos in each state: 2 processed, 1 pending, 1 failed."""
    register_user(client)
    headers = auth_header(client)
    event = make_event(client, headers, name="Rooftop Party").json()
    ids = {}
    for key in ("ok1", "ok2", "pending", "failed"):
        ids[key] = _upload(client, headers, event["id"], filename=f"{key}.jpg").json()["id"]
    repo = PhotoRepository(db_session)
    repo.set_status(ids["ok1"], "processed", processed=True)
    repo.set_status(ids["ok2"], "processed", processed=True)
    repo.set_status(ids["failed"], "failed")
    return event, ids, headers


class TestPublicEventView:
    def test_works_without_login_and_exposes_minimal_fields(self, client, event_with_photos):
        event, _, _ = event_with_photos
        res = client.get(f"{PUBLIC}/{event['join_token']}")  # no Authorization header
        assert res.status_code == 200
        body = res.json()
        assert set(body) == {"name", "expires_at", "photo_count"}
        assert body["name"] == "Rooftop Party"
        assert body["photo_count"] == 2  # processed only
        assert body["expires_at"] is not None

    def test_unknown_token_is_404(self, client):
        assert client.get(f"{PUBLIC}/not-a-real-token").status_code == 404

    def test_ended_event_is_410(self, client):
        register_user(client)
        now = datetime.now(timezone.utc)
        event = make_event(
            client,
            auth_header(client),
            extra={
                "starts_at": (now - timedelta(days=2)).isoformat(),
                "expires_at": (now - timedelta(days=1)).isoformat(),
            },
        ).json()
        assert client.get(f"{PUBLIC}/{event['join_token']}").status_code == 410
        assert client.get(f"{PUBLIC}/{event['join_token']}/photos").status_code == 410


class TestPublicPhotoList:
    def test_lists_only_processed_photos_without_login(self, client, event_with_photos):
        event, ids, _ = event_with_photos
        res = client.get(f"{PUBLIC}/{event['join_token']}/photos")
        assert res.status_code == 200
        body = res.json()
        assert {p["id"] for p in body["items"]} == {ids["ok1"], ids["ok2"]}
        assert all(set(p) == {"id"} for p in body["items"])  # nothing but an opaque id
        assert body["has_more"] is False

    def test_pagination(self, client, event_with_photos):
        event, _, _ = event_with_photos
        first = client.get(f"{PUBLIC}/{event['join_token']}/photos", params={"limit": 1}).json()
        assert len(first["items"]) == 1 and first["has_more"] is True
        second = client.get(
            f"{PUBLIC}/{event['join_token']}/photos",
            params={"limit": 1, "offset": first["next_offset"]},
        ).json()
        assert len(second["items"]) == 1 and second["has_more"] is False
        assert second["items"][0]["id"] != first["items"][0]["id"]

    def test_response_never_contains_user_ids_or_token(self, client, event_with_photos):
        event, _, _ = event_with_photos
        me = client.get(f"{API_PREFIX}/users/me", headers=event_with_photos[2]).json()
        for path in ("", "/photos"):
            text = client.get(f"{PUBLIC}/{event['join_token']}{path}").text
            assert me["id"] not in text
            assert event["id"] not in text


class TestPublicPreview:
    def test_serves_a_small_jpeg_and_never_the_original(self, client, db_session):
        register_user(client)
        headers = auth_header(client)
        event = make_event(client, headers).json()
        big = _image("JPEG", size=(2400, 1800))
        photo_id = _upload(client, headers, event["id"], data=big).json()["id"]
        PhotoRepository(db_session).set_status(photo_id, "processed", processed=True)

        res = client.get(f"{PUBLIC}/{event['join_token']}/photos/{photo_id}/preview")
        assert res.status_code == 200
        assert res.headers["content-type"] == "image/jpeg"
        assert "private" in res.headers["cache-control"]
        img = Image.open(io.BytesIO(res.content))
        assert max(img.size) <= 800
        assert len(res.content) < len(big)  # a downscale, not the original bytes

    def test_preview_is_cached_inside_the_event_preview_dir(self, client, db_session, tmp_path):
        register_user(client)
        headers = auth_header(client)
        event = make_event(client, headers).json()
        photo_id = _upload(client, headers, event["id"]).json()["id"]
        PhotoRepository(db_session).set_status(photo_id, "processed", processed=True)
        client.get(f"{PUBLIC}/{event['join_token']}/photos/{photo_id}/preview")
        # Event expiry deletes previews/{event_id}/, so the cache dies with the event.
        assert (tmp_path / "previews" / event["id"] / f"public-{photo_id}.jpg").exists()

    def test_pending_and_failed_photos_are_not_visible(self, client, event_with_photos):
        event, ids, _ = event_with_photos
        for key in ("pending", "failed"):
            res = client.get(f"{PUBLIC}/{event['join_token']}/photos/{ids[key]}/preview")
            assert res.status_code == 404

    def test_photo_from_another_event_is_404(self, client, event_with_photos, db_session):
        event, ids, headers = event_with_photos
        other = make_event(client, headers, name="Other").json()
        res = client.get(f"{PUBLIC}/{other['join_token']}/photos/{ids['ok1']}/preview")
        assert res.status_code == 404

    def test_unknown_photo_is_404(self, client, event_with_photos):
        event, _, _ = event_with_photos
        assert client.get(f"{PUBLIC}/{event['join_token']}/photos/nope/preview").status_code == 404


class TestMemberRoutesStayPrivate:
    def test_member_photo_routes_still_require_login(self, client, event_with_photos):
        event, ids, _ = event_with_photos
        eid, pid = event["id"], ids["ok1"]
        assert client.get(f"{API_PREFIX}/events/{eid}/photos").status_code == 401
        assert client.get(f"{API_PREFIX}/events/{eid}/photos/{pid}/file").status_code == 401
        assert client.get(f"{API_PREFIX}/events/{eid}").status_code == 401
        assert (
            client.post(f"{API_PREFIX}/events/{eid}/photos/download", json={}).status_code == 401
        )

    def test_join_token_in_public_path_cannot_be_an_event_id(self, client, event_with_photos):
        event, _, _ = event_with_photos
        # Public routes resolve by token only; an event id must not work as one.
        assert client.get(f"{PUBLIC}/{event['id']}").status_code == 404


@pytest.fixture
def rate_limited_client(client):
    from app.core.rate_limit import limiter

    limiter.reset()
    limiter.enabled = True
    try:
        yield client
    finally:
        limiter.reset()
        limiter.enabled = False


class TestPublicRateLimit:
    def test_public_routes_are_bounded_per_ip(self, rate_limited_client):
        from app.core.config import get_settings

        budget = int(get_settings().rate_limit_public.split("/")[0])
        headers = {"X-Real-IP": "198.51.100.77"}
        for _ in range(budget):
            assert rate_limited_client.get(f"{PUBLIC}/nope", headers=headers).status_code == 404
        blocked = rate_limited_client.get(f"{PUBLIC}/nope", headers=headers)
        assert blocked.status_code == 429
        # Another visitor is unaffected.
        other = rate_limited_client.get(f"{PUBLIC}/nope", headers={"X-Real-IP": "198.51.100.78"})
        assert other.status_code == 404

    def test_unrelated_public_paths_are_still_globally_throttled(self, rate_limited_client):
        from app.core.config import get_settings

        budget = int(get_settings().rate_limit_global.split("/")[0])
        headers = {"X-Real-IP": "198.51.100.90"}
        for i in range(budget):
            assert rate_limited_client.get(f"{API_PREFIX}/public/probe-{i}", headers=headers).status_code == 404
        assert rate_limited_client.get(f"{API_PREFIX}/public/probe-x", headers=headers).status_code == 429
