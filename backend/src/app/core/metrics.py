"""Prometheus metrics for the API + job queue.

Exposes a /metrics endpoint (in `main.py`) scraped by Prometheus every ~15s.
Kept intentionally small: HTTP latency/status and enqueue counts; RabbitMQ
queue depth/consumer health comes from `rabbitmq-exporter`. No secrets, no user
identifiers — only counters/gauges/histograms at the service level.
"""

from __future__ import annotations

from prometheus_client import Counter, Histogram

# HTTP request totals and latency. `path` is the route template (e.g.
# `/api/v1/events/{event_id}`), not the raw URL, so cardinality stays bounded.
HTTP_REQUESTS_TOTAL = Counter(
    "http_requests_total",
    "Total HTTP requests handled, by method / route template / status class",
    ["method", "path", "status"],
)

HTTP_REQUEST_DURATION_SECONDS = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency in seconds, by method / route template",
    ["method", "path"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0),
)

CELERY_JOBS_ENQUEUED_TOTAL = Counter(
    "celery_jobs_enqueued_total",
    "Number of Celery jobs enqueued, by queue name",
    ["queue"],
)


def observe_http(method: str, path: str, status_code: int, duration_s: float) -> None:
    """Record a single completed HTTP request. `path` is the route template."""
    status_cls = f"{status_code // 100}xx"
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status_cls).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration_s)


def record_enqueue(queue: str) -> None:
    CELERY_JOBS_ENQUEUED_TOTAL.labels(queue=queue).inc()
