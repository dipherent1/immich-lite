import json
from types import SimpleNamespace

from limits import parse
from slowapi.errors import RateLimitExceeded
from slowapi.wrappers import Limit
from starlette.requests import Request

from app.core.rate_limit import _client_ip, rate_limit_exceeded_handler


def _make_request(headers: dict[str, str] | None = None, client_host: str | None = "10.0.0.1") -> Request:
    raw_headers = [
        (k.lower().encode("latin-1"), v.encode("latin-1"))
        for k, v in (headers or {}).items()
    ]
    scope = {
        "type": "http",
        "method": "GET",
        "path": "/api/v1/events",
        "headers": raw_headers,
        "client": (client_host, 12345) if client_host else None,
    }
    return Request(scope)


class TestClientIp:
    def test_prefers_x_real_ip_over_x_forwarded_for(self):
        request = _make_request(
            headers={
                "X-Real-IP": "203.0.113.9",
                "X-Forwarded-For": "1.2.3.4, 203.0.113.9",
            }
        )
        assert _client_ip(request) == "203.0.113.9"

    def test_takes_rightmost_x_forwarded_for_ignoring_spoofed_leftmost(self):
        request = _make_request(
            headers={"X-Forwarded-For": "9.9.9.9, 198.51.100.42"}
        )
        assert _client_ip(request) == "198.51.100.42"

    def test_falls_back_to_client_host(self):
        request = _make_request(client_host="192.0.2.55")
        assert _client_ip(request) == "192.0.2.55"

    def test_returns_unknown_when_no_client(self):
        request = _make_request(client_host=None)
        assert _client_ip(request) == "unknown"


class TestRateLimitExceededHandler:
    def test_returns_429_with_readable_limit_and_retry_after(self):
        request = _make_request(headers={"X-Real-IP": "203.0.113.10"})
        limit = Limit(
            limit=parse("10/minute"),
            key_func=_client_ip,
            scope=None,
            per_method=False,
            methods=None,
            error_message=None,
            exempt_when=None,
            cost=1,
            override_defaults=True,
        )
        exc = RateLimitExceeded(limit)

        response = rate_limit_exceeded_handler(request, exc)

        assert response.status_code == 429
        assert response.headers["Retry-After"] == "60"
        body = json.loads(response.body.decode("utf-8"))
        assert body["detail"] == "Too many requests. Please slow down."
        assert body["limit"] == "10 per 1 minute"

