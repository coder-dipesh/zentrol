"""
Django settings for gesture_presentation project.
"""

import os
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# Initialize environment variables — explicitly point at the project-root .env
env = environ.Env()
env.read_env(BASE_DIR / '.env')

# SECURITY WARNING: keep the secret key used in production secret!
_SECRET_DEFAULT = 'django-insecure-dev-key-change-in-production'
SECRET_KEY = env('SECRET_KEY', default=_SECRET_DEFAULT)

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool('DEBUG', default=True)

# Never use '*' — set explicit hosts. Production must set ALLOWED_HOSTS to real domains.
ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=[
    'localhost',
    '127.0.0.1',
    '.ngrok-free.app',
    '.ngrok-free.dev',
    'host.docker.internal',
])


def _env_truthy(name: str) -> bool:
    """Read env before ``IS_SERVERLESS`` is computed (same semantics as serverless check)."""
    return (os.environ.get(name) or '').strip().lower() in ('1', 'true', 'yes')


_VERCEL = _env_truthy('VERCEL')
# Lip2Speech requires torch/mediacodec stack — excluded from requirements-vercel.txt.
# Default OFF when VERCEL=1 so serverless bundles stay under platform limits.
LIP2SPEECH_ENABLED = env.bool('LIP2SPEECH_ENABLED', default=not _VERCEL)

# Application definition
_INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    # Third party
    'rest_framework',
    'drf_spectacular',
    'corsheaders',

    # Local apps
    'gestures',
    'moodle',
]
if LIP2SPEECH_ENABLED:
    _INSTALLED_APPS.append('lip2speech')
INSTALLED_APPS = _INSTALLED_APPS

# ── Lip2Speech settings ────────────────────────────────────────────────────────
# Path to pre-trained model weights (.pt file).
# Download from https://github.com/Chris10M/Lip2Speech and set this env var.
LIP2SPEECH_WEIGHTS_PATH = env('LIP2SPEECH_WEIGHTS_PATH', default=None)

# ── Moodle / LTI 1.3 settings ──────────────────────────────────────────────────
# PyLTI1p3 uses Django's cache framework to persist OIDC state and nonces across
# the two-step LTI handshake. The default LocMemCache is per-process and won't
# work correctly in multi-worker deployments. Switch to DatabaseCache or Redis
# for production.
#
# To create the database cache table (needed for LTI OIDC state):
#   python manage.py createcachetable
#
# For Redis (recommended for production):
#   pip install django-redis
#   Set CACHE_BACKEND=django_redis.cache.RedisCache and CACHE_LOCATION=redis://...
CACHES = {
    'default': {
        'BACKEND': env(
            'CACHE_BACKEND',
            default='django.core.cache.backends.db.DatabaseCache',
        ),
        'LOCATION': env('CACHE_LOCATION', default='zentrol_cache_table'),
    }
}

# Base URL used when building absolute URLs in LTI config JSON.
# Set this in production to your public domain, e.g. https://zentrol.example.com
LTI_BASE_URL = env('LTI_BASE_URL', default='')

# Origins allowed to embed Zentrol in an iframe (Moodle site URLs), without trailing slash.
# Required for Moodle LTI when DEBUG=False — CSP frame-ancestors is built from this list plus 'self'.
# Example: LTI_FRAME_ANCESTORS=https://moodle.university.edu
LTI_FRAME_ANCESTORS = env.list('LTI_FRAME_ANCESTORS', default=[])

# ── Reverse-proxy / ngrok SSL header ──────────────────────────────────────────
# ngrok (and most reverse proxies) terminate TLS and forward requests as HTTP
# to Django. Without this setting, request.is_secure() returns False and
# PyLTI1p3's state cookie is set WITHOUT SameSite=None, which causes browsers
# to drop it on the cross-site POST from Moodle → /moodle/lti/launch/.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
USE_X_FORWARDED_HOST = True

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'whitenoise.middleware.WhiteNoiseMiddleware',  # Static files for production
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'config.middleware.FrameAncestorsCSPMiddleware',
]

ROOT_URLCONF = 'config.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'config.context_processors.deployment',
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'


def is_serverless_environment():
    """Detect if we're running in a serverless/read-only filesystem environment."""
    # Check environment variables first (fastest check)
    if os.environ.get('VERCEL', '').lower() == '1':
        return True
    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME') is not None:
        return True
    
    # Check if BASE_DIR is in a serverless path (common in Vercel/Lambda)
    base_dir_str = str(BASE_DIR)
    if '/var/task' in base_dir_str or '/var/runtime' in base_dir_str:
        return True
    
    # If none of the above match, assume local development
    return False

IS_SERVERLESS = is_serverless_environment()

# Database
# Serverless (Vercel, Lambda): require PostgreSQL — SQLite on /tmp is ephemeral and
# breaks auth/LTI after cold starts. Prefer migrate during deploy (vercel.json); cold-start
# migrate runs via ``config.serverless_db`` when the build step does not execute migrations.
if IS_SERVERLESS:
    _database_url = (os.environ.get('DATABASE_URL') or '').strip()
    if not _database_url:
        raise ImproperlyConfigured(
            'DATABASE_URL must be set for serverless deployments (e.g. VERCEL=1). '
            'Use managed PostgreSQL (Neon, Supabase, Vercel Postgres, etc.). SQLite is not '
            'supported on serverless because the filesystem is not durable across instances.'
        )
    if _database_url.lower().startswith('sqlite:'):
        raise ImproperlyConfigured(
            'DATABASE_URL must not use SQLite on serverless — use PostgreSQL. '
            'See docs/DEPLOYMENT.md (Vercel).'
        )
    DATABASES = {'default': env.db_url_config(_database_url)}
else:
    db_path = str(BASE_DIR / 'db.sqlite3')
    DATABASES = {
        'default': env.db(
            'DATABASE_URL',
            default=f'sqlite:///{db_path}',
        )
    }

# Opt out of cold-start migrate (e.g. when you run migrations only in CI / release phase).
SKIP_SERVERLESS_STARTUP_MIGRATE = env.bool('SKIP_SERVERLESS_STARTUP_MIGRATE', default=False)

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {
        'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator',
    },
    {
        'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator',
    },
]

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [
    BASE_DIR / 'static',
]

# WhiteNoise — serverless builds omit large demo assets (.vercelignore); manifest storage
# would require every {% static %} path at collectstatic time, so use non-manifest there.
STATICFILES_STORAGE = (
    'whitenoise.storage.CompressedStaticFilesStorage'
    if IS_SERVERLESS
    else 'whitenoise.storage.CompressedManifestStaticFilesStorage'
)

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Auth redirects
LOGIN_URL = 'login'
LOGIN_REDIRECT_URL = 'dashboard'
LOGOUT_REDIRECT_URL = 'home'

# Allow larger JSON payloads for preprocessed slide uploads from dashboard.
# PPTX parsing generates data URLs per slide; defaults are too small and can 400.
DATA_UPLOAD_MAX_MEMORY_SIZE = env.int('DATA_UPLOAD_MAX_MEMORY_SIZE', default=50 * 1024 * 1024)  # 50 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = env.int('FILE_UPLOAD_MAX_MEMORY_SIZE', default=50 * 1024 * 1024)  # 50 MB

# Browser clients allowed to call the API (same-origin Django pages + any extra dev origins).
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[
    'http://localhost:8000',
    'http://127.0.0.1:8000',
])

CORS_ALLOW_CREDENTIALS = True

# ── LTI / iframe cookie settings ───────────────────────────────────────────────
# LTI 1.3 runs inside a Moodle iframe (cross-site context). Modern browsers
# block cookies that don't have SameSite=None; Secure. Set these so that:
#   • Django session cookie is forwarded on cross-site POSTs from Moodle
#   • CSRF cookie is readable by the launch form POST
# In local dev over HTTP (ngrok provides HTTPS so Secure=True is fine).
SESSION_COOKIE_SAMESITE = 'None'
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = 'None'
CSRF_COOKIE_SECURE = True

CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[
    'http://localhost:8000',
    'http://127.0.0.1:8000',
    'https://*.ngrok-free.app',
    'https://*.ngrok-free.dev',
])

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticatedOrReadOnly',
    ],
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle'
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '100/hour',
        'user': '1000/hour',
        'gesture_log': '300/hour',
    },
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}

# OpenAPI / Swagger (drf-spectacular)
SPECTACULAR_SETTINGS = {
    'TITLE': 'Zentrol API',
    'DESCRIPTION': 'Gesture-controlled presentation system — REST API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
}

# Expose /api/schema/ and /api/docs/ outside DEBUG (default False — use staff + Django admin or env).
SPECTACULAR_PUBLIC = env.bool('SPECTACULAR_PUBLIC', default=False)

# Optional shared secret for POST /api/log-gesture/ (optional header X-Zentrol-Gesture-Log-Secret).
# If set, requests without matching X-Zentrol-Gesture-Log-Secret header get 403.
GESTURE_LOG_SHARED_SECRET = env('GESTURE_LOG_SHARED_SECRET', default='').strip()

# ── Algolia search ────────────────────────────────────────────────────────────
# Powers the dashboard ⌘K "Jump to" search. Optional — if ALGOLIA_APP_ID /
# ALGOLIA_ADMIN_API_KEY are not set, the search modal falls back to a static
# server-rendered list and no Algolia code paths run. To enable:
#   1. Create an Algolia app at https://www.algolia.com/
#   2. Set the three env vars below.
#   3. Run `python manage.py reindex_algolia` to push existing decks.
# Auto-sync of new/updated/deleted decks is wired via Django signals.
#
# Key roles (do NOT swap them):
#   ALGOLIA_ADMIN_API_KEY   — server-side only; used to push records and
#                             configure the index. Never sent to the browser.
#   ALGOLIA_SEARCH_API_KEY  — public search-only key; used as the "parent"
#                             when minting per-user secured keys for the
#                             browser. Restricted by Algolia to search only.
ALGOLIA_APP_ID = env('ALGOLIA_APP_ID', default='').strip()
ALGOLIA_ADMIN_API_KEY = env('ALGOLIA_ADMIN_API_KEY', default='').strip()
ALGOLIA_SEARCH_API_KEY = env('ALGOLIA_SEARCH_API_KEY', default='').strip()
ALGOLIA_INDEX_NAME = env('ALGOLIA_INDEX_NAME', default='zentrol_presentations').strip()
ALGOLIA_ENABLED = bool(ALGOLIA_APP_ID and ALGOLIA_ADMIN_API_KEY)

# Email (password reset / auth notifications)
EMAIL_BACKEND = env('EMAIL_BACKEND', default='django.core.mail.backends.smtp.EmailBackend')
EMAIL_HOST = env('EMAIL_HOST', default='localhost')
EMAIL_PORT = env.int('EMAIL_PORT', default=25)
EMAIL_HOST_USER = env('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = env('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS = env.bool('EMAIL_USE_TLS', default=False)
EMAIL_USE_SSL = env.bool('EMAIL_USE_SSL', default=False)
DEFAULT_FROM_EMAIL = env('DEFAULT_FROM_EMAIL', default='no-reply@zentrol.local')

# Production Security Settings
# =============================
if not DEBUG:
    # Security settings automatically enabled when DEBUG=False
    SECURE_SSL_REDIRECT = env.bool('SECURE_SSL_REDIRECT', default=True)
    SESSION_COOKIE_SECURE = env.bool('SESSION_COOKIE_SECURE', default=True)
    CSRF_COOKIE_SECURE = env.bool('CSRF_COOKIE_SECURE', default=True)
    SECURE_HSTS_SECONDS = env.int('SECURE_HSTS_SECONDS', default=31536000)
    SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool('SECURE_HSTS_INCLUDE_SUBDOMAINS', default=True)
    SECURE_HSTS_PRELOAD = env.bool('SECURE_HSTS_PRELOAD', default=True)
    SECURE_CONTENT_TYPE_NOSNIFF = env.bool('SECURE_CONTENT_TYPE_NOSNIFF', default=True)
    SECURE_BROWSER_XSS_FILTER = env.bool('SECURE_BROWSER_XSS_FILTER', default=True)
    # ALLOWALL keeps Django's XFrameOptionsMiddleware happy (None crashes .upper()).
    # Embedding policy for Moodle is enforced via LTI_FRAME_ANCESTORS_CSP frame-ancestors.
    X_FRAME_OPTIONS = 'ALLOWALL'
    _fa_parts = ["'self'"]
    for _raw in LTI_FRAME_ANCESTORS:
        _u = (_raw or '').strip().rstrip('/')
        if _u and _u not in _fa_parts:
            _fa_parts.append(_u)
    LTI_FRAME_ANCESTORS_CSP = 'frame-ancestors ' + ' '.join(_fa_parts)
    _sk = (SECRET_KEY or '').strip()
    if _sk == _SECRET_DEFAULT or len(_sk) < 48:
        raise ImproperlyConfigured(
            'SECRET_KEY must be set to a long random value (48+ characters) when DEBUG=False. '
            'Do not use the default development key in production.'
        )
else:
    # Dev / DEBUG: permissive framing for local and ngrok HTTPS testing.
    X_FRAME_OPTIONS = 'ALLOWALL'
    LTI_FRAME_ANCESTORS_CSP = ''

# Logging
# Use the IS_SERVERLESS variable already defined above

logging_handlers = {
    'console': {
        'class': 'logging.StreamHandler',
        'formatter': 'verbose',
    },
}

# Only add file handler if not in serverless environment and DEBUG is True
# In serverless environments, filesystem is read-only, so we can't write log files
# NEVER add file handler in serverless environments, regardless of DEBUG setting
if not IS_SERVERLESS and DEBUG:
    try:
        # Test if we can write to the log file location
        log_file = BASE_DIR / 'gestures.log'
        # Try to create/append to the file to verify write permissions
        with open(log_file, 'a') as test_file:
            pass
        # Only add if we successfully tested write access
        logging_handlers['file'] = {
            'class': 'logging.FileHandler',
            'filename': str(log_file),
            'formatter': 'verbose',
        }
    except (OSError, PermissionError, IOError):
        # If we can't write, just skip file logging
        pass

# Final safety check: remove file handler if we're in serverless (shouldn't happen, but be safe)
if IS_SERVERLESS and 'file' in logging_handlers:
    del logging_handlers['file']

# Build handlers list for root logger - only include handlers that exist
root_handlers = ['console']
if 'file' in logging_handlers:
    root_handlers.append('file')

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': logging_handlers,
    'root': {
        'handlers': root_handlers,
        'level': env('LOG_LEVEL', default='INFO'),
    },
}