# Zentrol — deployment and local development

## Local development (single process)

Django serves **HTML templates**, **`/static`**, and the **API** on one port.

```bash
cd /path/to/zentrol
python -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env       # edit SECRET_KEY and any DB URL
python manage.py migrate
python manage.py runserver 0.0.0.0:8000
```

- App: `http://127.0.0.1:8000`
- OpenAPI schema: `http://127.0.0.1:8000/api/schema/` (when exposed)
- Swagger UI: `http://127.0.0.1:8000/api/docs/` (when exposed)
- Health (v1): `http://127.0.0.1:8000/api/v1/health/`

---

## PostgreSQL locally

**Option A — Docker Compose (recommended)**

```bash
docker compose up -d
```

In `.env`:

```env
DATABASE_URL=postgres://zentrol:zentrol@127.0.0.1:5432/zentrol
```

Then:

```bash
python manage.py migrate
```

**Option B — Your own Postgres**

Point `DATABASE_URL` at your instance (same `django-environ` format). Keep SQLite in `.env.example` for quick clones that skip Docker.

---

## CORS and CSRF

For a **single Django site** (HTML + `/static` + `/api` on the same origin), defaults in `.env.example` (`http://localhost:8000`, `http://127.0.0.1:8000`) are usually enough.

If you **split** the app across origins later (e.g. static CDN + API host), set:

1. **`CORS_ALLOWED_ORIGINS`** — every browser origin that calls the API.
2. **`CSRF_TRUSTED_ORIGINS`** — same if you use cookie/session auth.

Example for production (adjust hosts):

```env
CORS_ALLOWED_ORIGINS=https://zentrol.example.com
CSRF_TRUSTED_ORIGINS=https://zentrol.example.com
```

---

## Production (Django on a long-lived host)

**Recommended**: one process (or container) running Django + Gunicorn/Uvicorn, with **PostgreSQL**, `DEBUG=False`, `collectstatic`, and HTTPS termination at your platform or reverse proxy.

1. Set `DATABASE_URL`, `SECRET_KEY` (48+ characters — startup fails if still using the dev default), `DEBUG=False`, `ALLOWED_HOSTS` (no wildcards).
2. Run `python manage.py collectstatic` and `migrate` per your platform.
3. Align `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` with your public URL(s).
4. **Moodle LTI**: set `LTI_BASE_URL` to your public HTTPS origin and `LTI_FRAME_ANCESTORS` to your Moodle site origin(s) (comma-separated). When `DEBUG=False`, Django uses **Content-Security-Policy `frame-ancestors`** (`'self'` plus those origins) so Moodle can embed Zentrol; omitting `LTI_FRAME_ANCESTORS` leaves only `'self'` and iframe launches from Moodle will be blocked by the browser.
5. **LTI cache**: use `DatabaseCache` + `python manage.py createcachetable`, or Redis for multiple workers (see `.env.example`).

---

## Vercel (serverless)

The repo ships **`requirements-vercel.txt`** (installed via **`vercel.json`** → `installCommand`) so deployments skip PyTorch / Lip2Speech / dev-only wheels and stay closer to the platform bundle limit.

- **`LIP2SPEECH_ENABLED`** defaults **`False`** when **`VERCEL=1`** — the `lip2speech` Django app and `/lip2speech/*` routes are not loaded.
- **`.vercelignore`** drops the `lip2speech/` package directory from the uploaded source (you cannot enable Lip2Speech on Vercel without switching to full `requirements.txt` and a hosting tier that fits the bundle — generally use a separate GPU/CPU service instead).
- **`DATABASE_URL`** is **required** and must be **PostgreSQL** (`postgres://` or `postgresql://`). Django raises at startup if it is missing or SQLite — serverless filesystems are not suitable for SQLite-backed auth.
- Set **`DATABASE_URL`**, **`SECRET_KEY`** (48+ chars), and **`DEBUG=False`** (plus hosts/CSRF) in the Vercel project environment so **build** can run migrations.
- **`vercel.json`** → **`buildCommand`** runs **`collectstatic`**, **`migrate --noinput`**, and **`createcachetable`** when Vercel actually executes custom builds — Python deployments sometimes omit this step, so **`config/serverless_db.py`** also runs **`migrate`** + **`createcachetable`** on each serverless cold start (disable with **`SKIP_SERVERLESS_STARTUP_MIGRATE=True`** only if you always migrate elsewhere).

---

## Checklist before demo

- [ ] `DEBUG=False`, strong `SECRET_KEY` (48+ chars), `ALLOWED_HOSTS` set (no `*`)
- [ ] PostgreSQL migrations applied
- [ ] `CORS_ALLOWED_ORIGINS` / `CSRF_TRUSTED_ORIGINS` match your public URL(s)
- [ ] `LTI_BASE_URL` and `LTI_FRAME_ANCESTORS` set if using Moodle in production
- [ ] Cache table or Redis configured for LTI OIDC state
- [ ] `GET /api/v1/health/` returns 200 from the deployed app
