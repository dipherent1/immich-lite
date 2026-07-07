FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0 \
    wget \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY lite_ml_service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN python -c "from lite_ml_service.infrastructure.embedding import _ensure_model_files; _ensure_model_files('buffalo_l')"

ENV QDRANT_URL=http://qdrant:6333

EXPOSE 8000

CMD ["python", "run_api.py"]
