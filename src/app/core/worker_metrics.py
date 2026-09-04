"""Minimal Prometheus metrics HTTP server for the RQ worker.

The worker exposes its own /metrics (on port 9100) so Prometheus has a direct
"is the worker process actually alive" signal — `up{job="worker"}` — plus the
number of jobs currently being processed. Kept dependency-light: a stdlib
`ThreadingHTTPServer`, no web framework needed inside the worker.
"""

from __future__ import annotations

import logging
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from prometheus_client import CONTENT_TYPE_LATEST, Gauge, generate_latest

logger = logging.getLogger("app.worker_metrics")

WORKER_UP = Gauge("worker_up", "1 if the worker process is alive and serving metrics")


class _MetricsHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/metrics":
            self.send_response(404)
            self.end_headers()
            return
        body = generate_latest()
        self.send_response(200)
        self.send_header("Content-Type", CONTENT_TYPE_LATEST)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: Any) -> None:
        # Keep request logs out of the worker's structured logging.
        return


def start_metrics_server(port: int = 9100) -> threading.Thread:
    """Start the metrics HTTP server in a daemon thread. Returns the thread."""
    WORKER_UP.set(1)

    server = ThreadingHTTPServer(("0.0.0.0", port), _MetricsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True, name="metrics-http")
    thread.start()
    logger.info("worker metrics server listening on :%d", port)
    return thread
