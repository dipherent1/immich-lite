# Immich Lite — Face Matching Microservice

A lightweight, standalone Python microservice for face embedding extraction and similarity matching, extracted from the main [Immich](https://github.com/immich-app/immich) machine-learning service. Uses the same **insightface** backend (ArcFace + RetinaFace) to keep embeddings compatible with the full Immich pipeline.

## Architecture

Clean Architecture with four layers:

```
immich-lite/
├── .env                       # DATABASE_URL for PostgreSQL (optional)
├── run_indexer.py              # CLI entry point for indexing
├── run_api.py                  # Entry point for the API server
├── .venv/                      # Python 3.11 virtual environment
└── lite_ml_service/
    ├── domain/                 # Entities + interfaces
    │   ├── entities.py         # FaceEmbedding, MatchResult, config dataclasses
    │   └── interfaces.py       # ABCs (EmbeddingProvider, EmbeddingRepository, FileService)
    ├── application/            # Use-case orchestration
    │   └── services.py         # IndexerService, MatcherService
    ├── infrastructure/         # Concrete implementations
    │   ├── embedding.py        # InsightFace-based face detection + embedding
    │   ├── storage.py          # JSON file repository (cosine similarity search)
    │   ├── postgres_storage.py # pgvector repository (PostgreSQL)
    │   └── file_io.py          # Local file read/copy/save
    └── presentation/           # API layer
        └── api.py              # FastAPI app with POST /api/match
```

Swapping out storage or the embedding backend only requires implementing the corresponding ABC.

## Requirements

- Python 3.11
- ~200 MB disk for the insightface model (downloaded on first use)
- PostgreSQL 14+ with `vector` extension (optional — falls back to JSON file)

## Setup

```bash
# From the immich-lite directory
python -m venv .venv
.venv\Scripts\activate.bat
.venv\Scripts\pip install -r lite_ml_service\requirements.txt
```

(Dependencies are already installed in the shipped `.venv`.)

### PostgreSQL storage (optional)

Create a `.env` file at the project root with your connection string:

```
DATABASE_URL=postgresql://postgres:postgres@localhost:5432/immich?sslmode=prefer
```

On startup the service checks for `DATABASE_URL`. If set and reachable, it uses pgvector; otherwise it falls back to JSON file storage. The table and ivfflat index are created automatically on first use.

## Usage

### 1. Index faces from a directory

```bash
python run_indexer.py C:\Users\SHO\Pictures\immich
```

This scans `path\to\photos` recursively for images, detects faces, extracts 512-dim ArcFace embeddings, and saves them to `embeddings.json`.

| Flag                  | Default           | Description                         |
| --------------------- | ----------------- | ----------------------------------- |
| `--embeddings <path>` | `embeddings.json` | Where to store the embedding index  |
| `--threshold <float>` | `0.5`             | Face detection confidence threshold |

### 2. Start the matching API

```bash
python run_api.py
```

| Flag                  | Default           | Description                             |
| --------------------- | ----------------- | --------------------------------------- |
| `--embeddings <path>` | `embeddings.json` | Path to the pre-built embedding index   |
| `--output <dir>`      | `output`          | Root directory for match results        |
| `--threshold <float>` | `0.5`             | Cosine similarity threshold for matches |
| `--host <host>`       | `0.0.0.0`         | Bind address                            |
| `--port <port>`       | `8000`            | Port                                    |

### 3. Match a face via API

```bash
curl -X POST http://localhost:8000/api/match \
  -F "file=@query.jpg" \
  -F "name=person_name"
```

The service will:

1. Save the uploaded image to `output/person_name/source/`
2. Extract the face embedding from it
3. Compare against all indexed embeddings (cosine similarity)
4. Copy matching source images to `output/person_name/matches/`
5. Return a JSON response with paths and similarity scores

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

| Method | Path         | Description                                  |
| ------ | ------------ | -------------------------------------------- |
| GET    | `/`          | Service info                                 |
| GET    | `/ping`      | Health check (returns `{"message": "pong"}`) |
| POST   | `/api/match` | Match a face against the indexed gallery     |

## Model

Uses **insightface** with the `buffalo_s` model pack, which includes:

- **RetinaFace** for face detection
- **ArcFace** (W600K-R50) for 512-dimensional face embeddings

The model is downloaded automatically on first use to `~/.insightface/models/`.

## Extending

- **Storage**: Implement `EmbeddingRepository` to use a vector DB (e.g., pgvector, Chroma, Qdrant)
- **Multi-face**: The API currently uses the first detected face; `detect_and_embed()` returns all faces — extend `MatcherService.match()` to iterate over all
- **Embedding backend**: Implement `EmbeddingProvider` to swap in a different model
