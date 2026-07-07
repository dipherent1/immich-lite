from __future__ import annotations

import logging
from pathlib import Path

from fastapi import Body, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from lite_ml_service.application.services import MatcherService

logger = logging.getLogger(__name__)


def create_app(matcher_service: MatcherService) -> FastAPI:
    app = FastAPI(title="Immich Lite - Face Matching")

    @app.get("/ping")
    async def ping():
        return {"message": "pong"}

    @app.get("/")
    async def root():
        return {"service": "Immich Lite Face Matching", "version": "1.0.0"}

    @app.get("/scan", response_class=HTMLResponse)
    async def scan_page():
        html_path = Path(__file__).parent / "scan.html"
        return html_path.read_text(encoding="utf-8")

    @app.post("/api/match")
    async def match_face(
        file1: UploadFile = File(..., description="First image of the target person (required)"),
        file2: UploadFile = File(None, description="Second image (optional, improves accuracy)"),
        file3: UploadFile = File(None, description="Third image (optional, improves accuracy)"),
        name: str = Form(...),
    ):
        files = [f for f in (file1, file2, file3) if f is not None]
        image_bytes_list: list[bytes] = []
        for f in files:
            if not f.content_type or not f.content_type.startswith("image/"):
                raise HTTPException(status_code=400, detail=f"'{f.filename}' is not an image")
            data = await f.read()
            if not data:
                raise HTTPException(status_code=400, detail=f"'{f.filename}' is empty")
            image_bytes_list.append(data)

        try:
            result = matcher_service.match_multiple(image_bytes_list, name)
            return JSONResponse(content=result)
        except Exception:
            logger.exception("Matching failed for '%s'", name)
            raise HTTPException(status_code=500, detail="Internal processing error")

    @app.post("/api/match-by-path")
    async def match_by_path(
        paths: list[str] = Body(..., description="Full file paths to images of the target person"),
        name: str = Body(..., description="Person's name for output directory"),
    ):
        image_bytes_list: list[bytes] = []
        for p in paths:
            path = Path(p)
            if not path.exists():
                raise HTTPException(status_code=404, detail=f"Path not found: {p}")

            if path.is_dir():
                image_files = sorted(
                    f for f in path.iterdir()
                    if f.is_file() and f.suffix.lower() in {
                        ".jpg", ".jpeg", ".png", ".webp", ".bmp",
                        ".heic", ".heif", ".tiff", ".tif", ".gif", ".avif",
                    }
                )
                if not image_files:
                    raise HTTPException(status_code=400, detail=f"No image files found in directory: {p}")
                for img_file in image_files:
                    try:
                        image_bytes_list.append(img_file.read_bytes())
                    except Exception as e:
                        raise HTTPException(status_code=500, detail=f"Failed to read {img_file}: {e}")
                continue

            ext = path.suffix.lower()
            if ext not in {".jpg", ".jpeg", ".png", ".webp", ".bmp",
                           ".heic", ".heif", ".tiff", ".tif", ".gif", ".avif"}:
                raise HTTPException(status_code=400, detail=f"Unsupported file format: {p} (got '{ext}')")

            try:
                image_bytes_list.append(path.read_bytes())
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Failed to read {p}: {e}")

        try:
            result = matcher_service.match_multiple(image_bytes_list, name)
            return JSONResponse(content=result)
        except Exception:
            logger.exception("Matching failed for '%s'", name)
            raise HTTPException(status_code=500, detail="Internal processing error")

    @app.get("/api/download/{name}")
    async def download_zip(name: str):
        import os
        output_root = os.environ.get("OUTPUT_ROOT", "output")
        zip_path = Path(output_root) / name / "matches" / f"{name}.zip"
        if not zip_path.exists():
            raise HTTPException(status_code=404, detail=f"No results found for '{name}'")
        return FileResponse(
            path=str(zip_path),
            media_type="application/zip",
            filename=f"{name}.zip",
        )

    return app
