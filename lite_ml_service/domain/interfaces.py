from abc import ABC, abstractmethod

from lite_ml_service.domain.entities import FaceEmbedding, MatchResult


class EmbeddingProvider(ABC):
    @abstractmethod
    def detect_and_embed(self, image_bytes: bytes) -> list[FaceEmbedding]:
        ...


class EmbeddingRepository(ABC):
    @abstractmethod
    def save_all(self, embeddings: list[FaceEmbedding]) -> None:
        ...

    @abstractmethod
    def load_all(self) -> list[FaceEmbedding]:
        ...

    @abstractmethod
    def find_similar(self, query: list[float], threshold: float) -> list[MatchResult]:
        ...


class FileService(ABC):
    @abstractmethod
    def collect_images(self, directory: str, extensions: set[str]) -> list[str]:
        ...

    @abstractmethod
    def copy_image(self, source: str, destination: str) -> str:
        ...

    @abstractmethod
    def save_upload(self, data: bytes, path: str) -> str:
        ...

    @abstractmethod
    def ensure_directory(self, path: str) -> str:
        ...
