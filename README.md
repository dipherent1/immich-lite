# Immich Lite — Face Matching Microservice

A lightweight, standalone Python microservice for face embedding extraction and similarity matching, extracted from the main [Immich](https://github.com/immich-app/immich) machine-learning service. Uses the same **insightface** backend (ArcFace + RetinaFace) to keep embeddings compatible with the full Immich pipeline.

## Architecture

Clean Architecture with four layers:

```
immich-lite/
├── .env                        # Qdrant connection config + model selection
├── docker-compose.yml          # Qdrant vector database service
├── run_indexer.py               # CLI entry point for indexing
├── run_api.py                   # Entry point for the API server
├── .venv/                       # Python 3.11 virtual environment
└── lite_ml_service/
    ├── domain/                  # Entities + interfaces
    │   ├── entities.py          # FaceEmbedding, MatchResult, config dataclasses
    │   └── interfaces.py        # ABCs (EmbeddingProvider, EmbeddingRepository, FileService)
    ├── application/             # Use-case orchestration
    │   └── services.py          # IndexerService, MatcherService (centroid matching)
    ├── infrastructure/          # Concrete implementations
    │   ├── embedding.py         # InsightFace detection + ArcFace ONNX embedding
    │   ├── qdrant_storage.py    # Qdrant vector DB repository (cosine distance)
    │   ├── storage.py           # JSON file fallback repository
    │   └── file_io.py           # Local file read/copy/save
    └── presentation/            # API layer
        ├── api.py               # FastAPI app (match, match-by-path, Swagger)
        └── scan.html            # Webcam capture UI (front/left/right)
```

Swapping out storage or the embedding backend only requires implementing the corresponding ABC.

## Requirements

- Python 3.11
- ~16 MB disk for the ONNX model (downloaded on first use from HuggingFace)
- [Docker](https://docs.docker.com/engine/install/) for the Qdrant vector database

## Setup

```bash
# From the immich-lite directory
python -m venv .venv
.venv\Scripts\activate.bat
.venv\Scripts\pip install -r lite_ml_service\requirements.txt
```

(Dependencies are already installed in the shipped `.venv`.)

### Qdrant vector database

Start Qdrant via Docker Compose:

```bash
docker compose up -d
```

This runs Qdrant on port 6333 (REST) and 6334 (gRPC) with a persistent named volume.

### Configuration

Create a `.env` file at the project root:

```env
QDRANT_URL=http://localhost:6333
QDRANT_COLLECTION_NAME=face_embeddings
MODEL_NAME=buffalo_l
```

| Variable                  | Default                | Description                             |
| ------------------------- | ---------------------- | --------------------------------------- |
| `QDRANT_URL`              | `http://localhost:6333`| Qdrant server REST endpoint             |
| `QDRANT_API_KEY`          | _(none)_               | Optional API key for authenticated Qdrant|
| `QDRANT_COLLECTION_NAME`  | `face_embeddings`      | Qdrant collection name                  |
| `MODEL_NAME`              | `buffalo_l`            | InsightFace model (`buffalo_s` or `buffalo_l`) |

On startup the service checks for `QDRANT_URL`. If set and reachable, it uses Qdrant; otherwise it falls back to JSON file storage (`embeddings.json`). The collection with COSINE distance and 512-dim vectors is created automatically.

## Usage

### 1. Index faces from a directory

```bash
python run_indexer.py C:\Users\SHO\Pictures\immich
```

This scans `path\to\photos` recursively for images, detects faces, extracts 512-dim ArcFace embeddings, and stores them in Qdrant (or `embeddings.json` as fallback).

| Flag                  | Default           | Description                         |
| --------------------- | ----------------- | ----------------------------------- |
| `--embeddings <path>` | `embeddings.json` | Fallback path when Qdrant is unused |
| `--threshold <float>` | `0.5`             | Face detection confidence threshold |

### 2. Start the matching API

```bash
python run_api.py
```

| Flag                  | Default           | Description                             |
| --------------------- | ----------------- | --------------------------------------- |
| `--embeddings <path>` | `embeddings.json` | Fallback path when Qdrant is unused     |
| `--output <dir>`      | `output`          | Root directory for match results        |
| `--threshold <float>` | `0.5`             | Cosine similarity threshold for matches |
| `--host <host>`       | `0.0.0.0`         | Bind address                            |
| `--port <port>`       | `8000`            | Port                                    |

### 3. Match a face via API

#### Upload images (up to 3 files)

```bash
curl -X POST http://localhost:8000/api/match \
  -F "file1=@front.jpg" \
  -F "file2=@left.jpg" \
  -F "file3=@right.jpg" \
  -F "name=person_name"
```

#### Pass file paths directly

```bash
curl -X POST http://localhost:8000/api/match-by-path \
  -H "Content-Type: application/json" \
  -d '{"paths": ["C:/photos/front.jpg", "C:/photos/left.jpg"], "name": "person_name"}'
```

Accepts a directory path — will scan all images inside it.

#### How centroid matching works

When uploading multiple images of the same person, the service:

1. Detects all faces in every uploaded image
2. Averages all 512-dimension embeddings into a single **centroid vector**
3. Matches the centroid against all indexed embeddings (cosine similarity)
4. This smooths out lighting, pose, and expression variations

#### Webcam capture UI

Open `http://localhost:8000/scan` in your browser to use the webcam-based capture interface. Guides you through:
- **Front** — face the camera
- **Left** — turn head slightly left  
- **Right** — turn head slightly right

Captures are automatically sent to the `/api/match` endpoint for centroid matching.

#### Example response

```json
{
  "name": "person_name",
  "source_image": "output/person_name/source/source.jpg",
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

| Method | Path                | Description                                              |
| ------ | ------------------- | -------------------------------------------------------- |
| GET    | `/`                 | Service info                                             |
| GET    | `/ping`             | Health check (returns `{"message": "pong"}`)             |
| GET    | `/scan`             | Webcam capture UI for face enrollment                    |
| POST   | `/api/match`        | Match face(s) via uploaded images (up to 3, centroid)    |
| POST   | `/api/match-by-path`| Match face(s) via server-side file/directory paths       |

## Model

Uses **insightface** model zoo with ONNX Runtime. The default model is `buffalo_l` (configurable via `MODEL_NAME` env var):

- **RetinaFace** for face detection (localized ONNX model)
- **ArcFace** (W600K-R50) for 512-dimensional face embeddings

Models are downloaded automatically on first use from HuggingFace (`immich-app/buffalo_l`) to `~/.cache/immich_ml/buffalo_l/`. You can also place a pre-downloaded `{model_name}.zip` at `C:\Users\SHO\Downloads\Setups/{model_name}.zip` to skip the download.

## Extending

- **Storage**: Implement `EmbeddingRepository` to use a different vector DB
- **Multi-face centroid**: Upload multiple images — embeddings are averaged into a centroid for more robust matching
- **Model**: Set `MODEL_NAME=buffalo_s` in `.env` for faster but less accurate inference
- **Embedding backend**: Implement `EmbeddingProvider` to swap in a different model
