"""Telegram alerts for server errors, with flood protection.

Any log record at ERROR or above (unhandled API exceptions, failed Celery tasks,
`logger.exception(...)` calls) becomes a Telegram message, *unless* sending it
would risk Telegram treating the bot as a spammer. Defences, in order:

1. **Never blocks the caller.** `emit()` only formats the record and puts it on a
   small bounded queue; a background thread does the throttling and the HTTP call.
   A full queue drops records instead of waiting.
2. **De-duplication.** An error is fingerprinted by *where* it happens (logger +
   exception type + innermost app frame), not by its message, so "user 123 failed"
   and "user 456 failed" are one problem. The first occurrence is sent; repeats are
   suppressed for `dedupe_seconds` and counted, and the next alert reports
   "(+N similar suppressed)".
3. **Global budget.** At most `max_per_minute` / `max_per_hour` messages overall,
   however many different errors occur. Over budget, alerts are dropped.
4. **Flood notice.** When `flood_threshold` alerts have been suppressed within one
   storm, a single "error flood" message is sent (once per storm) so you know to
   look at the logs instead of waiting for individual alerts.
5. **Telegram back-pressure.** Messages are spaced >= 1.2s apart, and an HTTP 429
   pauses all sending for the `retry_after` Telegram asks for.

Counters live in Redis when available, so the API and every worker process share
one budget and restarts don't reset it; otherwise they fall back to per-process
memory. Messages are scrubbed of tokens, JWTs, share links, emails and DB
passwords before leaving the server. Nothing here ever raises into the app.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import queue
import re
import threading
import time
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Callable, Protocol

logger = logging.getLogger("app.alerting")

# Loggers whose records are never alerted on: our own (avoids feedback loops) and
# the HTTP stack we use to send. `app.request` is skipped because an unhandled
# exception already produces its own traceback record; the request-line 5xx record
# would just be a second alert for the same failure.
_IGNORED_LOGGERS = ("app.alerting", "urllib3", "httpx", "httpcore", "app.request")

_KEY_PREFIX = "immich_alert:"
_PAUSE_KEY = "pause"
_DROPPED_KEY = "dropped"


# --- Storage for the throttle -------------------------------------------------


class Store(Protocol):
    """The few atomic operations the throttle needs (Redis or in-memory)."""

    def set_nx(self, key: str, ttl: int) -> bool: ...
    def set(self, key: str, ttl: int) -> None: ...
    def incr(self, key: str, ttl: int) -> int: ...
    def decr(self, key: str) -> None: ...
    def getdel(self, key: str) -> int: ...
    def delete(self, key: str) -> None: ...
    def exists(self, key: str) -> bool: ...


class MemoryStore:
    """Per-process fallback store. `clock` is injectable so tests can fast-forward."""

    def __init__(self, clock: Callable[[], float] = time.time) -> None:
        self._clock = clock
        self._data: dict[str, tuple[int, float]] = {}
        self._lock = threading.Lock()

    def _live(self, key: str) -> tuple[int, float] | None:
        item = self._data.get(key)
        if item is None:
            return None
        if item[1] <= self._clock():
            del self._data[key]
            return None
        return item

    def _gc(self) -> None:
        if len(self._data) > 2000:
            now = self._clock()
            for k in [k for k, (_, exp) in self._data.items() if exp <= now]:
                del self._data[k]

    def set_nx(self, key: str, ttl: int) -> bool:
        with self._lock:
            self._gc()
            if self._live(key) is not None:
                return False
            self._data[key] = (1, self._clock() + ttl)
            return True

    def set(self, key: str, ttl: int) -> None:
        with self._lock:
            self._data[key] = (1, self._clock() + ttl)

    def incr(self, key: str, ttl: int) -> int:
        with self._lock:
            item = self._live(key)
            value = (item[0] if item else 0) + 1
            self._data[key] = (value, self._clock() + ttl)  # sliding expiry
            return value

    def decr(self, key: str) -> None:
        with self._lock:
            item = self._live(key)
            if item is not None:
                self._data[key] = (max(0, item[0] - 1), item[1])

    def getdel(self, key: str) -> int:
        with self._lock:
            item = self._live(key)
            self._data.pop(key, None)
            return item[0] if item else 0

    def delete(self, key: str) -> None:
        with self._lock:
            self._data.pop(key, None)

    def exists(self, key: str) -> bool:
        with self._lock:
            return self._live(key) is not None


class RedisStore:
    """Shared store so the API and all worker processes use one budget."""

    def __init__(self, client) -> None:
        self._r = client

    def _k(self, key: str) -> str:
        return f"{_KEY_PREFIX}{key}"

    def set_nx(self, key: str, ttl: int) -> bool:
        return bool(self._r.set(self._k(key), 1, nx=True, ex=ttl))

    def set(self, key: str, ttl: int) -> None:
        self._r.set(self._k(key), 1, ex=ttl)

    def incr(self, key: str, ttl: int) -> int:
        pipe = self._r.pipeline()
        pipe.incr(self._k(key))
        pipe.expire(self._k(key), ttl)  # sliding expiry, like MemoryStore
        return int(pipe.execute()[0])

    def decr(self, key: str) -> None:
        self._r.decr(self._k(key))

    def getdel(self, key: str) -> int:
        return int(self._r.getdel(self._k(key)) or 0)

    def delete(self, key: str) -> None:
        self._r.delete(self._k(key))

    def exists(self, key: str) -> bool:
        return bool(self._r.exists(self._k(key)))


class ResilientStore:
    """Use `primary` (Redis); if it errors, fall back to `fallback` (memory) for a
    while and retry later. Alerting must keep working, and stay bounded, when
    Redis is down."""

    def __init__(
        self,
        primary: Store,
        fallback: Store,
        retry_after: float = 30.0,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._primary = primary
        self._fallback = fallback
        self._retry_after = retry_after
        self._clock = clock
        self._down_until = 0.0

    def _call(self, name: str, *args):
        if self._clock() >= self._down_until:
            try:
                return getattr(self._primary, name)(*args)
            except Exception:
                self._down_until = self._clock() + self._retry_after
                logger.warning("alert throttle: Redis unavailable, using per-process memory")
        return getattr(self._fallback, name)(*args)

    def set_nx(self, key: str, ttl: int) -> bool:
        return self._call("set_nx", key, ttl)

    def set(self, key: str, ttl: int) -> None:
        self._call("set", key, ttl)

    def incr(self, key: str, ttl: int) -> int:
        return self._call("incr", key, ttl)

    def decr(self, key: str) -> None:
        self._call("decr", key)

    def getdel(self, key: str) -> int:
        return self._call("getdel", key)

    def delete(self, key: str) -> None:
        self._call("delete", key)

    def exists(self, key: str) -> bool:
        return self._call("exists", key)


# --- Throttle policy ----------------------------------------------------------


@dataclass(frozen=True)
class AlertPolicy:
    dedupe_seconds: int = 600  # same problem: at most one alert per 10 min
    max_per_minute: int = 5  # across all problems
    max_per_hour: int = 30
    flood_threshold: int = 20  # suppressed alerts in one storm before the flood notice
    flood_window_seconds: int = 300  # a storm ends after this long without drops


@dataclass
class Decision:
    action: str  # "send" | "duplicate" | "budget" | "paused"
    suppressed_similar: int = 0  # for "send": repeats suppressed since the last alert
    flood_notice: bool = False  # True on the one drop that crosses the flood threshold


class AlertThrottle:
    def __init__(
        self,
        store: Store,
        policy: AlertPolicy = AlertPolicy(),
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._store = store
        self._policy = policy
        self._clock = clock

    def is_paused(self) -> bool:
        return self._store.exists(_PAUSE_KEY)

    def pause(self, seconds: int) -> None:
        self._store.set(_PAUSE_KEY, max(1, min(int(seconds), 3600)))

    def decide(self, fingerprint: str) -> Decision:
        p = self._policy
        if self.is_paused():
            return self._drop("paused")
        if not self._store.set_nx(f"fp:{fingerprint}", p.dedupe_seconds):
            self._store.incr(f"cnt:{fingerprint}", 86400)
            return self._drop("duplicate")

        now = int(self._clock())
        minute_key, hour_key = f"min:{now // 60}", f"hr:{now // 3600}"
        if self._store.incr(minute_key, 120) > p.max_per_minute:
            self._store.decr(minute_key)
            self._store.delete(f"fp:{fingerprint}")  # let it try again once budget frees
            return self._drop("budget")
        if self._store.incr(hour_key, 7200) > p.max_per_hour:
            self._store.decr(hour_key)
            self._store.decr(minute_key)
            self._store.delete(f"fp:{fingerprint}")
            return self._drop("budget")

        return Decision("send", suppressed_similar=self._store.getdel(f"cnt:{fingerprint}"))

    def _drop(self, reason: str) -> Decision:
        n = self._store.incr(_DROPPED_KEY, self._policy.flood_window_seconds)
        return Decision(reason, flood_notice=(n == self._policy.flood_threshold))


# --- Building the message -----------------------------------------------------

_REDACTIONS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\d{6,}:[A-Za-z0-9_-]{30,}"), "<telegram-token>"),
    (re.compile(r"eyJ[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]{5,}\.[A-Za-z0-9_-]*"), "<jwt>"),
    (re.compile(r"(?i)bearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer <redacted>"),
    (
        re.compile(r"(?i)\b(token|password|passwd|secret|authorization|api[_-]?key)=[^&\s'\"]+"),
        r"\1=<redacted>",
    ),
    # share-link tokens appear in paths: /join/<t>, /events/join/<t>, /public/events/<t>
    (re.compile(r"(?i)(/join/|/public/events/)[A-Za-z0-9_-]{8,}"), r"\1<token>"),
    (re.compile(r"(?i)(://[^/\s:@]+):[^@\s/]+@"), r"\1:***@"),  # user:pass@host
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
]


def sanitize(text: str) -> str:
    for pattern, replacement in _REDACTIONS:
        text = pattern.sub(replacement, text)
    return text


_VOLATILE = re.compile(
    r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|\b[0-9a-fA-F]{12,}\b|\d+"
)


@dataclass
class AlertItem:
    level: str
    logger_name: str
    message: str
    exc_type: str | None
    traceback_lines: list[str]
    location: str | None
    fingerprint: str
    context: dict


def _innermost_app_frame(tb) -> str | None:
    frame = None
    for f in traceback.extract_tb(tb):
        if "/app/" in f.filename.replace("\\", "/") or "site-packages" not in f.filename:
            frame = f
    if frame is None:
        return None
    return f"{os.path.basename(frame.filename)}:{frame.name}:{frame.lineno}"


def build_item(record: logging.LogRecord, context: dict | None = None) -> AlertItem:
    try:
        message = record.getMessage()
    except Exception:
        message = str(record.msg)

    exc_type = None
    location = None
    tb_lines: list[str] = []
    if record.exc_info and record.exc_info[0] is not None:
        etype, evalue, etb = record.exc_info
        exc_type = etype.__name__
        location = _innermost_app_frame(etb)
        tb_lines = "".join(traceback.format_exception(etype, evalue, etb)).strip().splitlines()

    if exc_type:
        # Where + what kind, not the message: ids/values vary between occurrences.
        loc_id = (location or "").rsplit(":", 1)[0]  # drop the line number (survives edits)
        basis = f"{record.name}|{exc_type}|{loc_id}"
    else:
        basis = f"{record.name}|{_VOLATILE.sub('#', message)[:200]}"
    return AlertItem(
        level=record.levelname,
        logger_name=record.name,
        message=message,
        exc_type=exc_type,
        traceback_lines=tb_lines,
        location=location,
        fingerprint=hashlib.sha1(basis.encode("utf-8", "replace")).hexdigest()[:16],
        context=context or {},
    )


MAX_MESSAGE_CHARS = 3500  # Telegram's hard limit is 4096


def format_alert(item: AlertItem, *, environment: str, service: str, suppressed: int = 0) -> str:
    first_line = (item.message.splitlines() or [""])[0][:400]
    title = f"{item.exc_type}: {first_line}" if item.exc_type else first_line
    lines = [f"🚨 {item.level} · {environment} · {service}", sanitize(title)]
    if item.location:
        lines.append(f"at {item.location}")
    ctx = item.context
    if ctx.get("request_id"):
        lines.append(f"request {ctx['request_id']}")
    if ctx.get("job_id"):
        lines.append(f"job {ctx['job_id']}")
    if suppressed:
        lines.append(f"(+{suppressed} similar error{'s' if suppressed != 1 else ''} suppressed since last alert)")
    if item.traceback_lines:
        # Drop Python 3.11's caret underline rows: noise in a chat message.
        useful = [ln for ln in item.traceback_lines if set(ln.strip()) - set("^~")]
        tail = sanitize("\n".join(useful[-10:]))
        lines.append("")
        lines.append(tail[-1500:])
    text = "\n".join(lines)
    return text if len(text) <= MAX_MESSAGE_CHARS else text[: MAX_MESSAGE_CHARS - 1] + "…"


def format_flood_notice(*, environment: str, service: str, threshold: int, window_seconds: int) -> str:
    return (
        f"🌊 Error flood · {environment} · {service}\n"
        f"{threshold}+ alerts were suppressed within {window_seconds // 60} min "
        "(repeats and over-budget errors). Further alerts are throttled until it calms down. "
        "Check the logs."
    )


# --- Sending ------------------------------------------------------------------


@dataclass
class SendResult:
    ok: bool
    status: int = 0
    retry_after: int = 0


def post_telegram(base_url: str, token: str, chat_id: str, text: str, timeout: float = 5.0) -> SendResult:
    """Send one message. The URL contains the bot token, so it must never be
    logged: callers only ever see the status code."""
    url = f"{base_url.rstrip('/')}/bot{token}/sendMessage"
    body = json.dumps({"chat_id": chat_id, "text": text, "disable_web_page_preview": True}).encode()
    request = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as resp:  # noqa: S310 (fixed https base)
            return SendResult(ok=200 <= resp.status < 300, status=resp.status)
    except urllib.error.HTTPError as exc:
        retry_after = 0
        if exc.code == 429:
            try:
                retry_after = int(json.loads(exc.read()).get("parameters", {}).get("retry_after", 30))
            except Exception:
                retry_after = 30
        return SendResult(ok=False, status=exc.code, retry_after=retry_after)
    except Exception:
        return SendResult(ok=False, status=0)


@dataclass
class AlertConfig:
    token: str
    chat_id: str
    environment: str = "unknown"
    service: str = "app"
    min_level: int = logging.ERROR
    api_base: str = "https://api.telegram.org"
    min_send_interval: float = 1.2
    queue_size: int = 100


class TelegramAlertHandler(logging.Handler):
    def __init__(
        self,
        config: AlertConfig,
        throttle: AlertThrottle,
        policy: AlertPolicy = AlertPolicy(),
        post: Callable[..., SendResult] = post_telegram,
    ) -> None:
        super().__init__(level=config.min_level)
        self._config = config
        self._throttle = throttle
        self._policy = policy
        self._post = post
        self._queue: queue.Queue[AlertItem] = queue.Queue(maxsize=config.queue_size)
        self._thread: threading.Thread | None = None
        self._pid = os.getpid()
        self._start_lock = threading.Lock()
        self._guard = threading.local()
        self.dropped_queue_full = 0

    # -- logging.Handler API (runs on the caller's thread: must stay cheap) --
    def emit(self, record: logging.LogRecord) -> None:
        try:
            if record.name.startswith(_IGNORED_LOGGERS) or getattr(self._guard, "busy", False):
                return
            from app.core.logging import correlation_context

            item = build_item(record, correlation_context())
            self._ensure_thread()
            try:
                self._queue.put_nowait(item)
            except queue.Full:
                self.dropped_queue_full += 1
        except Exception:
            pass  # alerting must never break the app

    def _ensure_thread(self) -> None:
        # Threads don't survive fork (Celery prefork children): restart per process.
        if self._thread is not None and self._pid == os.getpid() and self._thread.is_alive():
            return
        with self._start_lock:
            if self._thread is not None and self._pid == os.getpid() and self._thread.is_alive():
                return
            if self._pid != os.getpid():
                self._pid = os.getpid()
                self._queue = queue.Queue(maxsize=self._config.queue_size)
                self._start_lock = threading.Lock()
            self._thread = threading.Thread(target=self._run, name="telegram-alerts", daemon=True)
            self._thread.start()

    # -- background thread --
    def _run(self) -> None:
        self._guard.busy = True  # anything logged from here is never re-alerted
        while True:
            item = self._queue.get()
            try:
                self.process(item)
            except Exception:
                logger.warning("alert processing failed", exc_info=False)

    def process(self, item: AlertItem) -> None:
        """Throttle, format and send one record (public so tests can drive it
        synchronously)."""
        decision = self._throttle.decide(item.fingerprint)
        cfg = self._config
        if decision.flood_notice and not self._throttle.is_paused():
            self._send(
                format_flood_notice(
                    environment=cfg.environment,
                    service=cfg.service,
                    threshold=self._policy.flood_threshold,
                    window_seconds=self._policy.flood_window_seconds,
                )
            )
        if decision.action == "send":
            self._send(
                format_alert(
                    item,
                    environment=cfg.environment,
                    service=cfg.service,
                    suppressed=decision.suppressed_similar,
                )
            )

    def _send(self, text: str) -> None:
        cfg = self._config
        result = self._post(cfg.api_base, cfg.token, cfg.chat_id, text)
        if result.status == 429:
            self._throttle.pause(result.retry_after or 30)
            logger.warning("telegram asked us to slow down; pausing alerts for %ss", result.retry_after or 30)
        elif not result.ok:
            logger.warning("telegram alert not delivered (status %s)", result.status or "network error")
        if cfg.min_send_interval > 0:
            time.sleep(cfg.min_send_interval)  # stay well under Telegram's ~1 msg/sec/chat


# --- Wiring -------------------------------------------------------------------


def _env_bool(name: str, default: bool = False) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


def _build_store(redis_url: str) -> Store:
    memory = MemoryStore()
    if redis_url and redis_url.startswith("redis"):
        try:
            import redis

            client = redis.Redis.from_url(redis_url, socket_timeout=0.5, socket_connect_timeout=0.5)
            return ResilientStore(RedisStore(client), memory)
        except Exception:
            logger.warning("alert throttle: could not set up Redis, using per-process memory")
    return memory


def install_alert_handler(root: logging.Logger | None = None) -> TelegramAlertHandler | None:
    """Attach the Telegram handler to the root logger. Idempotent. Does nothing
    (returns None) unless ALERTS_ENABLED is true and both the bot token
    (TELEGRAM_ERROR_ALERT_TOKEN) and TELEGRAM_CHAT_ID are set."""
    root = root or logging.getLogger()
    for existing in root.handlers:
        if isinstance(existing, TelegramAlertHandler):
            return existing

    token = os.getenv("TELEGRAM_ERROR_ALERT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not (_env_bool("ALERTS_ENABLED") and token and chat_id):
        return None

    policy = AlertPolicy(
        dedupe_seconds=int(os.getenv("ALERT_DEDUPE_SECONDS", "600")),
        max_per_minute=int(os.getenv("ALERT_MAX_PER_MINUTE", "5")),
        max_per_hour=int(os.getenv("ALERT_MAX_PER_HOUR", "30")),
        flood_threshold=int(os.getenv("ALERT_FLOOD_THRESHOLD", "20")),
    )
    config = AlertConfig(
        token=token,
        chat_id=chat_id,
        environment=os.getenv("ALERT_ENVIRONMENT", "unknown"),
        service=os.getenv("ALERT_SERVICE", "app"),
        api_base=os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org"),
    )
    handler = TelegramAlertHandler(config, AlertThrottle(_build_store(os.getenv("REDIS_URL", "")), policy), policy)
    root.addHandler(handler)
    logger.info("Telegram error alerts enabled (env=%s service=%s)", config.environment, config.service)
    return handler


def _main(argv: list[str]) -> int:
    """`python -m app.core.alerting status|test` — check config / send ONE message."""
    cmd = argv[0] if argv else "status"
    token = os.getenv("TELEGRAM_ERROR_ALERT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    print(f"ALERTS_ENABLED      : {_env_bool('ALERTS_ENABLED')}")
    print(f"TELEGRAM_ERROR_ALERT_TOKEN: {'set' if token else 'MISSING'}")
    print(f"TELEGRAM_CHAT_ID: {'set' if chat_id else 'MISSING'}")
    print(f"environment/service : {os.getenv('ALERT_ENVIRONMENT', 'unknown')}/{os.getenv('ALERT_SERVICE', 'app')}")
    if cmd != "test":
        return 0
    if not (token and chat_id):
        print("cannot send: token and chat id are both required")
        return 1
    text = f"✅ Test alert · {os.getenv('ALERT_ENVIRONMENT', 'unknown')} · {os.getenv('ALERT_SERVICE', 'app')}\nTelegram error alerts are wired up."
    result = post_telegram(os.getenv("TELEGRAM_API_BASE", "https://api.telegram.org"), token, chat_id, text)
    print(f"test message: {'sent' if result.ok else 'FAILED'} (status {result.status or 'network error'})")
    return 0 if result.ok else 1


if __name__ == "__main__":
    import sys

    raise SystemExit(_main(sys.argv[1:]))
