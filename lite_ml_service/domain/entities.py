from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class BoundingBox:
    x1: int
    y1: int
    x2: int
    y2: int


@dataclass
class FaceEmbedding:
    image_path: str
    embedding: list[float]
    bbox: BoundingBox
    face_score: float


@dataclass
class MatchResult:
    image_path: str
    similarity: float
    bbox: BoundingBox


@dataclass
class IndexerConfig:
    source_dir: Path
    embeddings_path: Path
    detection_threshold: float = 0.5
    image_extensions: set[str] = field(default_factory=lambda: {".jpg", ".jpeg", ".png", ".webp", ".bmp"})


@dataclass
class MatcherConfig:
    indexed_embeddings_path: Path
    output_root: Path
    similarity_threshold: float = 0.5
    detection_threshold: float = 0.5
