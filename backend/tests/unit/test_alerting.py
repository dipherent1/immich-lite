"""Telegram error alerts: fingerprinting, flood protection, scrubbing, wiring.

Everything runs against a fake clock and a fake sender: no network, no sleeping.
"""

import io
import logging
import threading
import time
import urllib.error

import pytest

from app.core import alerting
from app.core.alerting import (
    AlertConfig,
    AlertPolicy,
    AlertThrottle,
    MemoryStore,
    RedisStore,
    ResilientStore,
    SendResult,
    TelegramAlertHandler,
    build_item,
    format_alert,
    install_alert_handler,
    post_telegram,
    sanitize,
)


class Clock:
    def __init__(self, t: float = 1_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def advance(self, seconds: float) -> None:
        self.t += seconds


class FakeSender:
    """Records messages instead of calling Telegram."""

    def __init__(self, result: SendResult | None = None):
        self.messages: list[str] = []
        self.result = result or SendResult(ok=True, status=200)

    def __call__(self, base, token, chat_id, text, timeout=5.0) -> SendResult:
        self.messages.append(text)
        return self.result

    @property
    def alerts(self):
        return [m for m in self.messages if m.startswith("🚨")]

    @property
    def floods(self):
        return [m for m in self.messages if m.startswith("🌊")]


def make(policy: AlertPolicy | None = None, clock: Clock | None = None, sender: FakeSender | None = None):
    clock = clock or Clock()
    sender = sender or FakeSender()
    policy = policy or AlertPolicy()
    throttle = AlertThrottle(MemoryStore(clock), policy, clock)
    handler = TelegramAlertHandler(
        AlertConfig(token="123456:" + "A" * 35, chat_id="42", environment="test", service="api", min_send_interval=0),
        throttle,
        policy,
        post=sender,
    )
    return handler, throttle, sender, clock


def record(msg="boom", name="app.thing", exc: BaseException | None = None, level=logging.ERROR):
    exc_info = None
    if exc is not None:
        try:
            raise exc
        except BaseException as e:  # noqa: BLE001 (build a real traceback)
            exc_info = (type(e), e, e.__traceback__)
    return logging.LogRecord(name, level, __file__, 10, msg, None, exc_info)


def feed(handler: TelegramAlertHandler, rec: logging.LogRecord) -> None:
    handler.process(build_item(rec))


# --- fingerprinting -----------------------------------------------------------


def test_same_failure_with_different_ids_is_one_problem():
    a = build_item(record("could not process photo 41 for user 7"))
    b = build_item(record("could not process photo 9001 for user 12"))
    assert a.fingerprint == b.fingerprint


def test_uuids_and_hex_ids_are_ignored_in_the_fingerprint():
    a = build_item(record("failed event=3f2c1a9e-1b2c-4d5e-8f90-aabbccddeeff"))
    b = build_item(record("failed event=00000000-0000-4000-8000-000000000000"))
    assert a.fingerprint == b.fingerprint


def test_different_logger_or_text_is_a_different_problem():
    base = build_item(record("db is down", name="app.a")).fingerprint
    assert build_item(record("db is down", name="app.b")).fingerprint != base
    assert build_item(record("cache is down", name="app.a")).fingerprint != base


def test_exception_fingerprint_uses_location_and_type_not_message():
    def explode(msg):
        raise ValueError(msg)

    def capture(msg):
        try:
            explode(msg)
        except ValueError as e:
            return (type(e), e, e.__traceback__)

    r1 = logging.LogRecord("app.x", logging.ERROR, "f", 1, "unhandled", None, capture("user 1 bad"))
    r2 = logging.LogRecord("app.x", logging.ERROR, "f", 1, "unhandled", None, capture("user 2 bad"))
    assert build_item(r1).fingerprint == build_item(r2).fingerprint
    assert build_item(r1).exc_type == "ValueError"
    assert build_item(r1).location and "explode" in build_item(r1).location

    r3 = logging.LogRecord("app.x", logging.ERROR, "f", 1, "unhandled", None, (KeyError, KeyError("k"), None))
    assert build_item(r3).fingerprint != build_item(r1).fingerprint


# --- de-duplication -----------------------------------------------------------


def test_first_error_is_sent_and_repeats_are_suppressed():
    handler, _, sender, _ = make()
    for _ in range(50):
        feed(handler, record("same problem"))
    assert len(sender.alerts) == 1


def test_repeat_after_cooldown_reports_how_many_were_suppressed():
    handler, _, sender, clock = make(AlertPolicy(dedupe_seconds=600, flood_threshold=10_000))
    for _ in range(8):
        feed(handler, record("same problem"))
    clock.advance(601)
    feed(handler, record("same problem"))
    assert len(sender.alerts) == 2
    assert "(+7 similar errors suppressed" in sender.alerts[1]
    assert "suppressed" not in sender.alerts[0]


def test_distinct_problems_each_alert_once():
    handler, _, sender, _ = make()
    for i in range(3):
        feed(handler, record(f"problem number {chr(97 + i)}"))
        feed(handler, record(f"problem number {chr(97 + i)}"))
    assert len(sender.alerts) == 3


# --- global budget ------------------------------------------------------------


def test_per_minute_budget_caps_a_storm_of_different_errors():
    handler, _, sender, _ = make(AlertPolicy(max_per_minute=5, max_per_hour=1000, flood_threshold=20))
    for i in range(60):
        feed(handler, record(f"unique failure kind {chr(65 + i % 26)}{chr(97 + i // 26)}"))
    assert len(sender.alerts) == 5
    assert len(sender.floods) == 1  # one summary, not 55 messages


def test_budget_frees_up_next_minute_and_dropped_error_can_alert_then():
    handler, _, sender, clock = make(AlertPolicy(max_per_minute=2, max_per_hour=1000, flood_threshold=1000))
    for name in ("alpha", "bravo", "charlie"):
        feed(handler, record(f"{name} failed"))
    assert len(sender.alerts) == 2  # charlie was over budget
    clock.advance(61)
    feed(handler, record("charlie failed"))  # same problem, new minute -> delivered
    assert len(sender.alerts) == 3
    assert "charlie" in sender.alerts[2]


def test_per_hour_budget_applies_across_minutes():
    handler, _, sender, clock = make(AlertPolicy(max_per_minute=100, max_per_hour=3, flood_threshold=1000))
    for i in range(10):
        feed(handler, record(f"hourly failure {chr(97 + i)}"))
        clock.advance(61)  # every error lands in a new minute
    assert len(sender.alerts) == 3


# --- flood notice -------------------------------------------------------------


def test_identical_error_flood_sends_one_alert_and_one_flood_notice():
    handler, _, sender, _ = make(AlertPolicy(flood_threshold=20))
    for _ in range(1000):
        feed(handler, record("db connection refused"))
    assert len(sender.alerts) == 1
    assert len(sender.floods) == 1
    assert len(sender.messages) == 2


def test_flood_notice_repeats_only_after_the_storm_calms_down():
    handler, _, sender, clock = make(AlertPolicy(flood_threshold=5, flood_window_seconds=300, dedupe_seconds=10_000))
    for _ in range(100):
        feed(handler, record("storm"))
    assert len(sender.floods) == 1
    clock.advance(301)  # quiet for longer than the window: the storm is over
    for _ in range(100):
        feed(handler, record("storm"))
    assert len(sender.floods) == 2


def test_message_volume_is_bounded_whatever_the_input():
    handler, _, sender, _ = make()  # defaults: 5/min, 20 to flood
    for i in range(5000):
        feed(handler, record(f"error variant {i % 97 * 'x'}{i % 13}"))
    assert len(sender.messages) <= 5 + 1


# --- Telegram back-pressure ---------------------------------------------------


def test_telegram_429_pauses_all_sending_for_retry_after():
    clock = Clock()
    sender = FakeSender(SendResult(ok=False, status=429, retry_after=30))
    handler, throttle, _, _ = make(clock=clock, sender=sender)
    feed(handler, record("first problem"))
    assert len(sender.messages) == 1
    assert throttle.is_paused()

    for i in range(20):
        feed(handler, record(f"another problem {chr(97 + i)}"))
    assert len(sender.messages) == 1  # nothing sent while paused

    clock.advance(31)
    sender.result = SendResult(ok=True, status=200)
    assert not throttle.is_paused()
    feed(handler, record("a fresh problem"))
    assert len(sender.messages) == 2


def test_pause_is_capped_at_an_hour():
    clock = Clock()
    _, throttle, _, _ = make(clock=clock)
    throttle.pause(10**9)
    clock.advance(3601)
    assert not throttle.is_paused()


def test_failed_delivery_does_not_crash_or_retry_in_a_loop():
    sender = FakeSender(SendResult(ok=False, status=0))
    handler, _, _, _ = make(sender=sender)
    for _ in range(10):
        feed(handler, record("network is down"))
    assert len(sender.messages) == 1  # one attempt, the rest are duplicates


# --- stores -------------------------------------------------------------------


class FakeRedis:
    """Just enough of redis-py for RedisStore, with expiry."""

    def __init__(self, clock: Clock):
        self.clock = clock
        self.data: dict[str, tuple[int, float | None]] = {}

    def _live(self, k):
        v = self.data.get(k)
        if v and v[1] is not None and v[1] <= self.clock():
            del self.data[k]
            return None
        return v

    def set(self, k, v, nx=False, ex=None):
        if nx and self._live(k):
            return None
        self.data[k] = (int(v), self.clock() + ex if ex else None)
        return True

    def incr(self, k):
        v = self._live(k)
        self.data[k] = ((v[0] if v else 0) + 1, v[1] if v else None)
        return self.data[k][0]

    def expire(self, k, ttl):
        v = self._live(k)
        if v:
            self.data[k] = (v[0], self.clock() + ttl)

    def decr(self, k):
        v = self._live(k)
        if v:
            self.data[k] = (v[0] - 1, v[1])

    def getdel(self, k):
        v = self._live(k)
        self.data.pop(k, None)
        return v[0] if v else None

    def delete(self, k):
        self.data.pop(k, None)

    def exists(self, k):
        return 1 if self._live(k) else 0

    def pipeline(self):
        outer = self

        class Pipe:
            def __init__(self):
                self.ops = []

            def incr(self, k):
                self.ops.append(lambda: outer.incr(k))

            def expire(self, k, ttl):
                self.ops.append(lambda: outer.expire(k, ttl))

            def execute(self):
                return [op() for op in self.ops]

        return Pipe()


def test_two_processes_sharing_redis_share_one_budget_and_dedupe():
    clock = Clock()
    redis = FakeRedis(clock)
    policy = AlertPolicy(max_per_minute=3, max_per_hour=100, flood_threshold=1000)
    sender = FakeSender()

    def process():
        t = AlertThrottle(RedisStore(redis), policy, clock)
        return TelegramAlertHandler(
            AlertConfig(token="1:x", chat_id="1", min_send_interval=0), t, policy, post=sender
        )

    api, worker = process(), process()
    feed(api, record("same problem"))
    feed(worker, record("same problem"))  # another process, same problem: duplicate
    assert len(sender.alerts) == 1
    for i in range(10):
        feed(api if i % 2 else worker, record(f"separate problem {chr(97 + i)}"))
    assert len(sender.alerts) == 3  # one shared budget of 3 per minute


def test_store_falls_back_to_memory_when_redis_errors_and_recovers():
    clock = Clock()

    class Broken:
        calls = 0

        def __getattr__(self, name):
            def boom(*a, **k):
                Broken.calls += 1
                raise ConnectionError("redis down")

            return boom

    store = ResilientStore(Broken(), MemoryStore(clock), retry_after=30, clock=clock)
    assert store.set_nx("k", 60) is True  # fell back to memory
    assert store.set_nx("k", 60) is False  # and the memory store is consistent
    calls = Broken.calls
    store.set_nx("other", 60)
    assert Broken.calls == calls  # not hammering a dead Redis
    clock.advance(31)
    store.set_nx("again", 60)
    assert Broken.calls == calls + 1  # retried after the back-off


# --- the handler itself -------------------------------------------------------


def wait_for(cond, timeout=3.0):
    end = time.time() + timeout
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.01)
    return False


def test_handler_works_end_to_end_through_logging_and_the_background_thread():
    handler, _, sender, _ = make()
    log = logging.getLogger("app.e2e_test")
    log.propagate = False
    log.addHandler(handler)
    try:
        for _ in range(300):
            log.error("kaput")
        assert wait_for(lambda: len(sender.messages) >= 1)
        time.sleep(0.2)
        assert len(sender.alerts) == 1
    finally:
        log.removeHandler(handler)


def test_warnings_and_info_are_not_alerted():
    handler, _, sender, _ = make()
    log = logging.getLogger("app.level_test")
    log.propagate = False
    log.addHandler(handler)
    try:
        log.warning("just a warning")
        log.info("info")
        time.sleep(0.2)
        assert sender.messages == []
    finally:
        log.removeHandler(handler)


@pytest.mark.parametrize("name", ["app.alerting", "httpx", "httpcore.http11", "urllib3.connectionpool", "app.request"])
def test_ignored_loggers_are_never_alerted(name):
    handler, _, sender, _ = make()
    handler.emit(record("something failed", name=name))
    time.sleep(0.15)
    assert sender.messages == []
    assert handler._queue.qsize() == 0


def test_errors_logged_while_sending_do_not_cause_a_feedback_loop():
    sender = FakeSender()
    handler, _, _, _ = make(sender=sender)
    log = logging.getLogger("app.loop_test")
    log.propagate = False
    log.addHandler(handler)
    inner = sender.__call__

    def noisy_post(*a, **k):
        log.error("error raised while sending")  # would re-enter the handler
        return inner(*a, **k)

    handler._post = noisy_post
    try:
        log.error("original problem")
        assert wait_for(lambda: len(sender.messages) >= 1)
        time.sleep(0.3)
        assert len(sender.alerts) == 1
    finally:
        log.removeHandler(handler)


def test_full_queue_drops_records_without_blocking_or_raising():
    release = threading.Event()

    def slow_post(*a, **k):
        release.wait(5)
        return SendResult(ok=True, status=200)

    policy = AlertPolicy()
    handler = TelegramAlertHandler(
        AlertConfig(token="1:x", chat_id="1", min_send_interval=0, queue_size=2),
        AlertThrottle(MemoryStore(), policy),
        policy,
        post=slow_post,
    )
    start = time.time()
    for i in range(200):
        handler.emit(record(f"distinct failure {i}"))
    assert time.time() - start < 1.0  # callers never wait on Telegram
    assert handler.dropped_queue_full > 0
    release.set()


def test_a_failing_sender_does_not_kill_the_alert_thread():
    calls = []

    def flaky(*a, **k):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("sender exploded")
        return SendResult(ok=True, status=200)

    policy = AlertPolicy()
    handler = TelegramAlertHandler(
        AlertConfig(token="1:x", chat_id="1", min_send_interval=0),
        AlertThrottle(MemoryStore(), policy),
        policy,
        post=flaky,
    )
    handler.emit(record("first distinct problem"))
    handler.emit(record("second distinct problem"))
    assert wait_for(lambda: len(calls) >= 2)


def test_emit_never_raises_even_for_broken_records():
    handler, _, _, _ = make()

    class Bad:
        def __str__(self):
            raise RuntimeError("no str for you")

    rec = logging.LogRecord("app.x", logging.ERROR, "f", 1, Bad(), None, None)
    handler.emit(rec)  # must not raise


def test_thread_is_restarted_in_a_forked_child_process():
    handler, _, sender, _ = make()
    handler.emit(record("before fork"))
    assert wait_for(lambda: len(sender.messages) >= 1)
    handler._pid = -1  # pretend we are a freshly forked Celery child
    handler.emit(record("after fork, different problem"))
    assert wait_for(lambda: len(sender.alerts) >= 2)


# --- message content ----------------------------------------------------------


def test_message_is_scrubbed_of_secrets():
    secrets = (
        "token=eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.abcDEFghi_-123 "
        "Authorization: Bearer abc.def.ghi "
        "GET /join/O4ZulOwmQ4BmT4XtY5fhkg and /api/v1/public/events/O4ZulOwmQ4BmT4XtY5fhkg/photos "
        "user alice.smith@example.com "
        "db postgresql://immich:SuperSecret1@postgres:5432/immich "
        "bot 123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw "
        "password=hunter2"
    )
    out = sanitize(secrets)
    for leaked in ("eyJhbGci", "abc.def.ghi", "O4ZulOw", "alice.smith", "SuperSecret1", "AAHdqTcv", "hunter2"):
        assert leaked not in out, leaked
    assert "/join/<token>" in out and "<email>" in out


def test_alert_text_is_scrubbed_and_never_contains_the_bot_token():
    sender = FakeSender()
    handler, _, _, _ = make(sender=sender)
    feed(handler, record("login failed for bob@example.com with password=letmein on /join/AbCdEfGhIjKlMnOp"))
    text = sender.alerts[0]
    assert "bob@example.com" not in text and "letmein" not in text and "AbCdEfGh" not in text
    assert "123456:" not in text  # the bot token itself


def test_alert_is_short_enough_for_telegram_even_with_a_huge_traceback():
    def deep(n):
        if n == 0:
            raise ValueError("x" * 10_000)
        deep(n - 1)

    try:
        deep(400)
    except ValueError as e:
        rec = logging.LogRecord("app.x", logging.ERROR, "f", 1, "y" * 10_000, None, (type(e), e, e.__traceback__))
    text = format_alert(build_item(rec), environment="production", service="api")
    assert len(text) <= alerting.MAX_MESSAGE_CHARS < 4096
    assert text.startswith("🚨 ERROR · production · api")


def test_traceback_caret_underlines_are_stripped_but_the_error_line_is_kept():
    item = build_item(record("failed", exc=ValueError("the real reason")))
    item.traceback_lines.insert(2, "                    ^^^^^^^^^^^^^^^^^^^^")
    text = format_alert(item, environment="e", service="s")
    assert "^^^^" not in text
    assert "ValueError: the real reason" in text


def test_alert_includes_request_and_job_ids_when_available():
    item = build_item(record("boom"), {"request_id": "abc123", "job_id": "job9"})
    text = format_alert(item, environment="e", service="s")
    assert "request abc123" in text and "job job9" in text


# --- Telegram HTTP client -----------------------------------------------------


def test_post_telegram_429_exposes_retry_after(monkeypatch):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(
            req.full_url, 429, "Too Many Requests", {}, io.BytesIO(b'{"ok":false,"parameters":{"retry_after":17}}')
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    result = post_telegram("https://api.telegram.org", "1:tok", "42", "hi")
    assert (result.ok, result.status, result.retry_after) == (False, 429, 17)


def test_post_telegram_network_error_is_a_failed_result_not_an_exception(monkeypatch):
    def boom(req, timeout=None):
        raise OSError("no route to host")

    monkeypatch.setattr(urllib.request, "urlopen", boom)
    assert post_telegram("https://api.telegram.org", "1:tok", "42", "hi").ok is False


def test_post_telegram_sends_to_the_bot_endpoint_with_the_chat_id(monkeypatch):
    seen = {}

    class Resp:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=None):
        seen["url"], seen["body"] = req.full_url, req.data
        return Resp()

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert post_telegram("https://api.telegram.org/", "111:abc", "-100500", "hello").ok
    assert seen["url"] == "https://api.telegram.org/bot111:abc/sendMessage"
    assert b'"chat_id": "-100500"' in seen["body"] and b'"hello"' in seen["body"]


# --- installation -------------------------------------------------------------


@pytest.fixture
def clean_alert_env(monkeypatch):
    for name in ("ALERTS_ENABLED", "TELEGRAM_ERROR_ALERT_TOKEN", "TELEGRAM_CHAT_ID", "REDIS_URL"):
        monkeypatch.delenv(name, raising=False)


def test_alerts_are_off_by_default(clean_alert_env):
    assert install_alert_handler(logging.getLogger("install_test_a")) is None


@pytest.mark.parametrize("missing", ["ALERTS_ENABLED", "TELEGRAM_ERROR_ALERT_TOKEN", "TELEGRAM_CHAT_ID"])
def test_all_three_settings_are_required(clean_alert_env, monkeypatch, missing):
    env = {"ALERTS_ENABLED": "true", "TELEGRAM_ERROR_ALERT_TOKEN": "1:abc", "TELEGRAM_CHAT_ID": "42"}
    env.pop(missing)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert install_alert_handler(logging.getLogger("install_test_b_" + missing)) is None


def test_install_attaches_once_and_is_idempotent(clean_alert_env, monkeypatch):
    monkeypatch.setenv("ALERTS_ENABLED", "true")
    monkeypatch.setenv("TELEGRAM_ERROR_ALERT_TOKEN", "1:abc")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "42")
    monkeypatch.setenv("ALERT_ENVIRONMENT", "production")
    root = logging.getLogger("install_test_c")
    first = install_alert_handler(root)
    assert isinstance(first, TelegramAlertHandler)
    assert install_alert_handler(root) is first
    assert sum(isinstance(h, TelegramAlertHandler) for h in root.handlers) == 1
    assert first._config.environment == "production"


def test_status_command_never_prints_secrets(clean_alert_env, monkeypatch, capsys):
    monkeypatch.setenv("TELEGRAM_ERROR_ALERT_TOKEN", "999999:SECRETSECRETSECRETSECRETSECRET12345")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "-1001234567")
    assert alerting._main(["status"]) == 0
    out = capsys.readouterr().out
    assert "SECRETSECRET" not in out and "-1001234567" not in out
    assert "TELEGRAM_ERROR_ALERT_TOKEN: set" in out
