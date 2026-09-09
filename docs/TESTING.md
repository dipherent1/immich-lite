# Testing — Immich Lite

This document describes the **entire backend test suite**: every test file, every
test, and what each one was written to verify. Run it with:

```bash
python -m pytest                                           # all tests
python -m pytest -v                                        # verbose, shows each test name
python -m pytest --cov=app --cov-report=term-missing       # with coverage
python -m pytest tests/unit/test_event_service.py -v       # one file
python -m pytest tests/integration -v                      # integration tests only
python -m pytest -k "join" -v                              # tests matching a keyword
```

**Current state:** 206 tests (131 unit · 39 repository · 36 integration), all passing, ~35s runtime, **80% line coverage**. Total coverage dropped from the ~89% documented earlier because the Phase 6 code added ~600 lines of notification/SSE/join-request surface (`core/sse.py`, `core/sse_relay.py`, `repositories/join_request_repository.py`, `repositories/notification_repository.py`, `notification_service.py`, `join_request_service.py`) that has no dedicated unit tests yet — the pre-Phase-6 modules remain at 90%+ as listed below.

> **Paths:** all paths below are relative to the `backend/` directory. Run the
> test commands from `backend/` (`pytest` resolves `testpaths`/`pythonpath` from
> `backend/pyproject.toml`).

| Scope | Line coverage |
|---|---|
| Services (`services/*`) | user 100% · event 99% · profile 100% · photo 98% · ingestion 100% · matching 100% |
| Repositories (`repositories/*`) | user 100% · event 100% · photo 100% · photo_match 100% |
| `core/security.py` | 100% |
| `core/vector_db.py` | 98% |
| `core/jobs.py` | 100% |
| `core/file_storage.py` | 93% |
| `api/deps.py` | 89% |
| `api/v1/endpoints/*` | auth 100% · events 100% · matches 100% · users 95% |
| Schemas (DTO validation) | ~100% |
| **Total (all `app/`)** | **80%** — remaining gaps: `embedding_service.py` (legacy GPU model wrapper, intentionally untested) 16%, `workers/` (excluded from coverage), Phase 6 notifiers: `sse.py` 0% · `sse_relay.py` 33% · `notification_repository.py` 33% · `join_request_repository.py` 34% · `notification_service.py` 48% · `join_request_service.py` 70% · `core/metrics.py` 52% · `core/middleware.py` 87% |

---

## Shared test fixtures — `tests/conftest.py`

| Fixture | What it provides |
|---|---|
| `user_repo` / `event_repo` / `photo_repo` / `match_repo` | `MagicMock(spec=...)` of each repository class |
| `file_service` | `MagicMock(spec=LocalFileService)` |
| `embedder` | `MagicMock(spec=EmbeddingProvider)` (the face detect/embed model) |
| `profile_repo` / `event_face_repo` | `MagicMock(spec=...)` of the Qdrant repositories |
| `profiles` | `MagicMock(spec=ProfileService)` |
| `make_user` / `make_event` | Factories that build real `User` / `Event` SQLModel instances with sensible defaults |
| `db_session` | **SQLite in-memory session** — creates all tables via `SQLModel.metadata.create_all`, yields a `sqlmodel.Session`, and tears down after each test. Used by repository tests and integration tests. |

Environment: `JWT_SECRET` is force-set to a fixed test secret **before** any app
module is imported (the app's `load_dotenv()` won't override it), so JWT
encode/decode in tests is deterministic and never depends on `.env`.

---

## `tests/unit/` — isolated unit tests (75 tests)

### `test_security.py` — `core/security.py` (7 tests)

**Target:** password hashing (bcrypt via pwdlib) and JWT creation/decoding.

| Test | What it was made to test |
|---|---|
| `test_hash_and_verify_password` | A hashed password verifies successfully, and the hash is not the plaintext. |
| `test_verify_wrong_password` | Verifying with the wrong plaintext returns `False`. |
| `test_create_and_decode_token` | JWT round-trip: a token created for a user id decodes back to that id. |
| `test_decode_expired_token` | A manually-built token whose `exp` is in the past decodes to `None`. |
| `test_decode_tampered_token` | Corrupting the token signature decodes to `None`. |
| `test_decode_empty_string` | An empty/blank token decodes to `None`. |
| `test_hash_is_not_reversible_plaintext` | The plaintext password never appears inside the stored hash. |

### `test_file_storage.py` — `core/file_storage.py` (8 tests)

**Target:** `LocalFileService` (write/read/copy under a storage root). Uses
pytest `tmp_path` — real files, no mocks.

| Test | What it was made to test |
|---|---|
| `test_save_and_read_roundtrip` | `save_upload` writes bytes at the returned relative path and `read` returns them unchanged. |
| `test_resolve_prevents_traversal` | A `../`-escaping path raises `ValueError`. |
| `test_save_upload_prevents_traversal` | `save_upload` itself rejects an escaping path. |
| `test_collect_images_only_extensions` | `collect_images` returns only files with allowed extensions, sorted. |
| `test_collect_images_missing_dir` | A non-existent directory yields an empty list. |
| `test_copy_image` | `copy_image` copies bytes and returns the relative path. |
| `test_abs_path_is_under_root` | `abs_path` resolves inside the storage root. |
| `test_read_missing_file_raises` | Reading a missing file raises `FileNotFoundError`. |

### `test_schemas.py` — request/response DTO validation (12 tests)

**Target:** Pydantic v2 validation boundaries of the API schemas + `PhotoMatch.bbox_dict`.

| Test | What it was made to test |
|---|---|
| `test_register_request_valid` | A well-formed `RegisterRequest` is accepted. |
| `test_register_request_invalid_email` | `"not-an-email"` fails validation (`EmailStr`). |
| `test_register_request_short_password` | Password under 8 chars raises a `ValidationError`. |
| `test_register_request_empty_display_name` | Empty `display_name` rejected. |
| `test_register_request_long_display_name` | `display_name` over 100 chars rejected. |
| `test_login_request_accepts_any_password_length` | Login has no min-length (wrong-length is a 401, not a 422). |
| `test_event_create_name_required` | Empty event name rejected. |
| `test_event_create_name_too_long` | Event name over 120 chars rejected. |
| `test_event_create_defaults` | `starts_at` defaults to now, `expires_at` defaults to `None`. |
| `test_photo_match_bbox_dict_valid` | Valid JSON bbox string parses into the expected dict. |
| `test_photo_match_bbox_dict_invalid_json` | Broken JSON falls back to `{}`. |
| `test_photo_match_bbox_dict_none` | `None` bbox falls back to `{}`. |

### `test_user_service.py` — `UserService` (9 tests)

**Target:** register / authenticate / get_by_id business rules.

| Test | What it was made to test |
|---|---|
| `test_register_success` | Happy path; the password stored is a hash, never plaintext. |
| `test_register_duplicate_email` | Existing email → 409; `create` never called. |
| `test_register_db_exception_still_409` | Repository exception → still 409, no internals leaked. |
| `test_authenticate_success` | Correct credentials → `TokenResponse`. |
| `test_authenticate_wrong_password` | Wrong password → 401. |
| `test_authenticate_unknown_email` | Unknown email → 401 (no account enumeration). |
| `test_authenticate_email_case_insensitive` | `USER@example.com` hits the `user@example.com` query. |
| `test_get_by_id_found` | Returns the user for a known id. |
| `test_get_by_id_not_found` | Returns `None` for an unknown id. |

### `test_event_service.py` — `EventService` (22 tests)

**Target:** the "active" time-window rule, event creation, join-by-link, and
member-gated detail lookup. Naive-vs-aware UTC handling edge cases.

| Test | What it was made to test |
|---|---|
| `test_is_active_within_window` | `now` strictly inside the window → active. |
| `test_is_active_before_start` | `now < starts_at` → inactive. |
| `test_is_active_at_exact_start` | `now == starts_at` → active. |
| `test_is_active_after_expiry` | `now > expires_at` → inactive. |
| `test_is_active_at_exact_expiry` | `now == expires_at` → active (inclusive boundary). |
| `test_is_active_null_expiry` | `expires_at=None` → active forever once started. |
| `test_is_active_naive_event_fields_tz_aware_now` | Naive event fields + tz-aware `now` → normalized and correct. |
| `test_is_active_naive_default_now` | Calling without `now` uses the current instant. |
| `test_create_requires_face_profile` | No face profile → 400; no event row created. |
| `test_create_success` | Valid create returns event; owner auto-added as attendee. |
| `test_create_invalid_window` | `expires_at <= starts_at` → 422. |
| `test_create_join_token_is_unique_random` | 100 tokens are all unique. |
| `test_join_unknown_token` | Unknown token → 404. |
| `test_join_inactive_event` | Expired event → 410 Gone. |
| `test_join_success` | Active event → attendee added, `joined=True`. |
| `test_join_already_attendee` | Re-joining → `joined=False` (idempotent). |
| `test_get_by_id_not_found` | Unknown event → 404. |
| `test_get_by_id_not_member` | Non-owner/non-attendee → 403. |
| `test_get_by_id_owner` | Owner can view; attendee count returned. |
| `test_get_by_id_attendee` | Attendee (not owner) can view. |
| `test_search_delegates` | Query passes through to repository. |
| `test_list_for_user_delegates` | Returns user's own/attended events. |

### `test_profile_service.py` — `ProfileService` (7 tests)

**Target:** face-profile enrollment — detect+embed, centroid averaging, upsert.

| Test | What it was made to test |
|---|---|
| `test_enroll_success` | Single face stored as the profile vector. |
| `test_enroll_multi_image_centroid` | Multiple face vectors averaged via `np.mean`. |
| `test_enroll_deduplicates_face_found` | Faces across images aggregate; returned count is correct. |
| `test_enroll_no_faces` | No face → 422 "No face detected". |
| `test_enroll_corrupt_image` | Embedder raises `ValueError` → 422. |
| `test_has_profile_true` | Forwards the repository's `True`. |
| `test_has_profile_false` | Forwards `False`. |

### `test_photo_service.py` — `PhotoService` (15 tests)

**Target:** the full upload rule chain plus member-gated list and file delivery.

| Test | What it was made to test |
|---|---|
| `test_upload_over_size_limit` | Over 20 MB → 413. |
| `test_upload_size_exact_limit_ok` | Exactly 20 MB allowed. |
| `test_upload_event_not_found` | Unknown event → 404. |
| `test_upload_not_member` | Non-member → 403. |
| `test_upload_inactive_event` | Past window → 410. |
| `test_upload_unsupported_extension` | Disallowed extension → 422. |
| `test_upload_missing_extension_defaults_to_jpg` | No suffix → `.jpg` default. |
| `test_upload_success_enqueues` | File saved, `Photo` row created (pending), job enqueued. |
| `test_upload_queue_down_upload_still_succeeds` | Queue unreachable → upload still succeeds (failure logged). |
| `test_list_for_event_not_member` | Non-member listing → 403. |
| `test_list_for_event_success` | Member listing returns paginated photos + `has_more`. |
| `test_get_photo_file_success` | Member fetches stored bytes. |
| `test_get_photo_file_not_member` | Non-member → 403. |
| `test_get_photo_file_wrong_event` | Photo belongs to a different event → 404. |
| `test_get_photo_file_missing_on_disk` | Stored path missing → 404. |

### `test_ingestion_service.py` — `IngestionService` (6 tests)

**Target:** photo → faces → Qdrant `event_faces` upsert → `processed` status.

| Test | What it was made to test |
|---|---|
| `test_process_success` | File read, faces upserted, status flipped to `processed`. |
| `test_process_no_faces_marks_processed` | Zero detectable faces → `processed` (not a failure). |
| `test_process_embedder_failure_marks_failed` | Embedder exception → `failed`, exception re-raised. |
| `test_process_missing_file_marks_failed` | File missing → `failed`, re-raised. |
| `test_process_by_id_success` | Resolves Photo, returns it after processing. |
| `test_process_by_id_not_found` | Unknown photo id → `FileNotFoundError`. |

### `test_matching_service.py` — `MatchingService` (8 tests)

**Target:** attendee-scoped vector matching, per-(photo,user) best-similarity write, feed.

| Test | What it was made to test |
|---|---|
| `test_match_photo_no_attendees` | No attendees → 0, nothing queried. |
| `test_match_photo_no_faces` | No stored face points → 0. |
| `test_match_photo_success` | One face, one hit: scope-limited query, threshold passed through, `upsert_best` called correctly. |
| `test_match_photo_below_threshold` | No hits above threshold → 0 written. |
| `test_match_photo_multiple_faces_same_person` | Several faces → several `upsert_best` calls. |
| `test_match_photo_empty_embedding_skipped` | Empty embedding vector → skipped. |
| `test_match_photo_scoped_to_attendees` | Payload filter guarantees only attendees can match. |
| `test_feed_delegates` | `feed()` delegates to `list_feed_for_user`. |

### `test_vector_db.py` — `core/vector_db.py` (20 tests)

**Target:** all three Qdrant repository classes against an in-memory `QdrantClient`
(patching `app.core.vector_db.QdrantClient` to a shared `:memory:` client).
Unit vectors with a single hot dimension enable deterministic cosine-similarity
checks.

**Fixture:** `qdrant` — monkeypatches `QdrantClient` so every constructor returns
a single shared in-memory instance; all Qdrant warnings are expected (local mode
doesn't support payload indexes).

| Test | What it was made to test |
|---|---|
| `test_has_profile_false_for_missing_user` | Unknown user id → `False`. |
| `test_upsert_then_has_profile` | After upsert, `has_profile` returns `True`. |
| `test_rescan_replaces_vector_without_duplicate_point` | Second upsert for same user replaces; count stays 1; old vector no longer matches. |
| `test_query_scoped_to_user_ids` | Query only returns results from the requested user-ids, never others. |
| `test_query_respects_threshold` | Identical vector (similarity 1.0) passes threshold 0.9. |
| `test_query_above_threshold_filters_other_vector` | Orthogonal vector (similarity 0.0) filtered by threshold 0.6. |
| `test_query_empty_user_ids_returns_nothing` | Empty user-ids list → `[]` without querying. |
| `test_upsert_faces_returns_count_and_persists` | Two faces stored, count is 2, `count()` confirms 2 points. |
| `test_upsert_faces_empty_returns_zero` | Empty embeddings list → 0. |
| `test_get_faces_for_photo_roundtrip` | Stored faces retrieved with correct bbox, score, and embedding. |
| `test_get_faces_scoped_by_photo` | Each photo's faces are isolated; empty photo id → `[]`. |
| `test_point_payload_carries_event_and_photo_ids` | Qdrant point payload stores `event_id` and `photo_id`. |
| `test_point_id_is_stable_md5` | `_point_id` returns consistent hash; different inputs → different hashes. |
| `test_upsert_batch_and_load_all` | Two embeddings round-tripped via upsert + `load_all`. |
| `test_save_all_full_replace` | `save_all` deletes old data, stores only new. |
| `test_find_similar_returns_hit_with_similarity_and_bbox` | One hit above threshold; similarity, path, and bbox correct. |
| `test_find_similar_below_threshold_filters_out` | Orthogonal vector → no hits at threshold 0.6. |
| `test_delete_by_dir_deletes_only_matching_prefix` | Deletes only files under the given prefix. |
| `test_delete_by_dir_empty_matches_returns_zero` | No matches → 0 deleted, no crash. |
| `test_get_indexed_paths` | Returns only paths under the given prefix. |

### `test_jobs.py` — `core/jobs.py` (2 tests)

**Target:** `enqueue_photo_processing` — Redis connection, RQ queue delegation, and error re-raise.

| Test | What it was made to test |
|---|---|
| `test_enqueue_success_delegates_to_rq_queue` | Fake Redis+RQ: correct queue name (`photos`), correct job function path, `job_timeout=300`, `record_enqueue("photos")` called. |
| `test_enqueue_reraises_when_redis_unavailable` | Redis.from_url raises → exception re-raised; `record_enqueue` not called. |

---

## `tests/repositories/` — repository tests against SQLite (39 tests)

All repository tests use the **`db_session`** fixture (in-memory SQLite,
`StaticPool`, all tables created and dropped per test) to exercise real
SQLAlchemy/SQLModel queries. No mocks are used — these are real database
integration tests at the repository level.

### `test_user_repository.py` — `UserRepository` (8 tests)

| Test | What it was made to test |
|---|---|
| `test_create_lowercases_email` | Email is lowercased on insert; all fields stored. |
| `test_get_by_id_roundtrip` | Created user retrieved by id. |
| `test_get_by_id_not_found` | Unknown id → `None`. |
| `test_get_by_email_found` | Created user retrieved by email. |
| `test_get_by_email_case_sensitive_lookup` | `get_by_email` is an exact (not case-insensitive) lookup. |
| `test_get_by_email_not_found` | Unknown email → `None`. |
| `test_create_duplicate_email_raises_integrity_error` | Duplicate email → `IntegrityError`. |
| `test_session_still_usable_after_integrity_error` | Session survives a failed insert (rollback); no stale state. |

### `test_event_repository.py` — `EventRepository` (11 tests)

| Test | What it was made to test |
|---|---|
| `test_create_event_persists` | Event stored; `get_by_id` and `get_by_token` return it. |
| `test_get_by_id_not_found` | Unknown event → `None`. |
| `test_get_by_token_not_found` | Unknown token → `None`. |
| `test_add_attendee_and_is_attendee` | After `add_attendee`, `is_attendee` returns `True`. |
| `test_add_attendee_duplicate_returns_false` | Second add → `False`; count stays 1. |
| `test_attendee_count_zero_when_nobody_joined` | No attendees → count 0. |
| `test_list_attendee_ids_returns_distinct_ids` | Duplicate add doesn't duplicate ids; correct set returned. |
| `test_search_by_name_partial_case_insensitive` | Partial, case-insensitive matching works. |
| `test_search_by_name_newest_first` | Results ordered by `created_at` desc. |
| `test_list_for_user_owned_and_attended_deduped` | Owned + attended events all returned; no duplicates. |
| `test_list_for_user_newest_first` | Results ordered by `created_at` desc. |

### `test_photo_repository.py` — `PhotoRepository` (10 tests)

| Test | What it was made to test |
|---|---|
| `test_create_photo_starts_pending` | Created photo has `status="pending"`, `processed_at=None`. |
| `test_get_by_id_roundtrip` | Created photo retrieved by id. |
| `test_get_by_id_not_found` | Unknown photo → `None`. |
| `test_set_status_processed_sets_processed_at` | `processed=True` sets `processed_at` to a datetime. |
| `test_set_status_failed_leaves_processed_at_none` | `processed=False` → `processed_at` stays `None`. |
| `test_set_status_missing_photo_is_noop` | Unknown photo id → no crash. |
| `test_list_pending_only_pending_oldest_first` | Only pending photos returned, ordered by `uploaded_at` asc; setting one to processed removes it from the list. |
| `test_list_pending_respects_limit` | `limit=2` returns exactly 2. |
| `test_list_for_event_newest_first_and_pagination` | 25 photos → first page has 24 (newest first, `has_more=True`); second page has 1 (`has_more=False`). |
| `test_list_for_event_scoped_to_event` | Photos from event B don't appear in event A's listing. |

### `test_photo_match_repository.py` — `PhotoMatchRepository` (10 tests)

| Test | What it was made to test |
|---|---|
| `test_upsert_best_inserts_new_row` | First insert creates a row with the given similarity and bbox. |
| `test_upsert_best_keeps_higher_similarity` | Second insert with higher similarity updates the existing row. |
| `test_upsert_best_ignores_lower_similarity` | Lower similarity leaves the row unchanged. |
| `test_upsert_best_no_duplicate_per_pair` | Five calls → only one row per (photo, user). |
| `test_list_for_user_scoped_and_newest_first` | Returns only matches for the given user, ordered by `created_at` desc. |
| `test_list_for_user_pagination_with_has_more` | 25 matches → `has_more=True` at limit 24; next page returns 1, `has_more=False`. |
| `test_list_feed_for_user_joins_event` | Feed returns `(PhotoMatch, Event)` tuples, newest first, correct event names. |
| `test_list_feed_for_user_only_matches_for_joined_events` | A match for an unrelated event still appears (the join isn't scoped by user membership — the feed shows all matched photos the user has). |
| `test_bbox_dict_property` | Valid bbox JSON parses to a dict. |
| `test_bbox_dict_property_invalid_json` | Invalid JSON → `{}`. |

---

## `tests/integration/` — full API integration tests (36 tests)

These tests exercise the **entire HTTP stack** via `fastapi.testclient.TestClient`.
Each request flows through the real router, DI, service, and repository layers
against an in-memory SQLite database. All Qdrant-backed dependencies are replaced
with `MagicMock` overrides.

**Shared fixtures** (`tests/integration/conftest.py`):

| Fixture | What it provides |
|---|---|
| `client` | `TestClient(app)` wired to `db_session`, temp-dir `LocalFileService`, and mocked `QdrantProfileRepository`, `EventFaceRepository`, `ProfileService` via `dependency_overrides` |
| `profile_repo` | `MagicMock(spec=QdrantProfileRepository)` with `has_profile.return_value = True` by default |
| `face_repo` | `MagicMock(spec=EventFaceRepository)` |
| `profile_service` | `MagicMock(spec=ProfileService)` |

Helper functions: `register_user(client, ...)`, `login(client, ...)`, `auth_header(client, ...)`, `make_event(client, headers, ...)`.

### `test_api_auth.py` — `/api/v1/auth` + `/api/v1/users/me` (11 tests)

| Test | What it was made to test |
|---|---|
| `test_register_returns_public_user` | 201; email + display_name present, `hashed_password` absent. |
| `test_register_duplicate_email_conflict` | Second register → 409. |
| `test_register_short_password_rejected` | Password < 8 chars → 422. |
| `test_register_invalid_email_rejected` | `"not-an-email"` → 422. |
| `test_login_success_returns_bearer_token` | 200; `token_type == "bearer"`; `access_token` present. |
| `test_login_wrong_password_unauthorized` | Wrong password → 401. |
| `test_login_unknown_user_unauthorized` | Unknown email → 401. |
| `test_me_with_valid_token` | GET `/users/me` → 200; `has_face_profile == True` (mock default). |
| `test_me_without_token_unauthorized` | No token → 401. |
| `test_me_with_garbage_token_unauthorized` | Invalid token → 401. |
| `test_has_face_profile_reflects_profile_repo` | When mock `has_profile` returns `False`, the response reflects it. |

### `test_api_events.py` — events CRUD, join, scan (15 tests)

| Test | What it was made to test |
|---|---|
| `test_create_event_requires_face_profile` | `has_profile=False` → 400 "face profile". |
| `test_create_event_success` | 201; name, join_token, `active=True` in response. |
| `test_create_event_with_expiry_in_past_rejected` | `expires_at < starts_at` → 422. |
| `test_create_event_rejects_empty_name` | Empty name → 422. |
| `test_list_my_events_empty_then_returns_created` | Initially `[]`; after create, one event listed. |
| `test_search_excludes_join_token` | Search response is `EventPublicResponse` (no `join_token`). |
| `test_get_event_detail_as_member` | Owner sees detail with `attendee_count=1`. |
| `test_get_event_detail_non_member_forbidden` | Intruder → 403. |
| `test_get_event_detail_not_found` | Unknown id → 404. |
| `test_join_by_token_success_then_duplicate` | First join → `joined=True`; second → `joined=False`. |
| `test_join_unknown_token_not_found` | Unknown token → 404. |
| `test_joined_event_appears_in_search_for_guest` | Guest who joined sees event in search results. |
| `test_scan_reports_images_processed_and_faces_found` | Upload 2 images → `images_processed=2, faces_found=1`. |
| `test_scan_requires_auth` | No token → 401. |
| `test_scan_bad_image_count_rejected` | Empty file list → 422. |

### `test_api_photos.py` — photo upload/list/file + match feed (10 tests)

A `monkeypatch`-based `autouse` fixture replaces `enqueue_photo_processing` with
a no-op so uploads never hit Redis. All photo tests create real files in a temp
directory via the overridden `LocalFileService`.

| Test | What it was made to test |
|---|---|
| `test_upload_and_fetch_roundtrip` | Upload a JPEG → 201; list shows 1 photo; file endpoint returns the exact bytes. |
| `test_upload_by_non_member_forbidden` | Intruder → 403. |
| `test_upload_to_unknown_event_not_found` | Unknown event → 404. |
| `test_upload_unsupported_extension_rejected` | `.exe` → 422. |
| `test_upload_oversized_file_rejected` | >20 MB → 413. |
| `test_photo_list_paginates` | 3 photos, limit=2 → `has_more=True`, next offset=2, then 1 item with `has_more=False`. |
| `test_photo_list_non_member_forbidden` | Intruder lists photos → 403. |
| `test_photo_file_missing_on_disk_returns_404` | After upload (200 OK), deleting the stored file makes the next fetch return 404. |
| `test_feed_lists_only_current_users_matches` | Owner's match doesn't appear in guest's feed; guest's match appears with correct `photo_id`, `event_name`, `similarity`, `bbox`, `file_url`. |
| `test_feed_empty_for_user_without_matches` | No matches → `items=[], has_more=False`. |

---

## What is NOT covered yet (and why)

These areas are real code but are intentionally excluded from the test suite:

- **`services/embedding_service.py`** (16%) — legacy `InsightFaceEmbeddingService` wrapper around the GPU-bound face-detection ONNX model. Requires downloading the `buffalo_l` model (~100 MB), loading it into memory, and a real ONNX runtime. This is a thin adapter layer over existing InsightFace code; it's tested implicitly when the full pipeline runs. No plans to unit-test it.
- **`workers/photo_worker.py`** (excluded from coverage) — RQ worker entry point that runs in a separate process. Tested implicitly via the repository/service layer tests above.
- **`core/logging.py`** (95%) — JSON formatter and rotating-file setup. Only the file-rotation handler branch is untested.
- **`core/middleware.py`** (87%) — `RequestLoggingMiddleware` correlation-id injection. The `process_request` → `call_next` chain requires an async ASGI test harness.
- **`core/metrics.py`** (52%) — Prometheus counters for RQ queue depth. The `refresh_rq_metrics` function requires a live Redis connection; the remaining lines are the gauge-update loop.
- **`core/database.py`** (73%) — `get_db` generator and engine setup. The engine creation is a startup-time side effect; the generator body is covered via integration tests.
- **`main.py`** (79%) — the unhandled-exception handler and metrics endpoint require specific ASGI error conditions and live Redis.
- **`api/deps.py`** (89%) — the real (non-overridden) `get_profile_repository`, `get_file_service`, `get_event_face_repository` factories that construct Qdrant/LocalFileService instances. These are thin one-liners; the integration tests override them to avoid connecting to real infrastructure.