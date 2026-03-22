# Zentrol (Gesture Presentation System)

A Django-based web application for controlling presentations using hand gestures powered by MediaPipe. The **UI is server-rendered HTML** in `templates/` with JavaScript under `static/js/` (Reveal.js, gesture engine, MediaPipe).

## Features

- 🤚 **Real-time Hand Gesture Recognition** — MediaPipe (client-side)
- 📊 **Presentation Control** — Navigate slides with gestures
- 📈 **Analytics** — Gesture usage and performance (evolving)
- 🎯 **Multiple Gesture Support** — Thumbs up, fist, open palm, victory, OK
- 🔌 **REST API** — Versioned routes under `/api/v1/`; OpenAPI at `/api/docs/` when `DEBUG` or `SPECTACULAR_PUBLIC`

## Tech Stack

- **Backend**: Django 4.2, Django REST Framework, drf-spectacular (OpenAPI)
- **Frontend**: Django templates (`templates/`) + static JS/CSS (`static/`)
- **Database**: SQLite (default), PostgreSQL via `DATABASE_URL` (recommended; `docker-compose.yml` provided)

## Local development setup

### Prerequisites

- Python 3.9+
- pip
- Virtual environment (recommended)

### Run the app

1. **Clone and enter the repo**
   ```bash
   git clone <your-repo-url>
   cd zentrol
   ```

2. **Virtual environment & Python deps**
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   pip install -r requirements.txt
   ```

3. **Environment**
   ```bash
   cp .env.example .env
   # Edit SECRET_KEY, DATABASE_URL if using Postgres (see docs/DEPLOYMENT.md)
   ```

4. **Optional: local PostgreSQL**
   ```bash
   docker compose up -d
   # Set DATABASE_URL=postgres://zentrol:zentrol@127.0.0.1:5432/zentrol in .env
   ```

5. **MediaPipe assets (offline mode)**
   ```bash
   chmod +x download_mediapipe.sh
   ./download_mediapipe.sh
   ```

6. **Demo slide PNGs + logos (optional)** — if `static/media/slides/` is empty, extract from `static/media.zip`:
   ```bash
   chmod +x scripts/ensure-static-media.sh
   ./scripts/ensure-static-media.sh
   ```
   See `static/MEDIA.md`.

7. **Migrate & run**
   ```bash
   python manage.py migrate
   python manage.py runserver 0.0.0.0:8000
   ```

8. **Optional**: `createsuperuser`, `setup_demo` as needed.

**URLs**

- Home: http://127.0.0.1:8000/
- Presentation: http://127.0.0.1:8000/presentation/
- MediaPipe test: http://127.0.0.1:8000/test/
- Admin: http://127.0.0.1:8000/admin/
- API health: http://127.0.0.1:8000/api/v1/health/
- OpenAPI / Swagger: when `DEBUG=True` or `SPECTACULAR_PUBLIC=True`

Full deployment notes: **`docs/DEPLOYMENT.md`**.

## Production deployment

See **`docs/DEPLOYMENT.md`** for Django on a long-lived host (Railway, Render, Fly, etc.) with PostgreSQL, `collectstatic`, and HTTPS.

The repo also ships **`docs/ARCHITECTURE.md`** and **`docs/API_INVENTORY.md`**.

## Project structure

```
zentrol/
├── config/                 # Django settings, urls, wsgi/asgi
├── gestures/               # Main app (views, API)
├── analytics/
├── templates/              # HTML: home, presentation, test_mediapipe
├── static/                 # MediaPipe, JS, CSS, media
├── docs/                   # ARCHITECTURE, DEPLOYMENT, API_INVENTORY, ADR/
├── docker-compose.yml      # Local PostgreSQL (optional)
├── .env.example
├── requirements.txt
└── manage.py
```

## Environment variables

Copy **`.env.example`** to `.env` and adjust. Key entries:

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | Django secret |
| `DEBUG` | `False` in production |
| `ALLOWED_HOSTS` | Comma-separated hosts |
| `DATABASE_URL` | SQLite default or PostgreSQL URL |
| `CORS_ALLOWED_ORIGINS` | Origins allowed to call the API (default: same host as Django in dev) |
| `CSRF_TRUSTED_ORIGINS` | Trusted origins for CSRF (align with your public URL) |
| `GESTURE_LOG_SHARED_SECRET` | Optional; if set, `POST /api/log-gesture/` requires header `X-Zentrol-Gesture-Log-Secret` |
| `SPECTACULAR_PUBLIC` | If `True`, expose `/api/schema/` and `/api/docs/` when `DEBUG=False` |

## API endpoints (quick reference)

- `GET /` — Home / demo
- `GET /presentation/` — Gesture presentation
- `GET /test/` — MediaPipe smoke test
- `GET /api/v1/health/` — Health JSON
- `POST /api/log-gesture/` — DRF gesture log (throttled; optional shared secret)
- `GET/POST /api/gesture-logs/` — DRF router
- `GET /api/schema/`, `GET /api/docs/` — When `DEBUG` or `SPECTACULAR_PUBLIC`
- `GET /admin/` — Django admin

See **`docs/API_INVENTORY.md`** for the full mapping.

## Development

### File explorer (VS Code / Cursor)

The workspace includes **`.vscode/settings.json`** so bulky folders (`venv/`, `staticfiles/`, `__pycache__/`, etc.) are **hidden** in the sidebar. Reload the window if you don’t see the change.

### Running tests
```bash
pytest
# or
python manage.py test
```

### Code formatting
```bash
black .
flake8 .
```

### Migrations
```bash
python manage.py makemigrations
python manage.py migrate
```

## License

[Your License Here]

## Support

For issues and questions, please open an issue on the repository.
