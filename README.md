# Zentrol (Gesture Presentation System)

A Django-based web application for controlling presentations using hand gestures powered by MediaPipe. The **UI is server-rendered HTML** in `templates/` with JavaScript under `static/js/` (Reveal.js, gesture engine, MediaPipe). Zentrol also integrates with **Moodle via LTI 1.3**, allowing instructors to embed it as an activity that auto-logs students into Django.

## Features

- 🤚 **Real-time Hand Gesture Recognition** — MediaPipe (client-side)
- 📊 **Presentation Control** — Navigate slides with gestures
- 📈 **Analytics** — Gesture usage and performance (evolving)
- 🎯 **Multiple Gesture Support** — Thumbs up, fist, open palm, victory, OK
- 🔌 **REST API** — Versioned routes under `/api/v1/`; OpenAPI at `/api/docs/` when `DEBUG` or `SPECTACULAR_PUBLIC`
- 🎓 **Moodle LTI 1.3** — Single-sign-on via LTI launch; auto-provisions Django users from Moodle identity; grade passback via AGS

## Tech Stack

- **Backend**: Django 4.2, Django REST Framework, drf-spectacular (OpenAPI), PyLTI1p3 2.0
- **Frontend**: Django templates (`templates/`) + static JS/CSS (`static/`)
- **Database**: SQLite (default), PostgreSQL via `DATABASE_URL` (recommended; `docker-compose.yml` provided)
- **LMS integration**: Moodle 4.4 via LTI 1.3 (OIDC + JWT)

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

---

## Moodle LTI 1.3 Integration — Local Testing

This section walks through running Moodle in Docker and connecting it to a local Django dev server via **ngrok**, so you can test the full LTI 1.3 launch flow (Moodle activity click → auto-login → Zentrol dashboard) on your laptop.

### How it works

```
Browser → Moodle (Docker :8080)
             ↓  POST to LTI login URL (via ngrok)
         Django (:8000) ←→ ngrok (public HTTPS URL)
             ↓  redirect to Moodle auth
         Moodle → POST signed JWT to launch URL (via ngrok)
             ↓
         Django validates JWT, auto-provisions user, redirects to /dashboard/
```

### Prerequisites

| Tool | Purpose |
|------|---------|
| Docker Desktop | Runs Moodle + MariaDB |
| [ngrok](https://ngrok.com/download) | Gives Django a public HTTPS URL reachable from both browser and Docker |
| Python 3.9+ | Django |

### Step 1 — Start Moodle in Docker

```bash
docker compose -f docker-compose.moodle.yml up -d --build
```

**First boot only (~5–8 min):** downloads Moodle 4.4 and runs the installer.  
Watch progress: `docker compose -f docker-compose.moodle.yml logs -f moodle`

Wait until you see `🌐 Starting Apache at http://localhost:8080 ...`, then open:

- **Moodle**: http://localhost:8080 — login with `admin / Admin1234!`

> On subsequent restarts the image is already built; it comes up in ~20 seconds.

### Step 2 — Start ngrok

In a separate terminal:

```bash
ngrok http 8000
```

Copy the `https://xxxx.ngrok-free.xxx` URL from the output. You'll use it in every step below — replace `https://YOUR-NGROK-URL` with the actual value.

### Step 3 — Configure Django environment

Edit `.env` in the project root (or create it from `.env.example`):

```dotenv
# Hosts Django will accept (ngrok sends X-Forwarded-Host)
ALLOWED_HOSTS=localhost,127.0.0.1,.ngrok-free.app,.ngrok-free.dev,0.0.0.0

# Required so Moodle's cross-site POST to /launch/ is accepted by CSRF middleware
CSRF_TRUSTED_ORIGINS=http://localhost:8000,http://localhost:8080,https://YOUR-NGROK-URL

# Database-backed cache so LTI OIDC state survives across the two-step handshake
CACHE_BACKEND=django.core.cache.backends.db.DatabaseCache
CACHE_LOCATION=zentrol_cache_table

# Public URL Django advertises in LTI config — must be reachable from both
# the browser AND the Moodle Docker container
LTI_BASE_URL=https://YOUR-NGROK-URL
```

Then create the cache table (one-time):

```bash
python manage.py createcachetable
```

### Step 4 — Generate RSA keys & register the Moodle platform

```bash
python manage.py generate_lti_keys \
  --name "Local Moodle" \
  --issuer http://localhost:8080 \
  --client-id PLACEHOLDER \
  --deployment-ids 1
```

> You'll replace `PLACEHOLDER` with the real client ID from Moodle in Step 5. Run the command again with `--update` after you have it.

### Step 5 — Register Zentrol as an LTI 1.3 tool in Moodle

1. In Moodle: **Site administration → Plugins → Activity modules → External tool → Manage tools**
2. Click **"configure a tool manually"** and fill in:

   | Field | Value |
   |-------|-------|
   | Tool name | `Zentrol Presentation` |
   | Tool URL | `https://YOUR-NGROK-URL/moodle/lti/launch/` |
   | LTI version | **LTI 1.3** |
   | Public keyset URL | `https://YOUR-NGROK-URL/moodle/lti/jwks/` |
   | Initiate login URL | `https://YOUR-NGROK-URL/moodle/lti/login/` |
   | Redirection URI(s) | `https://YOUR-NGROK-URL/moodle/lti/launch/` |
   | Default launch container | **New window** or **Existing window** |

3. Save. Moodle shows you a **Client ID** — copy it.

4. Back in Django admin (`http://localhost:8000/admin/` → **Moodle → LTI Tools → your record**), fill in:

   | Field | Value |
   |-------|-------|
   | Client ID | *(paste from Moodle)* |
   | Auth login URL | `http://localhost:8080/mod/lti/auth.php` |
   | Auth token URL | `http://host.docker.internal:8080/mod/lti/token.php` |
   | Key set URL | `http://host.docker.internal:8080/mod/lti/certs.php` |
   | Deployment IDs | `["1"]` |

   > `host.docker.internal` lets Django (on your Mac) reach Moodle (in Docker) for JWT validation calls. `localhost:8080` is used for browser-facing Moodle URLs.

   Or re-run the management command with all values:

   ```bash
   python manage.py generate_lti_keys \
     --name "Local Moodle" \
     --issuer http://localhost:8080 \
     --client-id YOUR_CLIENT_ID \
     --deployment-ids 1 \
     --auth-login-url http://localhost:8080/mod/lti/auth.php \
     --auth-token-url http://host.docker.internal:8080/mod/lti/token.php \
     --key-set-url http://host.docker.internal:8080/mod/lti/certs.php \
     --update
   ```

### Step 6 — Start Django

```bash
python manage.py runserver 0.0.0.0:8000
```

### Step 7 — Add the activity to a Moodle course and test

1. In Moodle, open (or create) a course → **Turn editing on → Add an activity → External tool**
2. Select **Zentrol Presentation** from the preconfigured tools list
3. Give it a name (e.g. `Gesture Demo`) and save
4. Click the activity

**Expected result:** the browser is briefly redirected through the LTI handshake and lands on the Zentrol dashboard, logged in as a Django user provisioned from your Moodle identity. Check Django logs:

```
POST /moodle/lti/login/   302   ← OIDC redirect OK
LTI: provisioned new user 'admin' for Moodle sub=2
LTI launch: user=admin course='My Course' issuer=http://localhost:8080
POST /moodle/lti/launch/  302   ← launch OK
GET  /dashboard/          200   ← landed on dashboard ✅
```

### LTI endpoints reference

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/moodle/lti/login/` | POST | OIDC initiation (Step 1 of handshake) |
| `/moodle/lti/launch/` | POST | JWT launch handler — logs user in |
| `/moodle/lti/jwks/` | GET | Tool public-key set (Moodle fetches this) |
| `/moodle/lti/config/` | GET | Tool config JSON (paste URL into Moodle for auto-fill) |
| `/moodle/lti/grade/<launch_id>/` | POST | Send score back to Moodle gradebook (AGS) |

### Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| `State not found` | State cookie blocked cross-site | Ensure `SECURE_PROXY_SSL_HEADER` is set and `LTI_BASE_URL` starts with `https://` |
| `Missing state param` | `enable_check_cookies()` fell back to GET | Already removed in this codebase — verify you're on the latest `moodleInt` commit |
| Django `Invalid HTTP_HOST` | ngrok host not in `ALLOWED_HOSTS` | Add `.ngrok-free.dev` or `.ngrok-free.app` to the list |
| Moodle iframe shows blank | `X-Frame-Options` blocking embed | `X_FRAME_OPTIONS = 'ALLOWALL'` is set — verify Django restarted |
| `No active LTI tools found` | LTI tool record missing or `is_active=False` | Check Django admin → Moodle → LTI Tools |
| `Unknown LTI issuer` | Issuer URL mismatch | Tool record issuer must exactly match Moodle's `wwwroot` (e.g. `http://localhost:8080`) |
| ngrok session expired | Free ngrok URL changes on restart | Re-run `ngrok http 8000`, update `LTI_BASE_URL` in `.env`, update all 4 URLs in Moodle tool settings, restart Django |

---

## Production deployment

See **`docs/DEPLOYMENT.md`** for Django on a long-lived host (Railway, Render, Fly, etc.) with PostgreSQL, `collectstatic`, and HTTPS.

The repo also ships **`docs/ARCHITECTURE.md`** and **`docs/API_INVENTORY.md`**.

## Project structure

```
zentrol/
├── config/                 # Django settings, urls, wsgi/asgi
├── gestures/               # Main app (views, API, gesture recognition)
├── moodle/                 # LTI 1.3 integration (views, models, management commands)
│   ├── models.py           # LTITool, LTIUserMapping, LTISession
│   ├── views.py            # /lti/login/, /lti/launch/, /lti/jwks/, /lti/config/
│   ├── lti_config.py       # ToolConfDict builder (PyLTI1p3 2.0 API)
│   └── management/commands/generate_lti_keys.py
├── lip2speech/             # Lip-to-speech synthesis pipeline
├── analytics/
├── templates/              # HTML: home, dashboard, presentation, test_mediapipe
├── static/                 # MediaPipe, JS, CSS, media
├── docker/                 # Moodle Docker image (Dockerfile.moodle, moodle-init.sh)
├── docs/                   # ARCHITECTURE, DEPLOYMENT, API_INVENTORY, ADR/
├── docker-compose.yml      # Local PostgreSQL (optional)
├── docker-compose.moodle.yml  # Moodle + MariaDB for LTI local testing
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
| `CORS_ALLOWED_ORIGINS` | Origins allowed to call the API |
| `CSRF_TRUSTED_ORIGINS` | Trusted origins for CSRF (include your ngrok URL for LTI testing) |
| `GESTURE_LOG_SHARED_SECRET` | Optional; if set, `POST /api/log-gesture/` requires `X-Zentrol-Gesture-Log-Secret` header |
| `SPECTACULAR_PUBLIC` | If `True`, expose `/api/schema/` and `/api/docs/` when `DEBUG=False` |
| `CACHE_BACKEND` | Django cache backend (use `DatabaseCache` for LTI OIDC state) |
| `CACHE_LOCATION` | Cache table name for `DatabaseCache` (default: `zentrol_cache_table`) |
| `LTI_BASE_URL` | Public HTTPS URL Django is reachable at — used in LTI config JSON and launch redirects |
| `LIP2SPEECH_WEIGHTS_PATH` | Path to pre-trained Lip2Speech `.pt` weights file |

## API endpoints (quick reference)

- `GET /` — Home / demo
- `GET /presentation/` — Gesture presentation
- `GET /test/` — MediaPipe smoke test
- `GET /api/v1/health/` — Health JSON
- `POST /api/log-gesture/` — DRF gesture log (throttled; optional shared secret)
- `GET/POST /api/gesture-logs/` — DRF router
- `GET /api/schema/`, `GET /api/docs/` — When `DEBUG` or `SPECTACULAR_PUBLIC`
- `GET /admin/` — Django admin
- `POST /moodle/lti/login/` — LTI 1.3 OIDC initiation
- `POST /moodle/lti/launch/` — LTI 1.3 JWT launch (auto-login)
- `GET /moodle/lti/jwks/` — Tool public-key set
- `GET /moodle/lti/config/` — Tool configuration JSON
- `POST /moodle/lti/grade/<launch_id>/` — Grade passback to Moodle

See **`docs/API_INVENTORY.md`** for the full mapping.

## Development

### File explorer (VS Code / Cursor)

The workspace includes **`.vscode/settings.json`** so bulky folders (`venv/`, `staticfiles/`, `__pycache__/`, etc.) are **hidden** in the sidebar. Reload the window if you don't see the change.

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
