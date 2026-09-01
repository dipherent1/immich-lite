from __future__ import annotations

import logging
from pathlib import Path

from app.domain.interfaces import FileService

logger = logging.getLogger("app.file_storage")


class LocalFileService(FileService):
    """Filesystem-backed FileService.

    Photos are written under a single storage root (default `output/`) at the
    relative path returned to the caller (e.g. `photos/{event}/{photo}.jpg`).
    Everything downstream references that same relative `storage_path` — nothing
    is ever copied for matching/delivery (Phase 5 resolves the path, it doesn't
    duplicate the file). Swap this class for an object-store adapter later without
    changing the worker or the DB schema.
    """

    def __init__(self, root: str = "output") -> None:
        self._root = Path(root).resolve()

    def _resolve(self, relative: str) -> Path:
        # Prevent path traversal outside the storage root.
        target = (self._root / relative).resolve()
        if not target.is_relative_to(self._root):
            raise ValueError(f"path escapes storage root: {relative!r}")
        return target

    def ensure_directory(self, relative: str) -> str:
        d = self._resolve(relative)
        d.mkdir(parents=True, exist_ok=True)
        return relative

    def save_upload(self, data: bytes, relative: str) -> str:
        target = self._resolve(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        logger.info("saved photo to %s (%d bytes)", relative, len(data))
        return relative

    def collect_images(self, directory: str, extensions: set[str]) -> list[str]:
        d = self._resolve(directory)
        if not d.exists():
            return []
        files: list[str] = []
        for p in sorted(d.rglob("*")):
            if p.is_file() and p.suffix.lower() in extensions:
                files.append(str(p.relative_to(self._root)).replace("\\", "/"))
        return files

    def copy_image(self, source: str, destination: str) -> str:
        src = self._resolve(source)
        dst = self._resolve(destination)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        return destination

    def read(self, relative: str) -> bytes:
        return self._resolve(relative).read_bytes()

    def abs_path(self, relative: str) -> str:
        return str(self._resolve(relative))
