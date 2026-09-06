# Testing — Immich Lite

This document describes the **entire backend test suite**: every test file, every
test, and what each one was written to verify. Run it with:

```bash
python -m pytest                # run all tests
python -m pytest -v             # verbose, shows each test name
python -m pytest --cov=app --cov-report=term-missing   # with coverage
python -m pytest tests/unit/test_event_service.py -v   # one file
python -m pytest -k "join" -v   # tests matching a keyword
```

**Current state:** 94 tests, all passing, ~4s runtime.

| Scope | Line coverage |
|---|---|
| Services (`services/*`) | user 100% · event 99% · profile 100% · photo 98% · ingestion 100% · matching 100% |
| `core/security.py` | 100% |
| `core/file_storage.py` | 93% |
| Schemas (DTO validation) | ~100% |
| **Total (all `app/`)** | 43% — low areas are `repositories/`, `vector_db.py`, `embedding_service.py`, and the logging/middleware/worker modules, which need a real DB/Qdrant (integration tests, not yet written) |

---

## Shared test fixtures — `tests/conftest.py`

Everything in the suite uses **mocks** — no database, no Qdrant, no Redis, no
real face model. Every external dependency is replaced with `MagicMock(...)`
parameterized on the classes' public methods.

| Fixture | What it substitutes |
|---|---|
| `user_repo` / `event_repo` / `photo_repo` / `match_repo` | `UserRepository` / `EventRepository` / `PhotoRepository` / `PhotoMatchRepository` |
| `file_service` | `LocalFileService` |
| `embedder` | `EmbeddingProvider` (the face detect/embed model) |
| `profile_repo` / `event_face_repo` | Qdrant `QdrantProfileRepository` / `EventFaceRepository` |
| `profiles` | `ProfileService` (the dependency `EventService` uses) |
| `make_user` / `make_event` | Factories that build real `User` / `Event` SQLModel instances with sensible defaults (fixed `id`s, naive-UTC datetimes matching what Postgres stores) |

Environment: `JWT_SECRET` is force-set to a fixed test secret **before** any app
module is imported (the app's `load_dotenv()` won't override it), so JWT
encode/decode in tests is deterministic and never depends on `.env`.

---

## `tests/unit/test_security.py` — `core/security.py` (7 tests)

**Target:** password hashing (bcrypt via pwdlib) and JWT creation/decoding. Pure
functions, no mocks.

| Test | What it was made to test |
|---|---|
| `test_hash_and_verify_password` | A hashed password verifies successfully, and the hash is not the plaintext. |
| `test_verify_wrong_password` | Verifying with the wrong plaintext returns `False`. |
| `test_create_and_decode_token` | JWT round-trip: a token created for a user id decodes back to that id. |
| `test_decode_expired_token` | A manually-built token whose `exp` is in the past decodes to `None` (never crashes). |
| `test_decode_tampered_token` | Corrupting the token signature decodes to `None`. |
| `test_decode_empty_string` | An empty/blank token decodes to `None`. |
| `test_hash_is_not_reversible_plaintext` | The plaintext password never appears inside the stored hash. |

---

## `tests/unit/test_file_storage.py` — `core/file_storage.py` (8 tests)

**Target:** `LocalFileService` (write/read/copy under a storage root). Uses
pytest `tmp_path` — real files, no mocks.

| Test | What it was made to test |
|---|---|
| `test_save_and_read_roundtrip` | `save_upload` writes bytes at the returned relative path and `read` returns them unchanged. |
| `test_resolve_prevents_traversal` | A `../`-escaping path raises `ValueError` (path-traversal guard). |
| `test_save_upload_prevents_traversal` | `save_upload` itself (not just `_resolve`) rejects an escaping path. |
| `test_collect_images_only_extensions` | `collect_images` returns only files with the allowed extensions, sorted. |
| `test_collect_images_missing_dir` | A non-existent directory yields an empty list (no crash). |
| `test_copy_image` | `copy_image` copies bytes to the destination and returns the relative path. |
| `test_abs_path_is_under_root` | `abs_path` resolves inside the storage root. |
| `test_read_missing_file_raises` | Reading a missing file raises `FileNotFoundError` (the consumer maps it to a 404). |

---

## `tests/unit/test_schemas.py` — request/response DTO validation (12 tests)

**Target:** Pydantic v2 validation boundaries of the API schemas + the
`PhotoMatch.bbox_dict` JSON property.

| Test | What it was made to test |
|---|---|
| `test_register_request_valid` | A well-formed `RegisterRequest` is accepted. |
| `test_register_request_invalid_email` | `"not-an-email"` fails validation (`EmailStr`). |
| `test_register_request_short_password` | Password under 8 chars raises a `ValidationError`. |
| `test_register_request_empty_display_name` | Empty `display_name` rejected (min_length=1). |
| `test_register_request_long_display_name` | `display_name` over 100 chars rejected. |
| `test_login_request_accepts_any_password_length` | Login deliberately has no min-length (wrong-length isn't a validation error, it's a 401 at auth time). |
| `test_event_create_name_required` | Empty event name rejected (min_length=1). |
| `test_event_create_name_too_long` | Event name over 120 chars rejected. |
| `test_event_create_defaults` | `starts_at` defaults to now, `expires_at` defaults to `None` (open-ended event). |
| `test_photo_match_bbox_dict_valid` | Valid JSON bbox string parses into the expected dict. |
| `test_photo_match_bbox_dict_invalid_json` | Broken JSON falls back to `{}` instead of crashing. |
| `test_photo_match_bbox_dict_none` | `None` bbox also falls back to `{}`. |

---

## `tests/unit/test_user_service.py` — `UserService` (9 tests)

**Target:** register / authenticate / get_by_id business rules.

| Test | What it was made to test |
|---|---|
| `test_register_success` | Happy path returns the user; the password stored is a hash, never the plaintext (`"password123"` absent). |
| `test_register_duplicate_email` | Existing email → `HTTPException 409`, and `create` is never called. |
| `test_register_db_exception_still_409` | Even if the repository blows up (e.g. a racing unique-violation), the client still gets 409 — internals are never leaked. |
| `test_authenticate_success` | Correct email+password returns a `TokenResponse` with an access token. |
| `test_authenticate_wrong_password` | Wrong password → 401. |
| `test_authenticate_unknown_email` | Unknown email → 401 (same generic message as wrong password, no account enumeration). |
| `test_authenticate_email_case_insensitive` | Login looks the user up by the lowercased email — `USER@example.com` hits the `user@example.com` query. |
| `test_get_by_id_found` | Returns the user for a known id. |
| `test_get_by_id_not_found` | Returns `None` for an unknown id. |

---

## `tests/unit/test_event_service.py` — `EventService` (22 tests)

**Target:** the "active" time-window rule, event creation, join-by-link, and
member-gated detail lookup. This is the largest file because the naive-vs-aware
UTC handling has many edge cases.

### is_active — the time-window rule (8 tests)

| Test | What it was made to test |
|---|---|
| `test_is_active_within_window` | `now` strictly inside `[starts_at, expires_at]` → active. |
| `test_is_active_before_start` | `now < starts_at` → inactive (event not yet open). |
| `test_is_active_at_exact_start` | `now == starts_at` → active (boundary: the window is inclusive at the start). |
| `test_is_active_after_expiry` | `now > expires_at` → inactive (event closed). |
| `test_is_active_at_exact_expiry` | `now == expires_at` → still active — only `now > expires_at` closes it (inclusive boundary at the end too). |
| `test_is_active_null_expiry` | `expires_at=None` → active forever once started. |
| `test_is_active_naive_event_fields_tz_aware_now` | The production case: event columns are **naive UTC** but `now` arrives **tz-aware**; the service normalizes `now` so the comparison never raises `TypeError`. |
| `test_is_active_naive_default_now` | Calling without `now` (uses the current instant) behaves correctly. |

### create (4 tests)

| Test | What it was made to test |
|---|---|
| `test_create_requires_face_profile` | Owner without a face profile → 400 (the Phase-2 prerequisite), and no event row is created. |
| `test_create_success` | Valid create returns the event and **auto-adds the owner as an attendee** (`add_attendee(event.id, owner.id)`). |
| `test_create_invalid_window` | `expires_at <= starts_at` → 422, no event created. |
| `test_create_join_token_is_unique_random` | 100 generated join tokens are all unique (collision-proof slugs). |

### join (4 tests)

| Test | What it was made to test |
|---|---|
| `test_join_unknown_token` | Unknown join token → 404. |
| `test_join_inactive_event` | Joining an expired event → 410 Gone. |
| `test_join_success` | Active event → attendee added, returns `(event, joined=True)`. |
| `test_join_already_attendee` | Re-joining → `joined=False` (idempotent, no duplicate row). |

### get_by_id (4 tests)

| Test | What it was made to test |
|---|---|
| `test_get_by_id_not_found` | Unknown event → 404. |
| `test_get_by_id_not_member` | Non-owner, non-attendee → 403. |
| `test_get_by_id_owner` | Owner can view and gets the attendee count. |
| `test_get_by_id_attendee` | An attendee (not the owner) can view and gets the count. |

### search / list (2 tests)

| Test | What it was made to test |
|---|---|
| `test_search_delegates` | `search` passes the query through to the repository (name search). |
| `test_list_for_user_delegates` | `list_for_user` returns the user's own/attended events via the repository. |

---

## `tests/unit/test_profile_service.py` — `ProfileService` (7 tests)

**Target:** face-profile enrollment — detect+embed, centroid averaging, upsert.

| Test | What it was made to test |
|---|---|
| `test_enroll_success` | A single detected face is stored as the profile vector (values passthrough). |
| `test_enroll_multi_image_centroid` | Face vectors from multiple images are averaged with `np.mean` (the centroid rule) — here `[1,2,3]` ∔ `[2,4,6]` → `[1.5,3,4.5]`. |
| `test_enroll_deduplicates_face_found` | Faces across images aggregate — 2 images (2 faces + 1 face) → 3 vectors → centroid of all three, and the returned count is 3. |
| `test_enroll_no_faces` | No face detected anywhere → 422 "No face detected", and no upsert happens. |
| `test_enroll_corrupt_image` | Embedder raising `ValueError` (undecodable image) → 422, no upsert. |
| `test_has_profile_true` | `has_profile` forwards the repository's `True`. |
| `test_has_profile_false` | `has_profile` forwards `False` (used to gate event creation). |

---

## `tests/unit/test_photo_service.py` — `PhotoService` (15 tests)

**Target:** the full upload rule chain plus member-gated list and file delivery.

### upload (9 tests)

| Test | What it was made to test |
|---|---|
| `test_upload_over_size_limit` | Data over the 20 MB cap → 413, *before* anything else. |
| `test_upload_size_exact_limit_ok` | Exactly 20 MB is allowed (boundary is inclusive). |
| `test_upload_event_not_found` | Unknown event → 404. |
| `test_upload_not_member` | Neither owner nor attendee → 403. |
| `test_upload_inactive_event` | Event past its window → 410. |
| `test_upload_unsupported_extension` | A disallowed extension → 422. |
| `test_upload_missing_extension_defaults_to_jpg` | Filename with no suffix silently defaults to `.jpg`. |
| `test_upload_success_enqueues` | Happy path: file saved once at the correct relative path, `Photo` row created with `pending` status and no uploader id leak, and the worker job is enqueued with the photo id. |
| `test_upload_queue_down_upload_still_succeeds` | If Redis/the queue is unreachable, the upload **still succeeds** (photo stays pending; the failure is logged, never surfaced to the client). |

### list (2 tests)

| Test | What it was made to test |
|---|---|
| `test_list_for_event_not_member` | Non-member listing → 403. |
| `test_list_for_event_success` | Member listing returns the paginated photos + `has_more` from the repository. |

### get_photo_file (4 tests)

| Test | What it was made to test |
|---|---|
| `test_get_photo_file_success` | Member fetches stored bytes. |
| `test_get_photo_file_not_member` | Non-member file fetch → 403. |
| `test_get_photo_file_wrong_event` | Photo exists but belongs to a **different** event → 404 (cross-event fetch blocked even for members). |
| `test_get_photo_file_missing_on_disk` | Stored path missing on disk → 404 (logged). |

---

## `tests/unit/test_ingestion_service.py` — `IngestionService` (6 tests)

**Target:** photo → faces → Qdrant `event_faces` upsert → `processed` status.

| Test | What it was made to test |
|---|---|
| `test_process_success` | Happy path: file read once by `storage_path` (never copied), every face upserted to `event_faces` scoped with `event_id` + `photo_id`, status flipped to `processed` with `processed_at`. |
| `test_process_no_faces_marks_processed` | A valid photo with zero detectable faces still marks the photo `processed` (0 faces isn't a failure). |
| `test_process_embedder_failure_marks_failed` | Embedder exception → photo marked `failed` and the exception **re-raised** (so the worker can surface it). |
| `test_process_missing_file_marks_failed` | File missing on disk → also `failed` + re-raise. |
| `test_process_by_id_success` | `process_by_id` resolves the `Photo` and returns it after processing. |
| `test_process_by_id_not_found` | Unknown photo id → `FileNotFoundError` (worker treats it as a permanent failure). |

---

## `tests/unit/test_matching_service.py` — `MatchingService` (8 tests)

**Target:** attendee-scoped vector matching + the per-(photo,user) best-similarity
write and the feed.

| Test | What it was made to test |
|---|---|
| `test_match_photo_no_attendees` | No attendees → 0, nothing queried. |
| `test_match_photo_no_faces` | No stored face points for the photo → 0. |
| `test_match_photo_success` | One face, one hit: the query is **scope-limited to the attendee ids** (`user_ids` filter), the threshold is passed through, and `upsert_best` is called with the correct `photo_id`, `user_id`, `similarity`, and serialized bbox. |
| `test_match_photo_below_threshold` | No hits above threshold → 0 written, no `upsert_best`. |
| `test_match_photo_multiple_faces_same_person` | Several faces hitting the same user → several `upsert_best` calls (each carrying its own similarity; `upsert_best` itself keeps the single highest row). |
| `test_match_photo_empty_embedding_skipped` | A face with an empty embedding vector is skipped, no query issued. |
| `test_match_photo_scoped_to_attendees` | The security boundary: matching never sees non-attendees — the payload-filtered query only ever returns attendee-scoped hits, so a non-attendee can never match. |
| `test_feed_delegates` | `feed(user_id, offset, limit)` delegates to `list_feed_for_user` and returns `(items, has_more)`. |

---

## What is NOT covered yet (and why)

These areas are real code but need **integration-style** tests, so they're the
known next step rather than part of this unit suite:

- **`repositories/*`** (36–43%) — SQL against a real test database (e.g. SQLite
  in-memory or a compose Postgres): `add_attendee` idempotency, `upsert_best`
  keep-best logic, pagination `has_more`, the feed join.
- **`core/vector_db.py`** (22%) — `QdrantProfileRepository` /
  `EventFaceRepository` against a Qdrant test instance (or in-memory client):
  payload filters, collection creation, point id semantics.
- **`core/jobs.py` / `workers/photo_worker.py`** — RQ enqueue + the worker's job
  lifecycle and reconnect loop (needs a fake/mock Redis).
- **`core/logging.py` / `core/middleware.py`** — JSON formatting, correlation
  ids, the unhandled-error handler (needs an async test client).
- **`services/embedding_service.py` / `core/vector_db.py` legacy repos** —
  wrappers around heavy ONNX/InsightFace models and the Qdrant client.
- **API endpoint integration** — route-level behavior (auth dependency,
  response models, id-leak discipline) via `TestClient` with DI overrides.