# Progress

Tracks completed work against [PHASES.md](PHASES.md). See [TODO.md](TODO.md) for what's remaining.

## ✅ Phase 0 — Repo restructure, no behavior change

**Goal:** Move the existing indexer/matcher code into the new `src/app/...` layout without changing what it does.
**Status:** Complete. All stop conditions verified.

### What was done

- **Relocated InsightFace/ArcFace embedding code** → `src/app/services/embedding_service.py`
  - `InsightFaceEmbeddingService` (formerly `InsightFaceEmbeddingProvider`), RetinaFace detection, ArcFace 512-dim embeddings, HEIC support, model download/extract all moved verbatim.
- **Relocated the Qdrant client** → `src/app/core/vector_db.py`
  - `QdrantEmbeddingRepository`, `VECTOR_DIM`, batch upsert, `find_similar`, etc., moved verbatim.
- **Relocated shared domain types** → `src/app/domain/{entities,interfaces}.py`
  - `BoundingBox`, `FaceEmbedding`, `MatchResult`, `IndexerConfig`, `MatcherConfig`; `EmbeddingProvider`, `EmbeddingRepository`, `FileService`.
- **Stood up `src/app/main.py`**
  - FastAPI app with an empty `api/v1/api.py` router (`/api/v1`) and a `/ping` health check.
- **Added core scaffolding**
  - `src/app/core/config.py` — Pydantic `BaseSettings` (DB URL, Qdrant, model).
  - `src/app/core/database.py` — SQLModel engine + session + `Base`, and a `get_db` dependency.
  - Placeholder packages `models/`, `schemas/`, `workers/`.
- **Added PostgreSQL to `docker-compose.yml`** alongside the existing Qdrant service
  - `postgres:16-alpine`, dedicated volume, healthcheck, host port `5433` (host `5432` was already taken by a native Postgres).
- **Set up Alembic**
  - `alembic.ini` + `migrations/` (env.py wired to `app.core.database.Base` and the app settings DB URL).
  - No migration files yet (Phase 0 ships no tables) — `alembic upgrade head` proves the wiring.
- **Kept the legacy package importable**
  - `lite_ml_service/` modules now re-export from the relocated `src/app` code (with a `sys.path` bootstrap in `lite_ml_service/__init__.py`), so `run_indexer.py` / `run_api.py` still work.
- **Dockerfile** now builds/runs the new `src/app` app (`uvicorn app.main:app`).
- **Added deps** to `requirements.txt`: `sqlalchemy`, `sqlmodel`, `alembic`, `pydantic-settings`, `psycopg2-binary`.

### Stop-condition verification

- ✅ App boots — `uvicorn app.main:app` starts successfully.
- ✅ `/ping` returns `200` → `{"message":"pong"}`.
- ✅ `alembic upgrade head` runs with no errors against an empty database (creates only `alembic_version`).
- ✅ Old CLI scripts (`run_indexer`, `run_api`) importable from the relocated code.

### Notes / environment quirks

- On this Windows host, the OS reserves TCP port ranges (e.g. `6267–6366`, `7906–8005`) that block binding of the standard ports: `6333`/`6334` (Qdrant) and `8000` (API) all fail with WinError 10013 even in plain Python (Docker isn't the cause). The compose file maps to free host ports instead: Qdrant `8090`/`8100`, API `8080`, Postgres `5433`. The Qdrant container also remains reachable over the Docker network. `docker compose up -d` now succeeds on this machine.
- The native Windows Postgres owns host port `5432`; this project's Postgres uses host port `5433`.

## Prior work (pre-Phase 0, preserved)

Before the phased plan, the repo contained the legacy `lite_ml_service` package:

- **Indexer** — directory scan → RetinaFace detect → ArcFace embed → Qdrant/JSON upsert (batch 32/100).
- **Matcher** — centroid of up-to-3 uploads → cosine search → copy matches → zip + metadata.
- **Webcam scan UI** (`/scan`), `run_indexer.py`, `run_api.py`, `config.yml`.
