# Immich Lite

A self-hosted face-matching service for photo events. Users enroll a face profile,
create or join events via share links / owner-approved join requests, upload photos,
and get matched photos (who's in the shot) delivered to them through an in-app feed
and live SSE notifications.

Built on the same **InsightFace** backend (RetinaFace detection + ArcFace embeddings)
the full [Immich](https://github.com/immich-app/immich) project uses, so vectors stay
compatible with the broader Immich ecosystem.

## Architecture

```
immich-lite/
├── backend/            # FastAPI app (backend/src/app) + Alembic migrations + RQ worker + tests
├── frontend/           # Next.js 16 (App Router, TypeScript) — single API client in src/lib/api.ts
├── monitoring/         # Prometheus, Grafana, Alertmanager configs + dashboard
├── legacy/             # Archived pre-rewrite code (see legacy/README.md — do not use)
├── docs/               # Phase plan, progress/changelog, testing & logging guides
└── docker-compose.yml  # Full stack: qdrant, postgres, redis, app, worker, monitoring
```

### Data flow

```
Photo upload (API) → Photo row (Postgres, status=pending) → RQ job (Redis)
  → photo_worker: detect faces → face embeddings → event_faces (Qdrant)
  → match vs attendee user_profiles (Qdrant, attendee-scoped filter)
  → PhotoMatch rows (Postgres) → notification per matched user → SSE live push
```

Two stores, two roles:

- **Postgres** — users, events, attendees, photos, matches, join requests, notifications.
- **Qdrant** — vectors only: `user_profiles` (one point per user) and `event_faces`
  (one point per detected face, payload-carried `event_id`/`photo_id`/`bbox`).

### Status

Phases 0–6 are complete (accounts/auth, face-profile enrollment, events, ingestion
pipeline with an RQ worker, attendee-scoped matching + feed, notifications/join
requests). Observability (structured JSON logs with correlation ids, Prometheus
metrics, Grafana dashboards, alert rules) is also in place. See `docs/PROGRESS.md`
for the full changelog and `docs/PHASES.md` for the roadmap.

## Quick start (Docker)

```bash
docker compose up -d
```

This starts Qdrant (`:8090`), Postgres (`:5433`), Redis, the API (`:8080`), the RQ
worker, and the monitoring stack (Prometheus `:9090`, Grafana `:3001`, Alertmanager
`:9093`, RQ dashboard `:9181`).

Rebuild after code changes:

```bash
docker compose up -d --build app worker
```

> **Host ports:** on Windows, reserved TCP ranges block `6333`/`8000`, so the compose
> file maps services to `8090`/`8100`/`8080`. Container ports are unchanged.

## Local development

Backend (Python 3.11):

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r backend/requirements.txt -r backend/requirements-dev.txt

# backing services only (no build)
docker compose up -d qdrant postgres redis

# run the API from backend/
cd backend
$env:PYTHONPATH="src"; uvicorn app.main:app --host 0.0.0.0 --port 8080
```

Frontend (Node 24 / npm):

```bash
cd frontend
npm install
npm run dev        # http://localhost:3000, talks to :8080 via NEXT_PUBLIC_API_URL
```

CORS is enabled for `http://localhost:3000` by default (`CORS_ORIGINS` setting).

### Environment

Copy `.env.example` to `.env` and set at least `JWT_SECRET`. Settings are read from
`.env` (loaded from the repo root regardless of CWD) via
`backend/src/app/core/config.py`.

## Database migrations

Alembic owns every schema change — never rely on ORM auto-create. Migrations live in
`backend/migrations/`; run them from `backend/`:

```bash
cd backend
alembic upgrade head          # apply
alembic downgrade -1          # roll back one step
alembic revision --autogenerate -m "describe change"
```

Tip: on the current Postgres setup the DB isn't exposed on a host port, so apply
migrations inside the app container: `docker compose exec app alembic upgrade head`.

## API surface (all under `/api/v1`)

| Area | Endpoints |
|---|---|
| Auth | `POST /auth/register`, `POST /auth/login` |
| Users | `GET /users/me`, `POST /users/me/scan` (face profile, 1–3 images) |
| Events | `POST /events`, `GET /events`, `GET /events/search`, `GET /events/join/{token}`, `GET /events/{id}`, `POST /events/{id}/photos`, `GET /events/{id}/photos`, `GET /events/{id}/photos/{pid}/file` |
| Join requests | `POST /events/{id}/join-request`, `GET /events/{id}/join-requests`, `PATCH .../approve`, `PATCH .../deny` |
| Matches | `GET /matches/me` (matched-photo feed) |
| Notifications | `GET /notifications`, `GET /notifications/unread-count`, `GET /notifications/stream` (SSE), `PATCH /notifications/{id}/read`, `PATCH /notifications/read-all` |
| Misc | `GET /ping`, `GET /metrics` (Prometheus) |

Interactive docs: `http://localhost:8080/docs`.

## Testing

191 tests (unit + repository + integration), ~89% line coverage:

```bash
cd backend
python -m pytest
python -m pytest --cov=app --cov-report=term-missing
```

See `docs/TESTING.md` for the full breakdown.

## Observability

- **Logs** — structured JSON (one object per line) with correlation ids so a single
  upload can be traced API → queue → worker. See `docs/LOGGING.md`.
- **Metrics** — Prometheus endpoint on the API (`:8080/metrics`) and the worker
  (`:9100`, internal), with alert rules that catch a dead worker / stalled queue.
- **Dashboards** — Grafana on `:3001` (login `admin`/`admin`), "Immich Lite" dashboard
  auto-provisioned from `monitoring/grafana/`.

## Notes

- Memory model: photos are stored once under `output/photos/{event}/{photo}.jpg`
  (bind-mounted `./output:/app/output`) and referenced everywhere by relative path —
  nothing is copied for matching or delivery.
- The frontend's auth is a JWT in `localStorage` via `frontend/src/lib/api.ts`; that
  single module is the seam for moving to HttpOnly-cookie auth behind a Next.js proxy.
- Qdrant has no foreign keys — points are soft-linked to Postgres via payload ids and
  are orphaned if a `Photo`/`Event` row is deleted without explicit cleanup (tracked
  as a hardening task in `docs/PHASES.md`).