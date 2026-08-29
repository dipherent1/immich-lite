from __future__ import annotations

import logging
import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1]
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from fastapi import FastAPI

from app.api.v1.api import api_router
from app.core.config import get_settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("app")

settings = get_settings()

app = FastAPI(title=settings.app_name, version=settings.app_version)

app.include_router(api_router)


@app.get("/ping")
async def ping() -> dict[str, str]:
    return {"message": "pong"}
