## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:

- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Part A — Standing Architecture Rules (apply to every change)

### Repository layout

Monorepo with three top-level app folders plus support directories. The backend is
self-contained under `backend/`; the frontend and monitoring stacks mirror it.

```text
immich-lite/
├── docker-compose.yml            # full stack: qdrant, postgres, redis, rq-dashboard,
│                                 #   exporters, prometheus, alertmanager, grafana, app, worker
├── .env                          # gitignored — compose interpolation + local dev (loaded from repo root)
├── .env.example                  # template of required/optional env vars
├── docs/                        # PHASES.md (roadmap) · PROGRESS.md (changelog) · TESTING.md · LOGGING.md
├── legacy/                       # archived pre-rewrite code — do not run or modify (see legacy/README.md)
├── backend/
│   ├── Dockerfile                # build context = backend/ (small, no frontend/monitoring)
│   ├── alembic.ini               # env.py inserts `src` on sys.path; DB URL from app settings
│   ├── pyproject.toml            # pytest config: testpaths=tests, pythonpath=src
│   ├── requirements.txt / requirements-dev.txt
│   ├── migrations/               # Alembic versions — one file per schema change (5 so far)
│   ├── src/app/                  # canonical Python package `app`
│   │   ├── api/
│   │   │   ├── deps.py           # DI wiring: get_db, get_*_repository/service, get_current_user
│   │   │   └── v1/
│   │   │       ├── api.py        # aggregates all routers under prefix /api/v1
│   │   │       └── endpoints/    # auth, users, events, join_requests, matches, notifications
│   │   ├── core/                 # config, database, security, logging, middleware, metrics,
│   │   │                         #   vector_db (Qdrant repos), file_storage, jobs, sse, sse_relay,
│   │   │                         #   notification_publisher, worker_metrics
│   │   ├── domain/               # entities.py + interfaces.py (Phase 0 value types / ABCs)
│   │   ├── models/               # SQLModel ORM: user, event, event_attendee, photo, photo_match,
│   │   │                         #   join_request, notification
│   │   ├── repositories/         # one class per aggregate — the ONLY layer with raw SQL
│   │   ├── schemas/              # Pydantic v2 request/response DTOs (one file per aggregate)
│   │   ├── services/             # business logic, raise HTTPException on errors
│   │   └── workers/              # photo_worker.py — RQ worker entry point
│   └── tests/                    # unit/ · repositories/ · integration/ (191 tests)
├── frontend/                     # Next.js 16, App Router, TypeScript, @/* alias, src/
│   └── src/
│       ├── app/                  # routes
│       ├── components/           # RequireAuth, EventsView, PhotoGrid, MatchesGrid, ...
│       └── lib/api.ts            # the SINGLE API client (base URL + Bearer token)
└── monitoring/                   # prometheus.yml, alerts.yml, alertmanager.yml, grafana/ provisioning
```

### Layering (routers → services → repositories → models)

- **Routers** (`api/v1/endpoints/*`) are thin: parse the request, call a service via `Depends(...)`, return a `response_model`. No DB, no raw SQL, no vector logic in `api/`.
- **Services** (`services/*`) own the business rules and raise `HTTPException` on errors (never leak DB exceptions or internals).
- **Repositories** (`repositories/*`) own ALL database access — a class per aggregate that takes the injected session (e.g. `UserRepository(db)`). This is the only layer with raw SQLAlchemy/SQLModel queries.
- **`api/deps.py`** wires DI: `get_db`, `get_user_repository`, `get_user_service`, `get_current_user`. No global state, no manual singletons (the embedding service is shared via `@lru_cache`).

### Frontend

- Located in `frontend/` (Next.js 16, App Router, TypeScript, `@/*` alias, `src/`).
- **`frontend/src/lib/api.ts` is the single API client** — it owns the FastAPI base URL (`NEXT_PUBLIC_API_URL`) and attaches `Authorization: Bearer <token>` from `localStorage`. Components never touch `localStorage`, never build auth headers, never hardcode the URL.
- To later move auth to HttpOnly cookies + a Next.js proxy, change only `lib/api.ts` (base URL becomes relative, token read from a cookie) — application components stay untouched.
- Protected pages use the `RequireAuth` client guard (`frontend/src/components/RequireAuth.tsx`).
- SSE notifications are consumed via `frontend/src/lib/notifications.ts` (`useNotifications()` hook, token passed as a query param because `EventSource` can't set headers).

### Logging

- All logging goes through Python's stdlib `logging`, configured once by `backend/src/app/core/logging.setup_logging()` (console + rotating file `backend/logs/`; `/app/logs/` in containers). File output is one JSON object per line; the console stays human-readable.
- Logs carry a **correlation context** (`request_id`, `job_id`, `user_id`) so one upload can be traced API → queue → worker. Add structured fields via `extra={"extra_fields": {...}}`.
- A request-logging middleware logs every HTTP call (method/path/status/duration + `user=<id>` when authenticated); 5xx at ERROR, 4xx at WARNING.
- A global unhandled-exception handler logs the full traceback and returns a generic 500.
- **Never log passwords, JWT tokens, or password hashes.** See `docs/LOGGING.md`.

### Coding rules (unchanged, keep enforcing)

- **Thin routers** — endpoints only parse requests, call a service, return a `response_model`. No DB or vector logic in `api/`.
- **Explicit status codes** on every route decorator.
- **response_model everywhere** — never leak ORM objects or password hashes.
- **Services layer owns logic** — embedding, matching, ingestion, and event-membership rules live in `services/`, not in routes or workers.
- **Repositories own DB access** — no raw SQL outside `repositories/`.
- **Dependency injection** via `Depends()` for DB sessions, current user, Qdrant client. No global state, no manual singletons.
- **Never expose the user id.** The authenticated user's id is always derived server-side from the JWT (`decode_access_token` → `sub` → `get_current_user`); no route trusts a client-supplied id, and no `*Response` schema includes the raw id. Use the DB user object's `.id` only internally (token `sub`, vector/profile lookups, logging).
- **Pydantic v2**, separate `*Create` / `*Response` schemas.
- **Async endpoints** for I/O-bound routes (DB, Qdrant, file upload). Use plain `def` (or a thread/worker offload) for the CPU-bound face-detection/embedding step so it doesn't block the event loop. Face enrollment/scan and photo ingestion both offload to non-event-loop contexts; the RQ worker does the heavy work for uploads.
- **HTTPException only** for errors — no ad-hoc dict responses.
- **Alembic owns every schema change** — never rely on `Base.metadata.create_all()` or ORM auto-sync outside of local scratch scripts. Every model addition or change ships with a generated migration in `backend/migrations/versions/`, committed in the same change as the model.

### Two data stores, two roles

- **Relational DB (Postgres)**: users, events, attendance, photos, matches, join requests, notifications — anything relational/queryable.
- **Qdrant**: only vectors. Two logical collections:
  - `user_profiles` — one point per user (`id = user_id`, payload `user_id`), replaced on re-scan.
  - `event_faces` — one point per detected face in an uploaded photo, payload includes `event_id`, `photo_id`, `bbox`, `face_score`.
- Matching never scans all of `user_profiles`. It always filters to the current event's attendee list first (payload filter on `user_id in [attendee_user_ids]`), then does the similarity search (`MatchingService`, `core/vector_db.py`).
- **Qdrant has no foreign keys.** Its "relation" to Postgres is soft: every point's payload carries the relevant Postgres id(s) (`user_id` on `user_profiles`; `event_id` + `photo_id` on `event_faces`) as plain metadata, and every query filters on that payload instead of joining. If a `Photo` or `Event` row is deleted, its Qdrant points are orphaned unless the deleting code explicitly cleans them up too — this is a real gap to handle in Phase 7, not something the database enforces for you.

### Phase 6 specifics (already shipped, keep these seams intact)

- **Notifications** — Postgres `notifications` table is the source of truth; Redis pub/sub (`notifications:events`) is the enforcement transport. `core/notification_publisher.py` (worker side, best-effort) → `core/sse_relay.py` (app-side async subscriber, started at startup and held by a **strong reference** in `main.py`) → `core/sse.py` (`SSEManager`, one `asyncio.Queue` per live client, 15s keepalives) → browser.
- **Matching integration** — `matching_service.match_photo` returns `set[str]` of matched attendee ids; the worker publishes a `photo_matched` notification per matched user (excluding the uploader).
- **Attendee backfill** — a user who becomes an attendee after photos already exist is matched against the event's stored faces (`MatchingService.match_new_attendee`), gated on `added` in both `EventService.join` and `JoinRequestService.approve`, wrapped in try/except so a Qdrant hiccup never breaks join/approve.
- **Metrics** — `core/metrics.py` (API, `GET /metrics`) + `core/worker_metrics.py` (`:9100`, worker-alive signal) + Prometheus/Grafana/alerts in `monitoring/`.
- **SSE auth** — the stream endpoint accepts the token as a query param for browser `EventSource`; the header path still wins if both are present.

### Repos with duplicate-identity regions

- `EventRepository.list_attendee_ids`, `QdrantProfileRepository.query_similar_restricted`, `EventFaceRepository.get_faces_for_photo` (and the scroll helper it shares with `get_faces_for_event`) are the matching backbone — change them together with `MatchingService` tests (`backend/tests/unit/test_matching_service.py`, `backend/tests/unit/test_vector_db.py`) when touching matching.
- Join/approve both call `add_attendee` then backfill; keep that flow idempotent and non-fatal to Qdrant.