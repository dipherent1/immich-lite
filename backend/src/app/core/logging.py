"""Centralized logging setup.

One place configures logging for the whole app: console output plus a rotating
file, at a level read from settings. Never log passwords, tokens, or password
hashes anywhere.

Logs are structured JSON, one object per line, so they are machine-parseable
in production (Loki/ELK/CloudWatch) instead of free-form text. In addition a
set of "correlation" context variables (request_id, job_id, user_id) is
attached to every record that shares a context, so a single upload can be
traced end-to-end across the API, the RQ queue and the worker.
"""

from __future__ import annotations

import json
import logging
import logging.handlers
from contextvars import ContextVar
from typing import Any

from app.core.config import get_settings


def correlation_context() -> dict[str, Any]:
    """Return the currently-set correlation fields for this context."""
    fields: dict[str, Any] = {}
    for var in CORRELATION_VARS:
        value = var.get()
        if value is not None:
            fields[var.name] = value
    return fields


def set_correlation(**fields: Any) -> None:
    """Attach correlation fields (e.g. request_id, job_id) to the current context."""
    for var in CORRELATION_VARS:
        if fields.get(var.name) is not None:
            var.set(str(fields[var.name]))


def clear_correlation() -> None:
    for var in CORRELATION_VARS:
        var.set(None)


class JsonFormatter(logging.Formatter):
    """Emit a single JSON object per log line.

    Base fields (timestamp, level, logger) plus `message`, plus any extra
    kwargs passed to the logging call, plus the current correlation context
    (request_id / job_id / user_id) so logs crossing service boundaries can be
    grouped. `exc_info` is rendered as a compact traceback string.
    """

    def format(self, record: logging.LogRecord) -> str:
        data: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname or logging.getLevelName(record.levelno),
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Merge correlation context (request_id / job_id / user_id) if set.
        for name, value in correlation_context().items():
            data[name] = value

        # Merge any extra= fields passed to the logging call.
        extra = getattr(record, "extra_fields", None)
        if extra:
            data.update({k: v for k, v in extra.items() if k not in data})

        if record.exc_info:
            data["exc"] = self.formatException(record.exc_info)

        return json.dumps(data, default=str)


def _console_formatter() -> logging.Formatter:
    """Human-readable console formatter for local dev; still includes correlation."""
    class _Human(logging.Formatter):
        def format(self, record: logging.LogRecord) -> str:
            base = _DATE_FORMAT and self.formatTime(record, "%Y-%m-%d %H:%M:%S")
            ctx = ""
            corr = correlation_context()
            if corr:
                ctx = " " + " ".join(f"{k}={v}" for k, v in corr.items())
            extra = getattr(record, "extra_fields", None)
            extra_str = ""
            if extra:
                extra_str = " " + " ".join(f"{k}={v}" for k, v in extra.items())
            line = f"{base} [{record.levelname}] {record.name}{ctx}: {record.getMessage()}{extra_str}"
            if record.exc_info:
                line += "\n" + self.formatException(record.exc_info)
            return line

    return _Human(_LOG_FORMAT, datefmt=_DATE_FORMAT)


_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

CORRELATION_VARS: tuple[ContextVar, ...] = (
    ContextVar("request_id", default=None),
    ContextVar("job_id", default=None),
    ContextVar("user_id", default=None),
)


def setup_logging() -> logging.Logger:
    """Configure root/console + rotating-file handlers. Idempotent."""
    settings = get_settings()

    root = logging.getLogger()
    # Avoid stacking duplicate handlers if called more than once.
    for existing in list(root.handlers):
        if isinstance(existing, logging.StreamHandler) and not isinstance(
            existing, logging.handlers.RotatingFileHandler
        ):
            root.removeHandler(existing)

    level = getattr(logging, settings.log_level.upper(), logging.INFO)
    root.setLevel(level)

    file_formatter = JsonFormatter()

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(_console_formatter())
        root.addHandler(console)

    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in root.handlers):
        try:
            from pathlib import Path

            log_path = Path(settings.log_file)
            if not log_path.is_absolute():
                _PROJECT_ROOT = Path(__file__).resolve().parents[3]
                log_path = _PROJECT_ROOT / log_path
            log_path.parent.mkdir(parents=True, exist_ok=True)

            file_handler = logging.handlers.RotatingFileHandler(
                log_path,
                maxBytes=settings.log_max_bytes,
                backupCount=settings.log_backup_count,
                encoding="utf-8",
            )
            # File handler emits structured JSON for machine parsing.
            file_handler.setFormatter(file_formatter)
            root.addHandler(file_handler)
        except Exception:  # logging must never crash the app
            logging.getLogger(__name__).warning(
                "Could not set up file logging to %s; continuing with console only",
                settings.log_file,
                exc_info=True,
            )

    return logging.getLogger("app")


def log_exception(logger: logging.Logger, context: str, exc: BaseException) -> None:
    """Log an exception with its full traceback and a human context string."""
    logger.exception("%s: %s: %s", context, type(exc).__name__, exc)


def log_error_extra(logger: logging.Logger, context: str, fields: dict[str, Any]) -> None:
    """Log an error-level message with any extra structured fields (non-secret)."""
    logger.error(context, extra={"extra_fields": fields})
