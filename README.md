# Immich Lite — Face Matching Microservice

A lightweight, standalone Python microservice for face embedding extraction and similarity matching, extracted from the main [Immich](https://github.com/immich-app/immich) machine-learning service. It uses the same **insightface** backend (ArcFace + RetinaFace) to keep embeddings compatible with the full Immich pipeline.

The project is being rebuilt around a phased plan (see [PHASES.md](PHASES.md)). **Phase 0 (repo restructure) is complete.** The code has been relocated into the new `src/app/...` layout without changing behavior.

## Status

| Phase | Description                          | Status  |
| ----- | ------------------------------------ | ------- |
| 0     | Repo restructure, no behavior change | ✅ Done |
| 1     | Accounts & Auth                      | ⬜ Todo |
| 2     | Face Profile Enrollment              | ⬜ Todo |
| 3     | Events                               | ⬜ Todo |
| 4     | Photo Ingestion Pipeline             | ⬜ Todo |
| 5     | Matching & Delivery                  | ⬜ Todo |
| 6     | Notifications (optional)             | ⬜ Todo |
| 7     | Hardening & Ops                      | ⬜ Todo |

See [PROGRESS.md](PROGRESS.md) for what's done and [TODO.md](TODO.md) for what's next.

## Phase 0 — Architecture (current)

The codebase now has two layers:

- **`src/app/`** — the new canonical application:
  - `main.py` — FastAPI app with `/ping` health check
  - `api/v1/api.py` — the API router (empty so far; sub-routers like auth/users/events land here in later phases)
  - `core/` — `config.py` (Pydantic settings), `database.py` (SQLModel/Postgres engine + session + `Base`), `vector_db.py` (Qdrant client)
  - `services/` — `embedding_service.py` (InsightFace + ArcFace + RetinaFace)
  - `domain/` — entities + interfaces (moved from the old package)
  - `models/`, `schemas/`, `workers/` — empty placeholders for later phases
- **`lite_ml_service/`** — the **legacy** package. It is superseded but still importable: its modules re-export from the relocated `src/app` code so the old CLI scripts (`run_indexer.py`, `run_api.py`) keep working. Do not add new code here.

```
immich-lite/
├── src/app/                     # canonical app
│   ├── main.py                  # FastAPI + /ping
│   ├── api/v1/api.py            # router (empty in Phase 0)
│   ├── core/{config,database,vector_db}.py
│   ├── services/embedding_service.py
│   ├── domain/{entities,interfaces}.py
│   └── models/, schemas/, workers/
├── lite_ml_service/             # legacy (re-exports from src/app)
├── migrations/                  # Alembic migrations (env.py wired to app Base)
├── alembic.ini                  # Alembic config
├── docker-compose.yml           # Qdrant + PostgreSQL + app
├── Dockerfile
├── run_indexer.py / run_api.py  # legacy CLI entry points
├── config.yml                   # legacy config
└── output/                      # legacy match output
```

## Requirements

- Python 3.11
- [Docker](https://docs.docker.com/engine/install/) and Docker Compose
- ~16 MB disk for the ONNX model (downloaded automatically from HuggingFace)

## Quick Start (Docker)

```bash
docker compose up -d
```

### Update the code only

```bash
docker compose up -d --build app
```

### To see the logs

```bash
docker logs -f immich-lite-app
```

This starts:

- **Qdrant** vector database (host ports `8090` REST / `8100` gRPC)
- **PostgreSQL** (host port `5433`)
- **Immich Lite** API server on host port `8080` (maps to the container's 8000)

> Note on this machine: Windows reserves TCP port ranges (e.g. `6267–6366`,
> `7906–8005`) that block binding to `6333`/`6334` and `8000`. The compose file maps
> to host ports outside those ranges (`8090`/`8100`/`8080`). The container ports are
> unchanged — only the host-facing bindings differ. Verify a port is free with
> `python -c "import socket; socket.socket().bind(('0.0.0.0', PORT))"`.

## Local Development Setup

### 1. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

For the new `src/app` layer, also install the relational/migration stack (included in the requirements above):

```bash
pip install sqlalchemy sqlmodel alembic pydantic-settings psycopg2-binary
```

### 2. Start the backing services

```bash
docker compose up -d qdrant postgres
```

### 3. Configure environment (`.env`)

```env
QDRANT_URL=http://localhost:8090
DATABASE_URL=postgresql+psycopg2://immich:immich@localhost:5433/immich_lite
```

Settings are read from `.env` by `src/app/core/config.py` (Pydantic settings). Override any field with the matching env var.

### 4. Run the new API server

```bash
# from the project root
PYTHONPATH=src uvicorn app.main:app --host 0.0.0.0 --port 8080
uvicorn app.main:app --host 0.0.0.0 --port 8080   # (if running from src/)
```

Health check:

```bash
curl http://localhost:8080/ping
# {"message":"pong"}
```

## Database Migrations (Alembic)

Alembic owns every schema change — never rely on `Base.metadata.create_all()` for the app DB.

```bash
# Apply all migrations (Phase 0 ships no tables yet; proves wiring + creates alembic_version)
alembic upgrade head

# Preview the SQL Alembic would emit
alembic upgrade head --sql

# Roll back one step
alembic downgrade -1

# Generate a migration from model changes
alembic revision --autogenerate -m "describe change"
```

`migrations/env.py` is wired to `app.core.database.Base` and reads the DB URL from the app settings.

## API Endpoints

| Method | Path    | Description  |
| ------ | ------- | ------------ |
| GET    | `/ping` | Health check |

(Routes for auth, users, events, photos, and matches are added in later phases under `/api/v1/...`.)

## Model

Uses **insightface** model zoo with ONNX Runtime. The default model is `buffalo_l` (configurable via `MODEL_NAME` in `config.yml` / `model_name` setting):

- **RetinaFace** for face detection (ONNX)
- **ArcFace** (W600K-R50) for 512-dimensional face embeddings

**Supported image formats:** JPG, PNG, WebP, BMP, HEIC, HEIF, TIFF, GIF, AVIF

Models are downloaded automatically on first use from HuggingFace (`immich-app/buffalo_l`) to `~/.cache/immich_ml/buffalo_l/`.

---

## Legacy CLI (superseded, still works)

The original indexer/matcher workflow is being replaced. It is kept functional for reference and can be removed once the new phases cover it. It lives in `lite_ml_service/` and is still importable via `run_indexer.py` / `run_api.py`.

### Index faces

```bash
python run_indexer.py                      # index all dirs from config.yml
python run_indexer.py C:\some\photos       # index a specific directory
python run_indexer.py --add C:\new_photos  # additive mode
```

### Run the legacy API

```bash
python run_api.py
```

### Legacy endpoints

| Method | Path                   | Description                                           |
| ------ | ---------------------- | ----------------------------------------------------- |
| GET    | `/`                    | Service info                                          |
| GET    | `/ping`                | Health check                                          |
| GET    | `/scan`                | Webcam capture UI                                     |
| POST   | `/api/match`           | Match face(s) via uploaded images (up to 3, centroid) |
| POST   | `/api/match-by-path`   | Match face(s) via server-side file/directory paths    |
| GET    | `/api/download/{name}` | Download matched images as zip                        |

### Legacy config (`config.yml`)

```yaml
model_name: buffalo_l
output_root: output
qdrant_collection_name: face_embeddings

image_paths:
  - "C:\\Users\\SHO\\Pictures\\D-days\\50-days"
  # ...
```

## Extending

- **Storage**: implement `EmbeddingRepository` (`save_all`, `upsert_batch`, `delete_by_dir`, `find_similar`)
- **Multi-face centroid**: upload multiple images — embeddings are averaged into a centroid for more robust matching
- **Model**: set `model_name: buffalo_s` in `config.yml` for faster but less accurate inference
- **Embedding backend**: implement `EmbeddingProvider` to swap in a different model
