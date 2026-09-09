from __future__ import annotations

import logging
from typing import Any

import psycopg2
from pgvector.psycopg2 import register_vector

from lite_ml_service.domain.entities import BoundingBox, FaceEmbedding, MatchResult
from lite_ml_service.domain.interfaces import EmbeddingRepository

logger = logging.getLogger(__name__)

VECTOR_DIM = 512
TABLE_NAME = "face_embeddings"


class PostgresEmbeddingRepository(EmbeddingRepository):
    def __init__(self, connection_string: str) -> None:
        self._conn_string = connection_string
        self._conn: Any = None
        self._connect()
        self._ensure_setup()

    def _connect(self) -> None:
        self._conn = psycopg2.connect(self._conn_string)
        self._conn.autocommit = True
        register_vector(self._conn)
        logger.info("Connected to PostgreSQL database")

    def _ensure_setup(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
            cur.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {TABLE_NAME} (
                    id SERIAL PRIMARY KEY,
                    image_path TEXT NOT NULL,
                    embedding vector({VECTOR_DIM}) NOT NULL,
                    bbox_x1 INT NOT NULL,
                    bbox_y1 INT NOT NULL,
                    bbox_x2 INT NOT NULL,
                    bbox_y2 INT NOT NULL,
                    face_score FLOAT NOT NULL,
                    created_at TIMESTAMP DEFAULT NOW()
                )
                """
            )
            cur.execute(
                f"CREATE INDEX IF NOT EXISTS idx_{TABLE_NAME}_embedding ON {TABLE_NAME} "
                "USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
            )
        logger.info("Ensured vector extension and table exist")

    def save_all(self, embeddings: list[FaceEmbedding]) -> None:
        with self._conn.cursor() as cur:
            cur.execute(f"TRUNCATE {TABLE_NAME}")
            for emb in embeddings:
                cur.execute(
                    f"""
                    INSERT INTO {TABLE_NAME}
                        (image_path, embedding, bbox_x1, bbox_y1, bbox_x2, bbox_y2, face_score)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        emb.image_path,
                        emb.embedding,
                        emb.bbox.x1,
                        emb.bbox.y1,
                        emb.bbox.x2,
                        emb.bbox.y2,
                        emb.face_score,
                    ),
                )
        logger.info("Saved %d embeddings to PostgreSQL", len(embeddings))

    def load_all(self) -> list[FaceEmbedding]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT image_path, embedding, bbox_x1, bbox_y1, bbox_x2, bbox_y2, face_score "
                f"FROM {TABLE_NAME} ORDER BY id"
            )
            rows = cur.fetchall()

        results = [
            FaceEmbedding(
                image_path=row[0],
                embedding=list(row[1]),
                bbox=BoundingBox(x1=row[2], y1=row[3], x2=row[4], y2=row[5]),
                face_score=row[6],
            )
            for row in rows
        ]
        logger.info("Loaded %d embeddings from PostgreSQL", len(results))
        return results

    def find_similar(self, query: list[float], threshold: float) -> list[MatchResult]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT image_path, bbox_x1, bbox_y1, bbox_x2, bbox_y2,
                       1 - (embedding <=> %s::vector) AS similarity
                FROM {TABLE_NAME}
                WHERE 1 - (embedding <=> %s::vector) >= %s
                ORDER BY similarity DESC
                """,
                (query, query, threshold),
            )
            rows = cur.fetchall()

        results = [
            MatchResult(
                image_path=row[0],
                similarity=float(row[5]),
                bbox=BoundingBox(x1=row[1], y1=row[2], x2=row[3], y2=row[4]),
            )
            for row in rows
        ]
        logger.debug("Found %d matches above threshold %.2f", len(results), threshold)
        return results

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            logger.info("PostgreSQL connection closed")
