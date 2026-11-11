import pytest
from conftest import API_PREFIX, login


@pytest.fixture
def rate_limited_client(client):
    """Enable the shared limiter with fresh counters for rate-limit tests."""
    from app.core.rate_limit import limiter

    limiter.reset()
    limiter.enabled = True
    try:
        yield client
    finally:
        limiter.reset()
        limiter.enabled = False


class TestRateLimiting:
    def test_auth_login_enforces_stricter_limit(self, rate_limited_client):
        headers = {"X-Real-IP": "198.51.100.1"}
        for _ in range(10):
            res = rate_limited_client.post(
                f"{API_PREFIX}/auth/login",
                json={"email": "nobody@example.com", "password": "wrongpassword"},
                headers=headers,
            )
            assert res.status_code == 401

        blocked = rate_limited_client.post(
            f"{API_PREFIX}/auth/login",
            json={"email": "nobody@example.com", "password": "wrongpassword"},
            headers=headers,
        )
        assert blocked.status_code == 429
        assert "Retry-After" in blocked.headers
        assert blocked.json()["limit"] == "10 per 1 minute"

    def test_global_limit_blocks_bot_probing_random_404_paths(self, rate_limited_client):
        headers = {"X-Real-IP": "198.51.100.2"}
        for i in range(60):
            res = rate_limited_client.get(f"/.env-probe-{i}", headers=headers)
            assert res.status_code == 404

        blocked = rate_limited_client.get("/.env", headers=headers)
        assert blocked.status_code == 429
        assert blocked.json()["detail"] == "Too many requests. Please slow down."

    def test_different_ips_have_independent_buckets(self, rate_limited_client):
        for _ in range(10):
            login_res = rate_limited_client.post(
                f"{API_PREFIX}/auth/login",
                json={"email": "nobody@example.com", "password": "wrongpassword"},
                headers={"X-Real-IP": "198.51.100.3"},
            )
            assert login_res.status_code == 401

        assert (
            rate_limited_client.post(
                f"{API_PREFIX}/auth/login",
                json={"email": "nobody@example.com", "password": "wrongpassword"},
                headers={"X-Real-IP": "198.51.100.3"},
            ).status_code
            == 429
        )

        # Spoofing leftmost X-Forwarded-For does not bypass when X-Real-IP is the same
        assert (
            rate_limited_client.post(
                f"{API_PREFIX}/auth/login",
                json={"email": "nobody@example.com", "password": "wrongpassword"},
                headers={
                    "X-Forwarded-For": "9.9.9.9, 198.51.100.3",
                    "X-Real-IP": "198.51.100.3",
                },
            ).status_code
            == 429
        )

        # A genuinely different client IP is unaffected
        other_ip = rate_limited_client.post(
            f"{API_PREFIX}/auth/login",
            json={"email": "nobody@example.com", "password": "wrongpassword"},
            headers={"X-Real-IP": "198.51.100.4"},
        )
        assert other_ip.status_code == 401

    def test_ping_and_metrics_are_exempt(self, rate_limited_client):
        headers = {"X-Real-IP": "198.51.100.5"}
        for _ in range(70):
            assert rate_limited_client.get("/ping", headers=headers).status_code == 200
            assert rate_limited_client.get("/metrics", headers=headers).status_code == 200

