import json

import pytest

from app.models.photo_match import PhotoMatch
from conftest import API_PREFIX, auth_header, make_event, register_user

_JPEG = b"\xff\xd8\xff\xe0fake-jpeg-bytes\xff\xd9"


@pytest.fixture(autouse=True)
def _no_enqueue(monkeypatch):
    monkeypatch.setattr(
        "app.services.photo_service.enqueue_photo_processing", lambda photo_id: None
    )


def _upload(client, headers, event_id, data=_JPEG, filename="pic.jpg"):
    return client.post(
        f"{API_PREFIX}/events/{event_id}/photos",
        headers=headers,
        files={"file": (filename, data, "image/jpeg")},
    )


class TestPhotoUpload:
    def test_upload_and_fetch_roundtrip(self, client):
        register_user(client)
        headers = auth_header(client)
        event = make_event(client, headers).json()

        upload = _upload(client, headers, event["id"])
        assert upload.status_code == 201
        body = upload.json()
        assert body["event_id"] == event["id"]
        assert body["status"] == "pending"
        assert body["storage_path"].startswith(f"photos/{event['id']}/")

        listing = client.get(f"{API_PREFIX}/events/{event['id']}/photos", headers=headers)
        assert listing.status_code == 200
        items = listing.json()["items"]
        assert [i["id"] for i in items] == [body["id"]]
        assert listing.json()["has_more"] is False

        fetched = client.get(
            f"{API_PREFIX}/events/{event['id']}/photos/{body['id']}/file",
            headers=headers,
        )
        assert fetched.status_code == 200
        assert fetched.content == _JPEG
        assert fetched.headers["content-type"] == "image/jpeg"

    def test_upload_by_non_member_forbidden(self, client):
        register_user(client)
        owner_headers = auth_header(client)
        event = make_event(client, owner_headers).json()

        register_user(client, email="intruder@example.com", display_name="Intruder")
        intruder_headers = auth_header(client, email="intruder@example.com")
        assert _upload(client, intruder_headers, event["id"]).status_code == 403

    def test_upload_to_unknown_event_not_found(self, client):
        register_user(client)
        assert _upload(client, auth_header(client), "no-such-event").status_code == 404

    def test_upload_unsupported_extension_rejected(self, client):
        register_user(client)
        headers = auth_header(client)
        event = make_event(client, headers).json()
        response = _upload(client, headers, event["id"], filename="evil.exe")
        assert response.status_code == 422

    def test_upload_oversized_file_rejected(self, client):
        register_user(client)
        headers = auth_header(client)
        event = make_event(client, headers).json()
        data = b"x" * (20 * 1024 * 1024 + 1)
        assert _upload(client, headers, event["id"], data=data).status_code == 413


class TestPhotoList:
    def test_photo_list_paginates(self, client):
        register_user(client)
        headers = auth_header(client)
        event = make_event(client, headers).json()
        for i in range(3):
            _upload(client, headers, event["id"], filename=f"pic{i}.jpg")
        response = client.get(
            f"{API_PREFIX}/events/{event['id']}/photos",
            params={"offset": 0, "limit": 2},
            headers=headers,
        )
        body = response.json()
        assert len(body["items"]) == 2
        assert body["has_more"] is True
        assert body["next_offset"] == 2
        tail = client.get(
            f"{API_PREFIX}/events/{event['id']}/photos",
            params={"offset": 2, "limit": 2},
            headers=headers,
        ).json()
        assert len(tail["items"]) == 1
        assert tail["has_more"] is False

    def test_photo_list_non_member_forbidden(self, client):
        register_user(client)
        owner_headers = auth_header(client)
        event = make_event(client, owner_headers).json()
        _upload(client, owner_headers, event["id"])

        register_user(client, email="intruder@example.com", display_name="Intruder")
        intruder_headers = auth_header(client, email="intruder@example.com")
        assert (
            client.get(f"{API_PREFIX}/events/{event['id']}/photos", headers=intruder_headers).status_code
            == 403
        )

    def test_photo_file_missing_on_disk_returns_404(self, client, tmp_path):
        register_user(client)
        headers = auth_header(client)
        event = make_event(client, headers).json()
        photo = _upload(client, headers, event["id"]).json()
        file_url = f"{API_PREFIX}/events/{event['id']}/photos/{photo['id']}/file"

        assert client.get(file_url, headers=headers).status_code == 200
        (tmp_path / photo["storage_path"]).unlink()
        assert client.get(file_url, headers=headers).status_code == 404


class TestMatchesFeed:
    def test_feed_lists_only_current_users_matches(self, client, db_session):
        current = register_user(client).json()
        owner = register_user(client, email="owner@example.com", display_name="Owner").json()
        owner_headers = auth_header(client, email="owner@example.com")
        event = make_event(client, owner_headers, name="Reunion").json()

        headers = auth_header(client)
        client.get(f"{API_PREFIX}/events/join/{event['join_token']}", headers=headers)
        upload = _upload(client, owner_headers, event["id"], filename="group.jpg")
        photo_id = upload.json()["id"]

        db_session.add(
            PhotoMatch(
                photo_id=photo_id,
                user_id=current["id"],
                similarity=0.85,
                bbox=json.dumps({"x1": 1, "y1": 2, "x2": 3, "y2": 4}),
            )
        )
        db_session.add(
            PhotoMatch(
                photo_id=photo_id,
                user_id=owner["id"],
                similarity=0.99,
                bbox="{}",
            )
        )
        db_session.commit()

        feed = client.get(f"{API_PREFIX}/matches/me", headers=headers)
        assert feed.status_code == 200
        items = feed.json()["items"]
        assert len(items) == 1
        assert items[0]["photo_id"] == photo_id
        assert items[0]["event_id"] == event["id"]
        assert items[0]["event_name"] == "Reunion"
        assert items[0]["similarity"] == 0.85
        assert items[0]["bbox"] == {"x1": 1, "y1": 2, "x2": 3, "y2": 4}
        assert items[0]["file_url"] == f"/api/v1/events/{event['id']}/photos/{photo_id}/file"

    def test_feed_empty_for_user_without_matches(self, client):
        register_user(client)
        headers = auth_header(client)
        body = client.get(f"{API_PREFIX}/matches/me", headers=headers).json()
        assert body["items"] == []
        assert body["has_more"] is False