from __future__ import annotations

import logging
import shutil
from pathlib import Path

from lite_ml_service.domain.interfaces import FileService

logger = logging.getLogger(__name__)

_IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp",
    ".heic", ".heif", ".tiff", ".tif", ".gif", ".avif",
}


class LocalFileService(FileService):
    def collect_images(self, directory: str, extensions: set[str] | None = None) -> list[str]:
        exts = extensions or _IMAGE_EXTENSIONS
        root = Path(directory)
        if not root.exists():
            logger.warning("Directory does not exist: %s", directory)
            return []

        paths: list[str] = []
        for ext in exts:
            paths.extend(str(p) for p in root.rglob(f"*{ext}") if p.is_file())
        paths.sort()
        logger.info("Found %d images in %s", len(paths), directory)
        return paths

    def copy_image(self, source: str, destination: str) -> str:
        src = Path(source)
        dst = Path(destination)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(str(src), str(dst))
        logger.debug("Copied %s -> %s", source, destination)
        return str(dst)

    def save_upload(self, data: bytes, path: str) -> str:
        dst = Path(path)
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(data)
        logger.debug("Saved upload (%d bytes) to %s", len(data), path)
        return str(dst)

    def ensure_directory(self, path: str) -> str:
        Path(path).mkdir(parents=True, exist_ok=True)
        return path
