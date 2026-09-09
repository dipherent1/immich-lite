"""Prometheus metrics for the API + RQ queue.

Exposes a /metrics endpoint (in `main.py`) scraped by Prometheus every ~15s.
Kept intentionally small: HTTP latency/status, RQ enqueue counts, and live RQ
queue depth (refreshed on each scrape from Redis). No secrets, no user
identifiers — only counters/gauges/histograms at the service level.
"""

from __future__ import annotations

import logging

from prometheus_client import Counter, Gauge, Histogram

logger = logging.getLogger("app.metrics")

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

RQ_JOBS_ENQUEUED_TOTAL = Counter(
    "rq_jobs_enqueued_total",
    "Number of RQ jobs enqueued, by queue name",
    ["queue"],
)

RQ_QUEUE_DEPTH = Gauge(
    "rq_queue_depth",
    "Current number of jobs waiting in an RQ queue (refreshed on scrape)",
    ["queue"],
)


def observe_http(method: str, path: str, status_code: int, duration_s: float) -> None:
    """Record a single completed HTTP request. `path` is the route template."""
    status_cls = f"{status_code // 100}xx"
    HTTP_REQUESTS_TOTAL.labels(method=method, path=path, status=status_cls).inc()
    HTTP_REQUEST_DURATION_SECONDS.labels(method=method, path=path).observe(duration_s)


def record_enqueue(queue: str) -> None:
    RQ_JOBS_ENQUEUED_TOTAL.labels(queue=queue).inc()


def refresh_rq_metrics(redis_url: str) -> None:
    """Update the live queue-depth gauge from Redis. Safe on any failure."""
    try:
        from redis import Redis
        from rq import Queue

        connection = Redis.from_url(redis_url)
        for queue_name in ("photos",):
            try:
                depth = Queue(queue_name, connection=connection).count
            except Exception:  # queue may not exist yet
                depth = 0
            RQ_QUEUE_DEPTH.labels(queue=queue_name).set(depth)
    except Exception:  # scraping must never crash the metrics endpoint
        logger.warning("could not refresh RQ metrics", exc_info=True)
