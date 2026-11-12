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


class TestEventCover:
    def test_first_uploaded_photo_becomes_default_cover(self, client):
        register_user(client)
        headers = auth_header(client)
        event = make_event(client, headers, name="Cover Test").json()
        assert event["cover_photo_id"] is None
        assert event["cover_url"] is None

        first = _upload(client, headers, event["id"], filename="first.jpg").json()
        detail = client.get(f"{API_PREFIX}/events/{event['id']}", headers=headers).json()
        assert detail["cover_photo_id"] == first["id"]
        assert detail["cover_url"] == f"/api/v1/events/{event['id']}/photos/{first['id']}/file"

        # Subsequent uploads must not overwrite the default cover.
        _upload(client, headers, event["id"], filename="second.jpg")
        detail_after = client.get(f"{API_PREFIX}/events/{event['id']}", headers=headers).json()
        assert detail_after["cover_photo_id"] == first["id"]

        # Public search results must still exclude private image references.
        search_items = client.get(
            f"{API_PREFIX}/events/search", params={"q": "Cover Test"}, headers=headers
        ).json()
        assert len(search_items) == 1
        assert "cover_photo_id" not in search_items[0]
        assert "cover_url" not in search_items[0]

    def test_creator_can_select_and_upload_cover(self, client):
        register_user(client)
        headers = auth_header(client)
        event = make_event(client, headers, name="Editable Cover").json()
        first = _upload(client, headers, event["id"], filename="first.jpg").json()
        second = _upload(client, headers, event["id"], filename="second.jpg").json()

        # Creator picks the second photo as the cover.
        res = client.patch(
            f"{API_PREFIX}/events/{event['id']}/cover",
            json={"photo_id": second["id"]},
            headers=headers,
        )
        assert res.status_code == 200
        assert res.json()["cover_photo_id"] == second["id"]
        assert res.json()["cover_url"] == f"/api/v1/events/{event['id']}/photos/{second['id']}/file"
        assert res.json()["cover_photo_id"] != first["id"]

        # Creator uploads a brand-new cover image directly.
        custom_bytes = b"\xff\xd8\xff\xe0custom-cover-bytes\xff\xd9"
        uploaded = client.post(
            f"{API_PREFIX}/events/{event['id']}/cover",
            headers=headers,
            files={"file": ("banner.jpg", custom_bytes, "image/jpeg")},
        )
        assert uploaded.status_code == 200
        new_cover_id = uploaded.json()["cover_photo_id"]
        assert new_cover_id not in {first["id"], second["id"]}

        fetched = client.get(uploaded.json()["cover_url"], headers=headers)
        assert fetched.status_code == 200
        assert fetched.content == custom_bytes

    def test_non_creator_attendee_cannot_edit_cover(self, client):
        register_user(client)
        owner_headers = auth_header(client)
        event = make_event(client, owner_headers).json()
        first = _upload(client, owner_headers, event["id"], filename="first.jpg").json()
        second = _upload(client, owner_headers, event["id"], filename="second.jpg").json()

        register_user(client, email="guest@example.com", display_name="Guest")
        guest_headers = auth_header(client, email="guest@example.com")
        client.get(f"{API_PREFIX}/events/join/{event['join_token']}", headers=guest_headers)

        patch_res = client.patch(
            f"{API_PREFIX}/events/{event['id']}/cover",
            json={"photo_id": second["id"]},
            headers=guest_headers,
        )
        assert patch_res.status_code == 403

        post_res = client.post(
            f"{API_PREFIX}/events/{event['id']}/cover",
            headers=guest_headers,
            files={"file": ("hack.jpg", _JPEG, "image/jpeg")},
        )
        assert post_res.status_code == 403

        detail = client.get(f"{API_PREFIX}/events/{event['id']}", headers=owner_headers).json()
        assert detail["cover_photo_id"] == first["id"]

    def test_set_cover_rejects_photo_from_other_event(self, client):
        register_user(client)
        headers = auth_header(client)
        ev1 = make_event(client, headers, name="Event 1").json()
        ev2 = make_event(client, headers, name="Event 2").json()
        other_photo = _upload(client, headers, ev2["id"], filename="other.jpg").json()

        res = client.patch(
            f"{API_PREFIX}/events/{ev1['id']}/cover",
            json={"photo_id": other_photo["id"]},
            headers=headers,
        )
        assert res.status_code == 404