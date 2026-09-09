---
 
## Part B — Phases
 
### Phase 0 — Repo restructure, no behavior change
**Goal:** Move the existing indexer/matcher code into the new `src/app/...` layout without changing what it does.
- Relocate InsightFace/ArcFace embedding code → `services/embedding_service.py`.
- Relocate Qdrant client setup → `core/vector_db.py`.
- Stand up `main.py` with an empty `api.py` router and a `/ping` health check.
- Add Postgres to `docker-compose.yml` alongside the existing Qdrant service.
- Run `alembic init migrations`, wire `env.py` to the app's declarative `Base`/`SQLModel.metadata`, and confirm `alembic upgrade head` runs cleanly against an empty database (no tables yet — this just proves the wiring).
- No new features yet.
**Stop condition:** app boots, `/ping` returns 200, `alembic upgrade head` runs with no errors, old CLI scripts still importable from their new locations.
### Phase 1 — Accounts & Auth
**Goal:** Users can register and log in.
- `models/user.py`: id (UUID PK), email (unique), hashed_password, display_name, created_at.
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login` (JWT access token).
- `core/security.py`: password hashing (passlib/bcrypt), JWT encode/decode.
- `Depends(get_current_user)` dependency for protected routes.
- Generate and apply `migrations/versions/0001_create_users.py` (`alembic revision --autogenerate -m "create users"` then review before applying).
**Explicitly out of scope this phase:** face scanning, events.
**Stop condition:** can register, log in, hit one protected `/me` route, and `alembic upgrade head` / `alembic downgrade -1` both work cleanly against the `users` table.
### Phase 2 — Face Profile Enrollment ("get scanned")
**Goal:** An authenticated user submits face image(s); this becomes their permanent profile vector.
- `POST /api/v1/users/me/scan` — accepts 1–3 images (reuse the existing centroid-averaging logic from the original matcher for multi-image submissions).
- `services/profile_service.py`: detect face(s) → embed → centroid → upsert into `user_profiles` Qdrant collection with `id=user_id`.
- Re-scanning overwrites the previous vector (upsert, not insert).
- `GET /api/v1/users/me` returns whether a profile vector exists yet (don't return the vector itself).
**Stop condition:** a user can scan, re-scan, and confirm profile status via the API.
### Phase 3 — Events
**Goal:** Users can create an event with a shareable link; opening that link while active marks you an attendee.
- `models/event.py`: id (UUID PK), owner_id (FK → users), name, join_token (random slug, unique + indexed), starts_at, expires_at, created_at.
- `models/event_attendee.py`: event_id (FK), user_id (FK), joined_at — composite primary key `(event_id, user_id)`, no surrogate id.
- `POST /api/v1/events` (create, owner must already have a face profile from Phase 2).
- `GET /api/v1/events/join/{join_token}` — **authenticated** call: if event is active (`now` between `starts_at`/`expires_at`, or `expires_at` null and event not closed), upsert an `event_attendee` row for `current_user` and return event details. If inactive, return 410 Gone.
- `GET /api/v1/events/{id}` — event details + attendee count (owner or attendee only).
- Decide and implement one explicit rule for what "URL still active" means (e.g. time window vs. an owner-toggled `is_open` boolean) — pick the simplest (time window) unless told otherwise.
- Generate and apply `migrations/versions/0002_create_events_and_attendees.py`.
**Explicitly out of scope this phase:** photo upload, matching.
**Stop condition:** an event can be created, a second test user can "join" via the link and shows up in the attendee list, and the migration applies/rolls back cleanly.
### Phase 4 — Photo Ingestion Pipeline
**Goal:** Photos uploaded to an active event get face-detected and embedded, scoped to that event.
- `models/photo.py`: id (UUID PK), event_id (FK), uploader_user_id (FK, nullable if anonymous upload is allowed), storage_path, status (enum: `pending`/`processed`/`failed`), uploaded_at, processed_at.
- `POST /api/v1/events/{id}/photos` — reject if event inactive; save file via existing `file_io` logic; create `Photo` row with `status=pending`; enqueue background processing (FastAPI `BackgroundTasks` is fine to start — note in code where this would become a real queue like Celery/RQ if volume grows).
- `services/ingestion_service.py` / `workers/photo_worker.py`: load photo → detect faces (reuse existing RetinaFace/ArcFace code) → for each face, embed and upsert into `event_faces` Qdrant collection with payload `{event_id, photo_id, bbox}` (point id is a fresh UUID per face, not the photo id — one photo can hold several faces) → set `Photo.status=processed`.
- Generate and apply `migrations/versions/0003_create_photos.py`.
- No matching yet — this phase only gets embeddings into Qdrant.
**Stop condition:** uploading a photo to an event produces the expected number of `event_faces` points in Qdrant (inspectable via a debug endpoint or direct Qdrant query) and the `photos` migration applies/rolls back cleanly.
### Phase 5 — Matching & Delivery
**Goal:** Matched photos reach the right users.
- `models/photo_match.py`: id (UUID PK), photo_id (FK), user_id (FK), similarity (float), bbox (JSON), created_at — unique constraint on `(photo_id, user_id)`.
- `services/matching_service.py`: for a processed photo's face embeddings, fetch the event's attendee `user_id` list, query `user_profiles` in Qdrant with a payload filter restricted to those ids, keep results above the similarity threshold, write `PhotoMatch` rows (dedupe: one row per photo+user, keep the best similarity if multiple faces match the same person).
- Run this automatically at the end of the Phase 4 worker (after embeddings are stored), or as its own follow-up background step — keep it a separate service call either way so it's independently testable.
- `GET /api/v1/matches/me` — authenticated user's feed: all photos matched to them, across all events they attended, newest first.
- `GET /api/v1/events/{id}/photos/{photo_id}/download` (or reuse existing zip/download logic) for retrieving the actual image.
- Generate and apply `migrations/versions/0004_create_photo_matches.py`.
**Explicitly out of scope this phase:** push/email notifications — the feed endpoint is the delivery mechanism for now.
**Stop condition:** upload a photo containing a known attendee's face → it appears in that attendee's `/matches/me` feed and nobody else's, and the migration applies/rolls back cleanly.
### Phase 6 — Notifications (optional, only after 0–5 are solid)
**Goal:** Push matched photos to users instead of requiring them to poll the feed.
- Pick one channel to start (e.g. email via a transactional provider, or WebSocket for in-app real-time).
- Trigger from the same point Phase 5 writes a `PhotoMatch` row — don't duplicate matching logic, just hook a notifier onto that event.
**Stop condition:** a test match triggers exactly one notification per matched user per photo.
### Phase 7 — Hardening & Ops
**Goal:** Make it deployable and safe to run unattended.
- Rate-limit uploads and scans; validate image content-type/size.
- Background worker becomes a real queue (Celery/RQ/arq) if Phase 4's `BackgroundTasks` approach is still in place.
- Structured logging around the ingestion → matching pipeline (photo id, event id, faces found, matches found).
- `docker-compose.yml` finalized: Postgres, Qdrant, API, worker.
- Delete/expire event data and Qdrant points for events past retention.
---

## Part C — Full Schema Reference

### Postgres

**users**
| field | type | notes |
|---|---|---|
| id | uuid, PK | |
| email | string | unique |
| hashed_password | string | never store plaintext |
| display_name | string | |
| created_at | timestamp | |

**events**
| field | type | notes |
|---|---|---|
| id | uuid, PK | |
| owner_id | uuid, FK → users.id | |
| name | string | |
| join_token | string | unique, indexed — the lookup key for `/events/join/{token}` |
| starts_at | timestamp | |
| expires_at | timestamp | nullable if you go with a manual `is_open` toggle instead of a time window |
| created_at | timestamp | |

**event_attendees**
| field | type | notes |
|---|---|---|
| event_id | uuid, FK → events.id | composite PK with user_id |
| user_id | uuid, FK → users.id | composite PK with event_id |
| joined_at | timestamp | |

**photos**
| field | type | notes |
|---|---|---|
| id | uuid, PK | |
| event_id | uuid, FK → events.id | |
| uploader_user_id | uuid, FK → users.id | nullable if anonymous upload is allowed |
| storage_path | string | |
| status | enum | `pending` \| `processed` \| `failed` |
| uploaded_at | timestamp | |
| processed_at | timestamp | nullable until processed |

**photo_matches**
| field | type | notes |
|---|---|---|
| id | uuid, PK | |
| photo_id | uuid, FK → photos.id | |
| user_id | uuid, FK → users.id | |
| similarity | float | cosine similarity score |
| bbox | json | `{x1, y1, x2, y2}` |
| created_at | timestamp | unique constraint on `(photo_id, user_id)` — keep best similarity if multiple faces match one person |

### Qdrant (soft-linked via payload, not FK-enforced)

**user_profiles**
| field | notes |
|---|---|
| id | **is** the `user_id` — enables plain upsert on re-scan, no lookup needed |
| vector | 512-dim, ArcFace output |
| payload.user_id | duplicate of id, kept in payload for filterable queries |

**event_faces**
| field | notes |
|---|---|
| id | random uuid — one photo can hold several faces, so this can't be the photo id |
| vector | 512-dim, ArcFace output |
| payload.event_id | scopes the point to an event |
| payload.photo_id | scopes the point to a photo |
| payload.bbox | `{x1, y1, x2, y2}` — which face in the photo this point represents |

---

## Notes for the agent

- The original CLI (`run_indexer.py`, `run_api.py`) and its directory-scanning workflow are being superseded, not preserved as a parallel feature — don't spend effort keeping the old CLI entry points working past Phase 0 unless asked.
- Reuse the existing `buffalo_l` InsightFace model and threshold/centroid logic rather than re-deriving it; the math doesn't change, only what it's plugged into.
- Every phase should be runnable and demoable on its own before moving on.
