# Legacy

Retired code from before the phased rewrite. **Do not run or modify anything in
this directory** — it is kept for reference and is fully recoverable as needed.

## What's here

| Path | What it was |
|---|---|
| `lite_ml_service/` | The original standalone face-matching package (its own `domain/`, `infrastructure/`, `application/`, `presentation/` layers, file + Qdrant + Postgres storage backend, CLI-driven indexer and matcher). |
| `run_api.py` | CLI entry point for the legacy matching API server. |
| `run_indexer.py` | CLI entry point for the legacy directory indexer. |
| `config.yml` | Legacy YAML config (`model_name`, `output_root`, `qdrant_collection_name`, `image_paths`). |

## Why it's archived

The canonical application lives in `backend/src/app/` (FastAPI + Alembic + Postgres +
Qdrant + RQ worker, Phase 0–6 complete). The legacy package was superseded by that
code and nothing in `backend/src` imports it. The old workflows it served (offline
directory indexing → JSON/Qdrant storage → `/api/match` webcam matching) are replaced
by the user-profile enrollment, event photo ingestion, and attendee-scoped matching
pipeline.

The useful logic it carried — InsightFace/ArcFace embedding, centroid averaging,
Qdrant matching — was **relocated, not rewritten**, into
`backend/src/app/services/embedding_service.py` and `backend/src/app/core/vector_db.py`
during Phase 0, so no unique code was lost by retiring this package.

## Recovering

Everything here is tracked by git. To bring any piece back, check out the revision
just before the archive commit (see `git log -- legacy/`), or copy a file out of
git history directly:

```bash
git show <commit>:legacy/lite_ml_service/main.py > /tmp/main.py
```