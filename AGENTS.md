## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

When the user types `/graphify`, invoke the `skill` tool with `skill: "graphify"` before doing anything else.

Rules:

- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- Dirty graphify-out/ files are expected after hooks or incremental updates; dirty graph files are not a reason to skip graphify. Only skip graphify if the task is about stale or incorrect graph output, or the user explicitly says not to use it.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).

---

## Part A — Standing Architecture Rules (apply to every phase)

### Directory structure

Migrate/grow into this layout. Keep the existing `insightface`/ArcFace embedding code and Qdrant client — relocate them, don't rewrite them.

```text
alembic.ini                         # Alembic config (root, alongside docker-compose.yml)
migrations/
│   ├── env.py                      # points at the app's SQLAlchemy/SQLModel metadata
│   └── versions/                   # one file per schema change, named by phase
src/
├── app/
│   ├── api/
│   │   ├── v1/
│   │   │   ├── endpoints/
│   │   │   │   ├── auth.py
│   │   │   │   ├── users.py          # profile scan + re-scan
│   │   │   │   ├── events.py         # create/join/list events
│   │   │   │   ├── photos.py         # upload + retrieval
│   │   │   │   └── matches.py        # per-user matched-photo feed
│   │   │   └── api.py                # aggregates routers
│   ├── core/
│   │   ├── config.py                 # Pydantic BaseSettings (env vars)
│   │   ├── database.py               # relational DB session (Postgres)
│   │   ├── security.py               # password hashing, JWT
│   │   └── vector_db.py              # Qdrant client/session wrapper
│   ├── models/                       # SQLAlchemy/SQLModel ORM models
│   │   ├── user.py
│   │   ├── event.py
│   │   ├── event_attendee.py
│   │   ├── photo.py
│   │   └── photo_match.py
│   ├── schemas/                      # Pydantic request/response DTOs
│   ├── services/                     # business logic, framework-agnostic
│   │   ├── embedding_service.py      # wraps existing InsightFace code
│   │   ├── profile_service.py        # enroll/update a user's face vector
│   │   ├── event_service.py          # event lifecycle, join logic
│   │   ├── ingestion_service.py      # photo -> faces -> embeddings
│   │   └── matching_service.py       # vector search scoped to attendees
│   ├── workers/                      # background/async job entry points
│   │   └── photo_worker.py           # embed + match a single uploaded photo
│   └── main.py
```

### Coding rules (unchanged from the original convention, keep enforcing these)

- **Thin routers** — endpoints only parse requests, call a service, return a `response_model`. No DB or vector logic in `api/`.
- **Explicit status codes** on every route decorator.
- **response_model everywhere** — never leak ORM objects or password hashes.
- **Services layer owns logic** — embedding, matching, and event-membership rules live in `services/`, not in routes or workers.
- **Dependency injection** via `Depends()` for DB sessions, current user, Qdrant client. No global state, no manual singletons.
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
