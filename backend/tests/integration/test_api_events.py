from conftest import API_PREFIX, auth_header, login, make_event, register_user


def _second_user(client):
    register_user(client, email="guest@example.com", display_name="Guest")
    return auth_header(client, email="guest@example.com")


class TestCreateEvent:
    def test_create_event_requires_face_profile(self, client, profile_service):
        register_user(client)
        profile_service.has_profile.return_value = False
        response = make_event(client, auth_header(client))
        assert response.status_code == 400
        assert "face profile" in response.json()["detail"]

    def test_create_event_success(self, client):
        register_user(client)
        response = make_event(client, auth_header(client), name="Summer Party")
        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Summer Party"
        assert body["join_token"]
        assert body["active"] is True

    def test_create_event_with_expiry_in_past_rejected(self, client):
        from datetime import datetime, timedelta, timezone

        register_user(client)
        starts_at = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        expires_at = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        response = make_event(
            client,
            auth_header(client),
            extra={"starts_at": starts_at, "expires_at": expires_at},
        )
        assert response.status_code == 422

    def test_create_event_rejects_empty_name(self, client):
        register_user(client)
        response = make_event(client, auth_header(client), name="")
        assert response.status_code == 422


class TestEventLifecycle:
    def test_list_my_events_empty_then_returns_created(self, client):
        register_user(client)
        headers = auth_header(client)
        assert client.get(f"{API_PREFIX}/events", headers=headers).json() == []
        created = make_event(client, headers, name="My Event").json()
        body = client.get(f"{API_PREFIX}/events", headers=headers).json()
        assert [e["name"] for e in body] == ["My Event"]
        assert body[0]["join_token"] == created["join_token"]

    def test_search_excludes_join_token(self, client):
        register_user(client)
        headers = auth_header(client)
        make_event(client, headers, name="Hawaii Trip")
        body = client.get(f"{API_PREFIX}/events/search", params={"q": "hawaii"}, headers=headers)
        assert body.status_code == 200
        items = body.json()
        assert len(items) == 1
        assert items[0]["name"] == "Hawaii Trip"
        assert "join_token" not in items[0]

    def test_get_event_detail_as_member(self, client):
        register_user(client)
        headers = auth_header(client)
        event = make_event(client, headers).json()
        body = client.get(f"{API_PREFIX}/events/{event['id']}", headers=headers)
        assert body.status_code == 200
        assert body.json()["attendee_count"] == 1  # owner is implicitly an attendee

    def test_get_event_detail_non_member_forbidden(self, client):
        register_user(client)
        owner_headers = auth_header(client)
        event = make_event(client, owner_headers).json()

        register_user(client, email="intruder@example.com", display_name="Intruder")
        intruder_headers = auth_header(client, email="intruder@example.com")
        response = client.get(f"{API_PREFIX}/events/{event['id']}", headers=intruder_headers)
        assert response.status_code == 403

    def test_get_event_detail_not_found(self, client):
        register_user(client)
        response = client.get(f"{API_PREFIX}/events/does-not-exist", headers=auth_header(client))
        assert response.status_code == 404


class TestJoinEvent:
    def test_join_by_token_success_then_duplicate(self, client):
        register_user(client)
        owner_headers = auth_header(client)
        event = make_event(client, owner_headers).json()

        guest_headers = _second_user(client)
        first = client.get(f"{API_PREFIX}/events/join/{event['join_token']}", headers=guest_headers)
        assert first.status_code == 200
        assert first.json()["joined"] is True

        second = client.get(f"{API_PREFIX}/events/join/{event['join_token']}", headers=guest_headers)
        assert second.status_code == 200
        assert second.json()["joined"] is False

    def test_join_unknown_token_not_found(self, client):
        register_user(client)
        response = client.get(f"{API_PREFIX}/events/join/nope", headers=auth_header(client))
        assert response.status_code == 404

    def test_joined_event_appears_in_search_for_guest(self, client):
        register_user(client)
        owner_headers = auth_header(client)
        event = make_event(client, owner_headers, name="Open House").json()

        guest_headers = _second_user(client)
        client.get(f"{API_PREFIX}/events/join/{event['join_token']}", headers=guest_headers)
        items = client.get(f"{API_PREFIX}/events/search", params={"q": "Open"}, headers=guest_headers).json()
        assert [e["name"] for e in items] == ["Open House"]


class TestScan:
    def test_scan_reports_images_processed_and_faces_found(self, client, profile_service):
        register_user(client)
        profile_service.enroll.return_value = 1
        files = [
            ("files", ("face.jpg", b"fake-jpeg-bytes", "image/jpeg")),
            ("files", ("face2.jpg", b"fake-jpeg-bytes", "image/jpeg")),
        ]
        response = client.post(
            f"{API_PREFIX}/users/me/scan",
            files=files,
            headers=auth_header(client),
        )
        assert response.status_code == 200
        body = response.json()
        assert body["images_processed"] == 2
        assert body["faces_found"] == 1
        profile_service.enroll.assert_called_once()

    def test_scan_requires_auth(self, client):
        files = [("files", ("face.jpg", b"data", "image/jpeg"))]
        assert (
            client.post(f"{API_PREFIX}/users/me/scan", files=files).status_code == 401
        )

    def test_scan_bad_image_count_rejected(self, client):
        register_user(client)
        response = client.post(
            f"{API_PREFIX}/users/me/scan",
            files=[],
            headers=auth_header(client),
        )
        assert response.status_code == 422