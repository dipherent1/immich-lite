# Notifications & Join Requests — Implementation Plan

> ✅ **COMPLETE** — all phases (A–I) implemented and verified end-to-end against the rebuilt Docker stack. See the "Notifications & Join Requests" section in [PROGRESS.md](PROGRESS.md) for what was done and the verification results.

## Overview

Adds three capabilities:
1. **Join request flow** — search → request → owner approves/denies (share links still instant-join)
2. **Notification system** — persistent notifications in Postgres, real-time delivery via SSE
3. **Notification UI** — bell + dropdown in dashboard header, full `/notifications` page

Photo processing status live-update is deferred (left as-is with manual refresh).

---

## Phase A — Models & Migration

### New models

**`src/app/models/join_request.py`**
```python
class JoinRequest(SQLModel, table=True):
    __tablename__ = "join_requests"
    id: str (UUID PK)
    event_id: str (FK → events.id, indexed)
    requester_id: str (FK → users.id, indexed)
    status: str  # "pending" | "approved" | "denied"
    created_at: datetime
    resolved_at: datetime | None
```
- Unique constraint on `(event_id, requester_id)` where `status = 'pending'` (partial index) — prevents duplicate pending requests.
- When approved → `EventAttendee` row is created, request status set to `approved`.
- When denied → status set to `denied`, requester notified.

**`src/app/models/notification.py`**
```python
class Notification(SQLModel, table=True):
    __tablename__ = "notifications"
    id: str (UUID PK)
    user_id: str (FK → users.id, indexed)
    type: str  # "join_request" | "join_approved" | "join_denied" | "photo_matched" | "photo_processed"
    title: str
    body: str
    subject_type: str | None  # "event" | "photo" | "join_request"
    subject_id: str | None    # ID of the related entity
    is_read: bool (default False)
    created_at: datetime
```

### Migration

**`migrations/versions/0005_create_join_requests_and_notifications.py`**
- Creates `join_requests` table (FKs, indexes, partial unique index on pending requests).
- Creates `notifications` table (FK, indexes on `user_id` + `is_read`).
- Standard apply/rollback verification.

### Register in `models/__init__.py`

Add `JoinRequest` and `Notification` to `__all__`.

---

## Phase B — Repositories

### `src/app/repositories/join_request_repository.py`

Methods:
- `create(event_id, requester_id) -> JoinRequest` — inserts with `status="pending"`, raises on duplicate pending (catches IntegrityError).
- `get_by_id(id) -> JoinRequest | None`
- `get_pending_for_event(event_id) -> list[JoinRequest]` — pending requests for an event, newest first, joined with User to get `display_name`/`email`.
- `resolve(id, status) -> JoinRequest` — sets `status` + `resolved_at`, returns the updated request.
- `get_by_event_and_requester(event_id, requester_id) -> JoinRequest | None` — check existing request.

### `src/app/repositories/notification_repository.py`

Methods:
- `create(user_id, type, title, body, subject_type=None, subject_id=None) -> Notification`
- `list_for_user(user_id, offset, limit) -> tuple[list[Notification], bool]` — newest first, paginated.
- `unread_count(user_id) -> int`
- `mark_read(id, user_id) -> None` — marks a single notification read (validates ownership).
- `mark_all_read(user_id) -> None` — marks all of a user's notifications read.

---

## Phase C — Services

### `src/app/services/notification_service.py`

Owns notification business logic. Called by other services (not directly by routers for create).

Methods:
- `create(user_id, type, title, body, subject_type, subject_id) -> Notification` — writes to DB, then publishes to Redis pub/sub for SSE delivery.
- `list_for_user(user_id, offset, limit)` — delegates to repo.
- `unread_count(user_id)` — delegates to repo.
- `mark_read(notification_id, user_id)` — delegates to repo.
- `mark_all_read(user_id)` — delegates to repo.

Redis pub/sub: on `create`, publishes a JSON message to channel `notifications:{user_id}` with the notification data. The SSE manager (started at app startup) subscribes and relays to connected clients.

### `src/app/services/join_request_service.py`

Owns join request business logic.

Methods:
- `request_to_join(event_id, requester_id) -> JoinRequest`
  - Validates event exists (404), is active (410), requester isn't already an attendee (400), no existing pending request (409).
  - Creates the request.
  - Notifies the event owner via `NotificationService` (type `join_request`).
- `list_pending(event_id, owner_id) -> list[JoinRequest]`
  - Validates the caller is the event owner (403).
  - Returns pending requests with requester info.
- `approve(request_id, owner_id) -> JoinRequest`
  - Validates caller is event owner (403), request is pending (400).
  - Sets status to `approved`, creates `EventAttendee` row.
  - Notifies the requester (type `join_approved`).
- `deny(request_id, owner_id) -> JoinRequest`
  - Validates caller is event owner (403), request is pending (400).
  - Sets status to `denied`.
  - Notifies the requester (type `join_denied`).

---

## Phase D — SSE Manager & Endpoint

### `src/app/core/sse.py` — SSE connection manager

```python
class SSEManager:
    """Manages per-user SSE connections and Redis pub/sub relay."""

    def __init__(self):
        self._clients: dict[str, list[asyncio.Queue]] = {}  # user_id -> list of queues
        self._redis_subscribed = False

    async def connect(self, user_id: str) -> AsyncGenerator:
        """Yields SSE events for this user. Handles subscribe/unsubscribe."""
        queue = asyncio.Queue()
        self._clients.setdefault(user_id, []).append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            self._clients[user_id].remove(queue)
            if not self._clients[user_id]:
                del self._clients[user_id]

    def dispatch(self, user_id: str, data: str):
        """Send an event to all connected clients of a user."""
        for queue in self._clients.get(user_id, []):
            queue.put_nowait(data)

sse_manager = SSEManager()  # module-level singleton
```

### Redis pub/sub listener (started in `main.py` lifespan)

A background task that subscribes to `notifications:*` channels in Redis and calls `sse_manager.dispatch()` when a message arrives. Uses `redis.asyncio` for non-blocking.

### `src/app/api/v1/endpoints/notifications.py`

Endpoints:
- `GET /api/v1/notifications/stream` — SSE endpoint. Returns `StreamingResponse(media_type="text/event-stream")`. Calls `sse_manager.connect(current_user.id)`. Keeps connection alive with periodic `:keepalive\n\n` comments.
- `GET /api/v1/notifications?offset=&limit=` — paginated notification list (for the full page and initial dropdown load).
- `GET /api/v1/notifications/unread-count` — returns `{"count": N}` (for the badge).
- `PATCH /api/v1/notifications/{id}/read` — mark one as read.
- `PATCH /api/v1/notifications/read-all` — mark all as read.

---

## Phase E — Join Request Endpoints

### `src/app/api/v1/endpoints/join_requests.py`

- `POST /api/v1/events/{event_id}/join-request` — request to join (any authenticated user with a face profile).
- `GET /api/v1/events/{event_id}/join-requests` — list pending requests (owner only).
- `PATCH /api/v1/events/{event_id}/join-requests/{request_id}/approve` — approve.
- `PATCH /api/v1/events/{event_id}/join-requests/{request_id}/deny` — deny.

### Wire into `api/v1/api.py`

Add the `join_requests` and `notifications` routers.

### DI in `api/deps.py`

Add factories:
- `get_notification_repository`
- `get_notification_service` (takes notification repo)
- `get_join_request_repository`
- `get_join_request_service` (takes join request repo, event repo, notification service)

---

## Phase F — Schemas

### `src/app/schemas/join_request.py`

```python
class JoinRequestResponse(BaseModel):
    id: str
    event_id: str
    requester_id: str
    requester_name: str  # from joined User
    status: str
    created_at: datetime
    resolved_at: datetime | None
```

### `src/app/schemas/notification.py`

```python
class NotificationResponse(BaseModel):
    id: str
    type: str
    title: str
    body: str
    subject_type: str | None
    subject_id: str | None
    is_read: bool
    created_at: datetime

class NotificationListResponse(BaseModel):
    items: list[NotificationResponse]
    has_more: bool
    next_offset: int

class UnreadCountResponse(BaseModel):
    count: int
```

### Add to `schemas/__init__.py`

Register new schemas.

---

## Phase G — Worker Integration

### `src/app/workers/photo_worker.py`

After `matching.match_photo(photo)` completes, publish a notification event to Redis for each matched user:

```python
from app.core.notification_publisher import publish_notification

for match_user_id in matched_user_ids:
    publish_notification(
        user_id=match_user_id,
        type="photo_matched",
        title="New match found!",
        body=f"A photo in {event_name} matches your face.",
        subject_type="photo",
        subject_id=photo.id,
    )
```

### `src/app/core/notification_publisher.py` (new)

Thin helper that publishes a notification JSON message to a Redis pub/sub channel. The API server's SSE listener picks it up and persists + delivers.

```python
def publish_notification(**kwargs):
    """Publish a notification event to Redis for the API server to persist + deliver."""
    import json
    from redis import Redis
    from app.core.config import get_settings
    conn = Redis.from_url(get_settings().redis_url)
    conn.publish("notifications:events", json.dumps(kwargs))
```

---

## Phase H — Frontend

### `frontend/src/lib/notifications.ts` — SSE hook

```typescript
export function useNotifications() {
  // Connects to /api/v1/notifications/stream
  // Returns: { notifications, unreadCount, markRead, markAllRead }
  // Auto-reconnects on disconnect.
}
```

### `frontend/src/components/NotificationBell.tsx`

- Bell icon with unread count badge (red circle).
- Click toggles a dropdown showing the 10 most recent notifications.
- Each notification has: icon by type, title, body, time ago, read/unread styling.
- Click on a notification navigates to the subject (event page, etc.) and marks it read.
- "Mark all read" button.
- "View all notifications" link to `/notifications`.

### `frontend/src/components/NotificationsPage.tsx`

- Full page listing all notifications, paginated.
- Same notification rendering as the dropdown but with more detail.
- "Mark all read" button at the top.

### `frontend/src/app/notifications/page.tsx`

- `RequireAuth`-wrapped route rendering `NotificationsPage`.

### `frontend/src/app/dashboard/page.tsx`

- Add `<NotificationBell />` in the dashboard header area (next to the user info).

### `frontend/src/components/EventsView.tsx`

- **Search results**: Replace the "Requesting to join is coming soon" note with a **"Request to join"** button. On click, POST to `/events/{id}/join-request` and show success/pending state.
- **Your events (owner view)**: Add a "Pending requests (N)" badge/count. Click to expand a list with Approve/Deny buttons per request.

### `frontend/src/lib/api.ts`

Add new types and functions:
- `JoinRequestResponse`, `NotificationResponse`, `NotificationListResponse`, `UnreadCountResponse`
- `requestToJoin(eventId)`, `listPendingRequests(eventId)`, `approveRequest(eventId, requestId)`, `denyRequest(eventId, requestId)`
- `getNotifications(offset, limit)`, `getUnreadCount()`, `markNotificationRead(id)`, `markAllNotificationsRead()`

### `frontend/src/app/events/[id]/page.tsx`

- For the event owner, show a "Join requests" section below the attendee list.
- Lists pending requests with Approve/Deny buttons.
- Refreshes after each action.

---

## Phase I — Verification

### Backend
- `alembic upgrade head` / `alembic downgrade` apply cleanly.
- POST join request → owner sees it in `GET /events/{id}/join-requests`.
- Approve → requester becomes attendee, gets notification.
- Deny → requester gets denial notification.
- Share link → instant join (unchanged).
- SSE stream delivers notifications in real-time.
- `GET /notifications` returns paginated list.
- `PATCH /notifications/{id}/read` marks read.
- Worker match → matched user gets notification via SSE.

### Frontend
- `npm run build` passes.
- Search → "Request to join" → owner sees pending request → approve → requester can now access event.
- Notification bell shows unread count, dropdown shows notifications.
- `/notifications` page shows full history.

---

## File change summary

### New files (backend)
- `src/app/models/join_request.py`
- `src/app/models/notification.py`
- `src/app/repositories/join_request_repository.py`
- `src/app/repositories/notification_repository.py`
- `src/app/services/join_request_service.py`
- `src/app/services/notification_service.py`
- `src/app/core/sse.py`
- `src/app/core/notification_publisher.py`
- `src/app/api/v1/endpoints/join_requests.py`
- `src/app/api/v1/endpoints/notifications.py`
- `migrations/versions/0005_create_join_requests_and_notifications.py`

### New files (frontend)
- `frontend/src/lib/notifications.ts` (SSE hook)
- `frontend/src/components/NotificationBell.tsx`
- `frontend/src/components/NotificationsPage.tsx`
- `frontend/src/app/notifications/page.tsx`

### Modified files (backend)
- `src/app/models/__init__.py` — register new models
- `src/app/schemas/__init__.py` — register new schemas
- `src/app/api/v1/api.py` — add new routers
- `src/app/api/deps.py` — add new DI factories
- `src/app/main.py` — start SSE Redis listener on startup
- `src/app/workers/photo_worker.py` — publish match notifications
- `src/app/services/matching_service.py` — return matched user IDs

### Modified files (frontend)
- `frontend/src/lib/api.ts` — new types + functions
- `frontend/src/components/EventsView.tsx` — request-to-join button, pending requests for owners
- `frontend/src/app/dashboard/page.tsx` — add NotificationBell
- `frontend/src/app/events/[id]/page.tsx` — join requests section for owner
