## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:

- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

## Part A — Standing Architecture Rules (apply to every phase)

### Directory structure

Grow into this layout, keeping the existing `insightface`/ArcFace embedding code and Qdrant client — relocate them, don't rewrite them. This reflects the current live structure (Phases 0–4 + frontend).

```text
alembic.ini                         # Alembic config (root, alongside docker-compose.yml)
migrations/
│   ├── env.py                      # points at the app's SQLAlchemy/SQLModel metadata
│   └── versions/                   # one file per schema change, named by phase
frontend/                           # Next.js (App Router, TS) — see notes below
src/
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── endpoints/
│   │   │   │   ├── auth.py         # register/login (thin)
│   │   │   │   ├── users.py        # profile scan + re-scan
│   │   │   │   ├── events.py       # create/join/list events + photo upload/list/file
│   │   │   │   ├── photos.py       # upload + retrieval (planned home; currently in events.py)
│   │   │   │   └── matches.py      # per-user matched-photo feed
│   │   │   └── api.py              # aggregates routers
│   │   └── deps.py                 # DI wiring: get_db, get_user_*/photo_*/file deps, get_current_user
│   ├── core/
│   │   ├── config.py               # Pydantic BaseSettings (env vars) + load_dotenv
│   │   ├── database.py             # relational DB session (Postgres)
│   │   ├── security.py             # password hashing (pwdlib[bcrypt]), JWT (PyJWT)
│   │   ├── logging.py              # setup_logging(): console + rotating file; log_exception helpers
│   │   ├── middleware.py           # RequestLoggingMiddleware (method/path/status/duration/user)
│   │   ├── vector_db.py            # Qdrant client/session wrapper + EventFaceRepository (event_faces)
│   │   ├── file_storage.py         # FileService (ABC in domain/interfaces.py): LocalFileService
│   │   └── jobs.py                 # RQ: enqueue_photo_processing(photo_id)
│   ├── domain/                     # shared value types & interfaces (Phase 0): entities, interfaces
│   ├── models/                     # SQLAlchemy/SQLModel ORM models
│   │   ├── user.py
│   │   ├── event.py
│   │   ├── event_attendee.py
│   │   ├── photo.py
│   │   └── photo_match.py
│   ├── repositories/               # DB access layer (one class per aggregate)
│   │   ├── user_repository.py      # all `users` SQLAlchemy access
│   │   └── photo_repository.py     # all `photos` access (paginated list_for_event)
│   ├── schemas/                    # Pydantic request/response DTOs
│   ├── services/                   # business logic, framework-agnostic
│   │   ├── user_service.py         # register/authenticate/get_by_id (HTTPException on error)
│   │   ├── embedding_service.py    # wraps existing InsightFace code
│   │   ├── profile_service.py      # enroll/update a user's face vector
│   │   ├── event_service.py        # event lifecycle, join logic
│   │   ├── ingestion_service.py    # photo -> faces -> embeddings
│   │   ├── photo_service.py        # upload rules + member-scoped photo list/file
│   │   └── matching_service.py     # vector search scoped to attendees
│   ├── workers/                    # background/async job entry points
│   │   └── photo_worker.py         # embed + match a single uploaded photo
│   └── main.py                     # app factory: CORS + request logging + unhandled-error handler
```

### Layering (routers → services → repositories → models)

- **Routers** (`api/v1/endpoints/*`) are thin: parse the request, call a service via `Depends(...)`, return a `response_model`. No DB, no raw SQL, no vector logic in `api/`.
- **Services** (`services/*`) own the business rules and raise `HTTPException` on errors (never leak DB exceptions or internals).
- **Repositories** (`repositories/*`) own ALL database access — a class per aggregate that takes the injected session (e.g. `UserRepository(db)`). This is the only layer with raw SQLAlchemy/SQLModel queries.
- **`api/deps.py`** wires DI: `get_db`, `get_user_repository`, `get_user_service`, `get_current_user`. No global state, no manual singletons.

### Frontend

- Located in `frontend/` (Next.js 16, App Router, TypeScript, `@/*` alias, `src/`).
- **`frontend/src/lib/api.ts` is the single API client** — it owns the FastAPI base URL (`NEXT_PUBLIC_API_URL`) and attaches `Authorization: Bearer <token>` from `localStorage`. Components never touch `localStorage`, never build auth headers, never hardcode the URL.
- To later move auth to HttpOnly cookies + a Next.js proxy, change only `lib/api.ts` (base URL becomes relative, token read from a cookie) — application components stay untouched.
- Protected pages use the `RequireAuth` client guard (`frontend/src/components/RequireAuth.tsx`).

### Logging

- All logging goes through Python's stdlib `logging`, configured once by `core/logging.setup_logging()` (console + rotating file `logs/`).
- A request-logging middleware logs every HTTP call (method/path/status/duration + `user=<id>` when authenticated); 5xx at ERROR, 4xx at WARNING.
- A global unhandled-exception handler logs the full traceback and returns a generic 500.
- **Never log passwords, JWT tokens, or password hashes.**

### Coding rules (unchanged from the original convention, keep enforcing these)

- **Thin routers** — endpoints only parse requests, call a service, return a `response_model`. No DB or vector logic in `api/`.
- **Explicit status codes** on every route decorator.
- **response_model everywhere** — never leak ORM objects or password hashes.
- **Services layer owns logic** — embedding, matching, and event-membership rules live in `services/`, not in routes or workers.
- **Repositories own DB access** — no raw SQL outside `repositories/`.
- **Dependency injection** via `Depends()` for DB sessions, current user, Qdrant client. No global state, no manual singletons.
- **Never expose the user id.** The authenticated user's id is always derived server-side from the JWT (`decode_access_token` → `sub` → `get_current_user`); no route trusts a client-supplied id, and no `*Response` schema includes the raw id. Use the DB user object's `.id` only internally (token `sub`, vector/profile lookups, logging).
- **Pydantic v2**, separate `*Create` / `*Response` schemas.
- **Async endpoints** for I/O-bound routes (DB, Qdrant, file upload). Use plain `def` (or a thread/worker offload) for the CPU-bound face-detection/embedding step so it doesn't block the event loop.
- **HTTPException only** for errors — no ad-hoc dict responses.
- **Alembic owns every schema change** — never rely on `Base.metadata.create_all()` or ORM auto-sync outside of local scratch scripts. Every model addition or change ships with a generated migration in `migrations/versions/`, committed in the same change as the model.

### Two data stores, two roles

- **Relational DB (Postgres)**: users, events, attendance, photos, match records — anything relational/queryable.
- **Qdrant**: only vectors. Two logical collections:
  - `user_profiles` — one point per user (`id = user_id`), replaced on re-scan.
  - `event_faces` — one point per detected face in an uploaded photo, payload includes `event_id`, `photo_id`, `bbox`.
- Matching never scans all of `user_profiles`. It always filters to the current event's attendee list first (payload filter on `must match any of [attendee_user_ids]`), then does the similarity search.
- **Qdrant has no foreign keys.** Its "relation" to Postgres is soft: every point's payload carries the relevant Postgres id(s) (`user_id` on `user_profiles`; `event_id` + `photo_id` on `event_faces`) as plain metadata, and every query filters on that payload instead of joining. If a `Photo` or `Event` row is deleted, its Qdrant points are orphaned unless the deleting code explicitly cleans them up too — this is a real gap to handle in Phase 7, not something the database enforces for you.
  See **Part C** below for the full field-by-field schema.

---
