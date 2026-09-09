from conftest import API_PREFIX, auth_header, login, register_user


class TestRegister:
    def test_register_returns_public_user(self, client):
        response = register_user(client)
        assert response.status_code == 201
        body = response.json()
        assert body["email"] == "user@example.com"
        assert body["display_name"] == "Test User"
        assert "has_face_profile" in body
        assert "hashed_password" not in body

    def test_register_duplicate_email_conflict(self, client):
        assert register_user(client).status_code == 201
        response = register_user(client)
        assert response.status_code == 409

    def test_register_short_password_rejected(self, client):
        response = register_user(client, password="short")
        assert response.status_code == 422

    def test_register_invalid_email_rejected(self, client):
        response = register_user(client, email="not-an-email")
        assert response.status_code == 422


class TestLogin:
    def test_login_success_returns_bearer_token(self, client):
        register_user(client)
        response = login(client)
        assert response.status_code == 200
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]

    def test_login_wrong_password_unauthorized(self, client):
        register_user(client)
        assert login(client, password="wrongpass").status_code == 401

    def test_login_unknown_user_unauthorized(self, client):
        assert login(client, email="nobody@example.com").status_code == 401


class TestMe:
    def test_me_with_valid_token(self, client):
        register_user(client)
        headers = auth_header(client)
        response = client.get(f"{API_PREFIX}/users/me", headers=headers)
        assert response.status_code == 200
        body = response.json()
        assert body["email"] == "user@example.com"
        assert body["display_name"] == "Test User"
        assert body["has_face_profile"] is True

    def test_me_without_token_unauthorized(self, client):
        assert client.get(f"{API_PREFIX}/users/me").status_code == 401

    def test_me_with_garbage_token_unauthorized(self, client):
        assert (
            client.get(
                f"{API_PREFIX}/users/me",
                headers={"Authorization": "Bearer not-a-real-token"},
            ).status_code
            == 401
        )

    def test_has_face_profile_reflects_profile_repo(self, client, profile_repo):
        register_user(client)
        profile_repo.has_profile.return_value = False
        response = client.get(f"{API_PREFIX}/users/me", headers=auth_header(client))
        assert response.status_code == 200
        assert response.json()["has_face_profile"] is False