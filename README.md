# Immich Lite — Face Matching Microservice

A lightweight, standalone Python microservice for face embedding extraction and similarity matching, extracted from the main [Immich](https://github.com/immich-app/immich) machine-learning service. Uses the same **insightface** backend (ArcFace + RetinaFace) to keep embeddings compatible with the full Immich pipeline.

## Architecture

Clean Architecture with four layers:

```
immich-lite/
├── .env                        # Qdrant connection (secrets only)
├── config.yml                  # App config (paths, model, collection)
├── docker-compose.yml          # Qdrant + app services
├── Dockerfile                  # Python app container
├── run_indexer.py               # CLI entry point for indexing
├── run_api.py                   # Entry point for the API server
├── .venv/                       # Python 3.11 virtual environment
└── lite_ml_service/
    ├── domain/                  # Entities + interfaces
    │   ├── entities.py          # FaceEmbedding, MatchResult, config dataclasses
    │   └── interfaces.py        # ABCs (EmbeddingProvider, EmbeddingRepository, FileService)
    ├── application/             # Use-case orchestration
    │   └── services.py          # IndexerService (batch + progress bar), MatcherService
    ├── infrastructure/          # Concrete implementations
    │   ├── embedding.py         # InsightFace + ArcFace ONNX (HEIC support)
    │   ├── qdrant_storage.py    # Qdrant vector DB (md5 IDs, batch upsert)
    │   ├── storage.py           # JSON file fallback
    │   └── file_io.py           # Local file read/copy/save
    └── presentation/            # API layer
        ├── api.py               # FastAPI (match, download, Swagger)
        └── scan.html            # Webcam capture UI
```

Swapping out storage or the embedding backend only requires implementing the corresponding ABC.

## Requirements

- Python 3.11
- [Docker](https://docs.docker.com/engine/install/) and Docker Compose
- ~16 MB disk for the ONNX model (downloaded automatically from HuggingFace)

## Quick Start (Docker)

One command to run everything:

```bash
docker compose up -d
```

This starts:
- **Qdrant** vector database on port 6333 (REST) and 6334 (gRPC)
- **Immich Lite** API server on port 8000

Then follow the [Indexing](#step-1-index-faces) and [Matching](#step-2-match-faces) sections below.

## Local Development Setup

### 1. Install dependencies

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r lite_ml_service\requirements.txt
```

(Dependencies are already installed in the shipped `.venv`.)

### 2. Start Qdrant

```bash
docker compose up -d qdrant
```

### 3. Configure environment

**`.env`** — deployment secrets (Qdrant connection):

```env
QDRANT_URL=http://localhost:6333
```

**`config.yml`** — app configuration (paths, model, collection):

```yaml
model_name: buffalo_l
output_root: output
qdrant_collection_name: face_embeddings

image_paths:
  - "C:\\Users\\SHO\\Pictures\\D-days\\50-days"
  - "C:\\Users\\SHO\\Pictures\\D-days\\adama"
  - "C:\\Users\\SHO\\Pictures\\D-days\\culture day"
  - "C:\\Users\\SHO\\Pictures\\D-days\\grad"
  - "C:\\Users\\SHO\\Pictures\\D-days\\jema"
  - "C:\\Users\\SHO\\Pictures\\D-days\\kuriftu"
  - "C:\\Users\\SHO\\Pictures\\D-days\\mechanical+yub"
  - "C:\\Users\\SHO\\Pictures\\D-days\\oldies"
  - "C:\\Users\\SHO\\Pictures\\D-days\\photo shoot"
```

| File | Purpose |
|---|---|
| `.env` | Secrets and deployment-specific overrides (`QDRANT_URL`, `QDRANT_API_KEY`) |
| `config.yml` | App config (image paths, model name, output root, collection name) |

Environment variables in `.env` always override values in `config.yml`.

## How to Use

### Step 1: Index faces

#### Option A: Use image_paths from config.yml

If `image_paths` is set in `config.yml`, just run:

```bash
python run_indexer.py
```

It will index all directories listed in `config.yml` with a progress bar.

#### Option B: Pass directories as arguments

```bash
python run_indexer.py C:\Users\SHO\Pictures\D-days\50-days C:\Users\SHO\Pictures\D-days\adama
```

#### Option C: Additive mode (don't overwrite existing)

```bash
python run_indexer.py --add C:\Users\SHO\Pictures\new_folder
```

This adds new faces without clearing existing embeddings. Safe to run multiple times.

| Flag | Default | Description |
|---|---|---|
| `--add` | _(off)_ | Additive mode: keep existing embeddings, only add/update |
| `--embeddings <path>` | `embeddings.json` | Fallback path when Qdrant is unused |
| `--threshold <float>` | `0.5` | Face detection confidence threshold |

**Indexing modes:**

| Command | Behavior |
|---|---|
| `python run_indexer.py` | Re-index all dirs from config.yml (clears each dir's old embeddings first) |
| `python run_indexer.py --add <dir>` | Add only — don't touch existing data |
| `python run_indexer.py <dir>` | Re-index just that dir (clears its old embeddings) |

Progress bar shows images processed, faces found, and skipped count. Embeddings are processed in batches of 32 and upserted in batches of 100 to avoid timeouts.

### Step 2: Start the API server

```bash
python run_api.py
```

| Flag | Default | Description |
|---|---|---|
| `--embeddings <path>` | `embeddings.json` | Fallback path when Qdrant is unused |
| `--output <dir>` | `output` | Root directory for match results |
| `--threshold <float>` | `0.5` | Cosine similarity threshold for matches |
| `--host <host>` | `0.0.0.0` | Bind address |
| `--port <port>` | `8000` | Port |

### Step 3: Match faces

#### Option A: Upload images (up to 3 files)

```bash
curl -X POST http://localhost:8000/api/match \
  -F "file1=@front.jpg" \
  -F "file2=@left.jpg" \
  -F "file3=@right.jpg" \
  -F "name=person_name"
```

#### Option B: Pass file paths on the server

```bash
curl -X POST http://localhost:8000/api/match-by-path \
  -H "Content-Type: application/json" \
  -d '{"paths": ["C:/photos/front.jpg", "C:/photos/left.jpg"], "name": "person_name"}'
```

#### Option C: Use the webcam UI

Open [http://localhost:8000/scan](http://localhost:8000/scan) in your browser. It guides you through capturing front, left, and right photos, which are automatically matched.

### Step 4: Download results

After matching, download all matched images (plus source) as a zip file:

```bash
curl -O http://localhost:8000/api/download/person_name
```

The zip is also saved at `output/<name>/matches/<name>.zip`.

### How centroid matching works

When uploading multiple images of the same person, the service:

1. Detects all faces in every uploaded image
2. Averages all 512-dimension embeddings into a single **centroid vector**
3. Matches the centroid against all indexed embeddings (cosine similarity)
4. This smooths out lighting, pose, and expression variations

## Example Response

```json
{
  "name": "person_name",
  "source_image": "output/person_name/source/source.jpg",
  "zip_file": "output/person_name/matches/person_name.zip",
  "matches": [
    {
      "image_path": "C:/photos/group.jpg",
      "copied_to": "output/person_name/matches/group.jpg",
      "similarity": 0.9214,
      "bounding_box": { "x1": 120, "y1": 80, "x2": 200, "y2": 260 }
    }
  ],
  "matched_count": 1
}
```

## API Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/` | Service info |
| GET | `/ping` | Health check |
| GET | `/scan` | Webcam capture UI |
| POST | `/api/match` | Match face(s) via uploaded images (up to 3, centroid) |
| POST | `/api/match-by-path` | Match face(s) via server-side file/directory paths |
| GET | `/api/download/{name}` | Download matched images as zip |

## Model

Uses **insightface** model zoo with ONNX Runtime. The default model is `buffalo_l` (configurable via `MODEL_NAME` in `config.yml`):

- **RetinaFace** for face detection (ONNX)
- **ArcFace** (W600K-R50) for 512-dimensional face embeddings

**Supported image formats:** JPG, PNG, WebP, BMP, HEIC, HEIF, TIFF, GIF, AVIF

Models are downloaded automatically on first use from HuggingFace (`immich-app/buffalo_l`) to `~/.cache/immich_ml/buffalo_l/`.

## Extending

- **Storage**: Implement `EmbeddingRepository` (`save_all`, `upsert_batch`, `delete_by_dir`, `find_similar`)
- **Multi-face centroid**: Upload multiple images — embeddings are averaged into a centroid for more robust matching
- **Model**: Set `model_name: buffalo_s` in `config.yml` for faster but less accurate inference
- **Embedding backend**: Implement `EmbeddingProvider` to swap in a different model
