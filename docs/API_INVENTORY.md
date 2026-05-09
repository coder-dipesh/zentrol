# API inventory — templates vs API

This document maps **user-facing behavior** to **routes** and the **JSON API**.

## HTML / template routes (`gestures`, Django)

| User flow | Route | View | Notes |
|-----------|-------|------|--------|
| Home / demo | `GET /` | `home` | Renders `home.html` |
| Presentation | `GET /presentation/` | `presentation_view` | Query `session_id`; creates/gets `PresentationSession`; `presentation.html` |

Templates live in **`templates/`** at the project root.

## Legacy / unversioned JSON & API (`/api/`)

| Purpose | Method & path | Auth / notes |
|---------|----------------|--------------|
| Log gesture (JSON) | `POST /api/log-gesture/` | DRF `api_view`; **throttled** (`gesture_log`). If `GESTURE_LOG_SHARED_SECRET` is set, requires header `X-Zentrol-Gesture-Log-Secret`. |
| Gesture logs (DRF) | `GET/POST ... /api/gesture-logs/` (router) | Default DRF; authenticated writes where configured — confirm client auth for writes. |
| Session stats | `GET /api/gesture-logs/session_stats/?session_id=...` | Custom `@action` on ViewSet. |

Router base is included at `path('api/', include(router.urls))` → list/detail routes under `/api/gesture-logs/`.

## Versioned API (`/api/v1/`)

| Purpose | Method & path | Notes |
|---------|----------------|-------|
| Health | `GET /api/v1/health/` | Public; JSON `{ status, service, version }` |

**Planned / to add** (optional): slide metadata, session create/heartbeat, batched gesture logs — prefer new paths here and document in OpenAPI.

## OpenAPI

- **Schema**: `GET /api/schema/` (OpenAPI 3)
- **Swagger UI**: `GET /api/docs/`

Registered only when **`DEBUG=True`** or **`SPECTACULAR_PUBLIC=True`** (see `config/urls.py`).

## Analytics app

No `analytics` Django app ships in this repo; related URL includes are commented out in `config/urls.py`.

## Admin

| Path | Purpose |
|------|---------|
| `/admin/` | Django admin |
