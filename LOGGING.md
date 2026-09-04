# Logging — Immich Lite

This document describes **everything** about how logging works: the format, the
correlation model, every place that writes a log, the configuration, and how to
read/debug the logs for production.

The headline: logs are **structured JSON** (one object per line) written to a
rotating file, they carry **correlation ids** (`request_id`, `job_id`,
`user_id`) so a single upload can be traced end‑to‑end across the API, the RQ
queue and the worker, and they are shaped so a log aggregator (Loki / ELK /
CloudWatch) can ingest them with **zero reformatting**. A human‑readable console
format is kept for local / container-journal dev.

---

## 1. The three pillars (why this file exists)

Logs are only one of three observability pillars. This project has **two** done:

| Pillar | Status | Where |
|---|---|---|
| **Logs** ("what happened") | ✅ Done | This document |
| **Metrics** ("how much / is it healthy") | ✅ Done | `monitoring/` + Prometheus/Grafana (see PROGRESS.md) |
| **Traces** ("where did one request's time go") | ⏳ Next | not yet added |

A log is a discrete event. It tells you *something happened* (a photo matched, a
request 500'd, a worker died). It does **not** tell you *current state* (is the
queue backing up? is the worker alive?) — that is metrics, and it is not covered
here.

---

## 2. Core files

| File | Role |
|---|---|
| `src/app/core/logging.py` | Central config, the JSON + human formatters, correlation helpers |
| `src/app/core/middleware.py` | HTTP request logging + sets `request_id` / `user_id` correlation |
| `src/app/core/jobs.py` | RQ enqueue logging + sets `job_id`, `photo_id` fields |
| `src/app/workers/photo_worker.py` | Worker lifecycle + per-job correlation (`get_current_job`) |
| `src/app/main.py` | Boots `setup_logging()`, global unhandled-exception handler, request middleware |
| `src/app/core/config.py` | Logging settings (`log_level`, `log_file`, rotation) |

---

## 3. The log line format

### File output (production shape): JSON

One JSON object per line. A request log looks like this:

```json
{"ts":"2026-09-03T23:29:03+0000","level":"WARNING","logger":"app.request",
 "message":"GET /api/nonexistent -> 404 (1.1ms)",
 "request_id":"409f3c05c6e4","method":"GET","path":"/api/nonexistent",
 "status":404,"duration_ms":1.1}
```

Always-present base fields (from `JsonFormatter` in `logging.py`):

| Field | Meaning |
|---|---|
| `ts` | ISO‑8601 timestamp with UTC offset (e.g. `2026-09-03T23:29:03+0000`) |
| `level` | `DEBUG` / `INFO` / `WARNING` / `ERROR` / `CRITICAL` |
| `logger` | Python logger name (e.g. `app`, `app.request`, `app.matching`, `app.ingestion`) |
| `message` | The human log message |

These are merged in on top (when present):

| Field | Meaning | Set by |
|---|---|---|
| `request_id` | 12‑hex id per HTTP request | middleware |
| `job_id` | RQ job id, per background job | worker / enqueue |
| `user_id` | authenticated user id | middleware (from `request.state.user_id`) |
| `exc` | rendered traceback | any `logger.exception()` / 5xx |
| any extra fields | `photo_id`, `event_id`, `method`, `path`, `status`, `duration_ms`, `matches`, … | call sites via `extra={"extra_fields": {...}}` |

Precedence: correlation context and `extra_fields` are merged in but never
overwrite each other on collision (the first value already present wins), so
base fields stay intact.

### Console output (local dev shape): human-readable

The console handler keeps a human formatter (`_console_formatter` in
`logging.py`) so local/container logs are easy on the eyes, but it still shows
correlation and extra fields inline:

```
2026-09-03 23:29:03 [WARNING] app.request request_id=409f3c05c6e4: GET /api/nonexistent -> 404 (1.1ms) method=GET path=/api/nonexistent status=404 duration_ms=1.1
```

### Exception / tracebacks

When an error is logged via `logger.exception(...)` or a 5xx, the record carries
`exc_info`, and the formatter adds an `exc` key containing the full traceback as
a string. This is how the request middleware writes unhandled 500s and how the
worker surfaces ingestion/matching failures.

---

## 4. Correlation model (trace a request/job end-to-end)

The key idea: **every log line that shares a logical unit of work carries the
same correlation id**, so you can `grep` (or filter in a log aggregator) by one
id and see the whole life of that work.

| Correlation id | Set in | Shared by |
|---|---|---|
| `request_id` | middleware, at HTTP request start | all deps + service logs during that HTTP request |
| `user_id` | middleware, after auth | same — the authenticated identity |
| `job_id` | worker via RQ `get_current_job()`; enqueue logs it too | all ingest + match logs for that photo job |
| `photo_id` | enqueue + worker | **cross-process** link: the API and the worker are separate processes, so `photo_id` is the key that ties the enqueue log (API process) to the processing logs (worker process). |

The correlation lives in `contextvars` (`CORRELATION_VARS` in `logging.py`):
- **HTTP request** — `RequestLoggingMiddleware` calls `set_correlation(request_id=...)` before dispatching and `user_id` is added once auth resolves. Because Starlette runs the request in one async context, the contextvars propagate to every log emitted during that request. `clear_correlation()` runs in the `finally` so a reused worker/thread never leaks an id.
- **Background job** — `process_photo` calls `get_current_job()` and sets `job_id` into the same context, so all ingest/match logs for that job carry it; `clear_correlation()` runs when the job ends.

**Why this matters:** if matching silently fails, you can grab the `request_id`
from the API log, find the `job_id`, and follow every worker log for that job —
no more "black box".

---

## 5. What each component logs

### HTTP requests — `core/middleware.py`

`RequestLoggingMiddleware` (added in `main.py`):
- Every HTTP request logged with full structured fields; **skipped for** well-known endpoints (`/ping`, `/openapi.json`, `/docs`, `/redoc`, `/docs/oauth2-redirect`, `/metrics`).
- Severity by status: `5xx` → `ERROR` (also re-raised so the global handler logs the traceback), `4xx` → `WARNING`, else `INFO`.
- `user_id` is attached when the auth dependency has run (`request.state.user_id`).
- Also **feeds Prometheus metrics** (`observe_http`) for latency/status — see the metrics doc, not the log file.

### App lifecycle / global errors — `main.py`

- `setup_logging()` runs once at import; logs `Application starting up`.
- `@app.exception_handler(Exception)` — a catch-all that logs the full traceback of any uncaught error and returns a generic 500 (never leaks internals).
- Note: a 500 can log **twice** (request middleware `exc_info` + the global handler) — a known, accepted redundancy.

### Auth — `api/deps.py` (`app.auth`)

- `get_current_user` logs `WARNING` on auth failures (missing / invalid / expired token, unknown user). The token **value is never logged**.

### Job enqueue — `core/jobs.py` (`app.jobs`)

- Logs `enqueued photo job` with `photo_id` + `job_id` structured fields.
- On failure, logs an `ERROR` with `exc_info` (`failed to enqueue photo job`) and re-raises.

### Worker — `workers/photo_worker.py`

- Logs worker startup / reconnect (Redis connection-loss handling).
- `process_photo` sets `job_id` correlation and logs `processing photo` with `photo_id` + `event_id`.

### Services

- `app.ingestion` — `photo processed event=… photo=… faces=…`; on failure `photo processing failed …` with `exc_info` and marks the photo `failed`.
- `app.matching` — `no attendees to match against …`, `no faces stored for photo=…`, `photo matched … matches=…`.
- `app.user` — register/login success + warnings on duplicate-email / failed login (email only, **no password**).
- `app.auth` — auth failure warnings.

---

## 6. Configuration

Settings live in `src/app/core/config.py` and are read from env / `.env`:

| Setting | Env / `.env` | Default | Meaning |
|---|---|---|---|
| `log_level` | `LOG_LEVEL` | `INFO` | `DEBUG` / `INFO` / `WARNING` / `ERROR` (uppercased when read) |
| `log_file` | `LOG_FILE` | `logs/app.log` | Relative paths resolve against the **project root** (container: `/app/logs/app.log`) |
| `log_max_bytes` | — | `5 * 1024 * 1024` | Rotation threshold per file |
| `log_backup_count` | — | `3` | Number of rotated `.1`, `.2`, `.3` files kept |

Behavior:
- The root logger level is set from `LOG_LEVEL`, so raising it to `WARNING`
  suppresses `INFO` logs globally.
- The rotating file handler writes JSON; the console handler writes human-readable.
- `setup_logging()` is **idempotent** — calling it multiple times won't stack duplicate handlers.
- File setup is wrapped in `try/except` so a logging failure (e.g. unwritable path) **never crashes the app**; it warns and continues with console only.

---

## 7. Reading and debugging the logs

### View live

```bash
# JSON (what log aggregators / you-in-prod should scrape)
docker compose logs app
docker compose logs worker

# Or tail the file inside a container
docker exec immich-lite-app tail -f /app/logs/app.log
```

### Where to look — one place for each service

| What | URL |
|---|---|
| **Grafana dashboard** (all services at a glance) | http://localhost:3001 → "Immich Lite" (login `admin`/`admin`) |
| **Prometheus** (query/metrics + alert rules) | http://localhost:9090 |
| **Alertmanager** (alerts + notifications) | http://localhost:9093 |
| **RQ Dashboard** (photo queue + job status) | http://localhost:9181 |
| **Qdrant** (collections, points, vectors) | http://localhost:8090/dashboard |
| **Postgres** | pgAdmin (your existing setup) |
| **App API** (FastAPI auto-docs) | http://localhost:8080/docs |
| **App metrics** (raw Prometheus format) | http://localhost:8080/metrics |
| **Redis / Postgres exporter endpoints** | http://localhost:9121/metrics / http://localhost:9187/metrics |

> The **worker** metrics (`:9100`) are internal only — Prometheus reaches them
> at `worker:9100` on the docker network, not exposed to the host.

### GitHub `grep`-style filtering (works because each line is one JSON object)

```bash
# All errors, quickly
docker logs immich-lite-app 2>&1 | Select-String '"level":"ERROR"'

# Follow one request end-to-end by its request_id
docker logs immich-lite-app 2>&1 | Select-String "409f3c05c6e4"

# Follow one photo's full lifecycle (API enqueue -> worker ingest -> match)
docker exec immich-lite-app tail -f /app/logs/app.log | Select-String "photo_id=acc1c43e"

# Worker-alive / reconnect noise
docker logs immich-lite-worker 2>&1 | Select-String "reconnect|Redis"
```

### For production (large volume)

Do **not** rely on `docker logs`. The JSON format is designed to be shipped
straight into a log aggregator with a sidecar/agent (Promtail→Loki, Filebeat→
Elasticsearch, CloudWatch agent, Datadog). Because each line is a complete JSON
object, the aggregator can index `level`, `logger`, `request_id`, `user_id`,
`photo_id`, etc. without any custom parsing — and you can then query "all ERRORs
for user X across the last hour" instantly.

---

## 8. Hard rules

- **Never log passwords, JWT tokens, or password hashes.** Period. Auth logs
  record email/user id and the *reason*, never credentials.
- **Never expose the raw user id** to the API response layer, but logging it in
  the correlation context is fine internally.
- Add structured fields via `extra={"extra_fields": {...}}` rather than
  hand-building strings, so the fields stay JSON-typed in the file output.
- Keep the console human-readable; keep the file JSON. Don't make them identical.
- If a question is really about **state/volume** (is the queue healthy? is the
  worker up?) that's a **metrics** question — see the Prometheus/Grafana stack
  and its alerts rather than grepping logs.

---

## 9. How to extend

Adding a new logged event is a two-liner:

```python
import logging
logger = logging.getLogger("app.<your_area>")            # or reuse an existing area logger

logger.info("thing happened", extra={"extra_fields": {"photo_id": p.id, "matches": n}})
# logger.warning(...) / logger.error(...) / logger.exception(...) for errors
```

- Use `logger.exception(...)` in `except` blocks to attach the traceback.
- Pass non-secret identifiers as `extra_fields` so they land in the JSON.
- If a new background process needs correlation, mirror the worker pattern
  (`get_current_job()`) or set a `ContextVar` id explicitly.