"""Centralized logging setup.

One place configures logging for the whole app: console output plus a rotating
file, at a level read from settings. Never log passwords, tokens, or password
hashes anywhere.
"""

from __future__ import annotations

import logging
import logging.handlers
from typing import Any

from app.core.config import get_settings

_LOG_FORMAT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


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

    formatter = logging.Formatter(_LOG_FORMAT, datefmt=_DATE_FORMAT)

    if not any(isinstance(h, logging.StreamHandler) for h in root.handlers):
        console = logging.StreamHandler()
        console.setFormatter(formatter)
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
            file_handler.setFormatter(formatter)
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
    extras = " ".join(f"{k}={v}" for k, v in fields.items())
    logger.error("%s (%s)", context, extras)
