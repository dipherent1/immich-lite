from fastapi import APIRouter

from app.api.v1.endpoints import auth, events, join_requests, matches, notifications, users
from app.core.config import get_settings
from app.core.rate_limit import limiter

_settings = get_settings()

api_router = APIRouter(prefix="/api/v1")

# Apply global rate limit as a default to every route registered on this router.
# Individual endpoints can override with their own @limiter.limit(...) decorator.
api_router.include_router(auth.router)
api_router.include_router(users.router)
api_router.include_router(events.router)
api_router.include_router(join_requests.router)
api_router.include_router(matches.router)
api_router.include_router(notifications.router)
