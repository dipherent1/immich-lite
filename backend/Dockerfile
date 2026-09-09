FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PYTHONPATH=/app/src
# Best-effort pre-cache of the face models we use (buffalo_s). The worker and the
# API share a runtime model-cache volume, so a cold build that can't reach
# HuggingFace still succeeds and the models are fetched at first run instead.
RUN python -c "from app.services.embedding_service import _ensure_model_files; _ensure_model_files('buffalo_s')" || true

ENV QDRANT_URL=http://qdrant:6333

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
