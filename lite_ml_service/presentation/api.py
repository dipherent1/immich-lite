from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

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

    @app.post("/api/match")
    async def match_face(
        file: UploadFile = File(...),
        name: str = Form(...),
    ):
        if not file.content_type or not file.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="File must be an image")

        image_bytes = await file.read()
        if not image_bytes:
            raise HTTPException(status_code=400, detail="Empty file")

        try:
            result = matcher_service.match(image_bytes, name)
            return JSONResponse(content=result)
        except Exception:
            logger.exception("Matching failed for '%s'", name)
            raise HTTPException(status_code=500, detail="Internal processing error")

    return app
