"""
Django settings for gesture_presentation project.
"""

import os
from pathlib import Path
import environ

# Initialize environment variables
env = environ.Env()
environ.Env.read_env()

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = env('SECRET_KEY', default='django-insecure-dev-key-change-in-production')

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = env.bool('DEBUG', default=True)

ALLOWED_HOSTS = env.list('ALLOWED_HOSTS', default=['localhost', '127.0.0.1','*'])

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    
    # Third party
    'rest_framework',
    'corsheaders',
    
    # Local apps
    'gestures',
    'analytics',
]

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
            ],
        },
    },
]

WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'

# Database
# In serverless environments (like Vercel), use /tmp directory which is writable
# Note: /tmp is ephemeral - data may be cleared between invocations
def is_serverless_environment():
    """Detect if we're running in a serverless/read-only filesystem environment."""
    # Check environment variables
    if os.environ.get('VERCEL', '').lower() == '1':
        return True
    if os.environ.get('AWS_LAMBDA_FUNCTION_NAME') is not None:
        return True
    
    # Check if BASE_DIR is in a serverless path
    base_dir_str = str(BASE_DIR)
    if '/var/task' in base_dir_str or '/var/runtime' in base_dir_str:
        return True
    
    # Try to write to a test file to check filesystem permissions
    try:
        test_file_path = BASE_DIR / '.write_test'
        with open(test_file_path, 'w') as f:
            f.write('test')
        os.remove(test_file_path)
        return False  # Filesystem is writable
    except (OSError, PermissionError, IOError):
        return True  # Filesystem is read-only

IS_SERVERLESS = is_serverless_environment()

# Configure database path based on environment
if IS_SERVERLESS:
    # In serverless, use /tmp directory which is writable
    # Note: /tmp is ephemeral - data persists only during the function execution
    db_path = '/tmp/db.sqlite3'
else:
    # In local development, use project directory
    db_path = str(BASE_DIR / 'db.sqlite3')

DATABASES = {
    'default': env.db(
        'DATABASE_URL',
        default=f'sqlite:///{db_path}'
    )
}

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

# WhiteNoise configuration for static files serving in production
STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# CORS Settings (for ngrok/local development)
CORS_ALLOWED_ORIGINS = env.list('CORS_ALLOWED_ORIGINS', default=[
    'http://localhost:8000',
    'http://127.0.0.1:8000',
])

CORS_ALLOW_CREDENTIALS = True

# CSRF settings for ngrok
CSRF_TRUSTED_ORIGINS = env.list('CSRF_TRUSTED_ORIGINS', default=[])

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
        'user': '1000/hour'
    }
}

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
    X_FRAME_OPTIONS = 'DENY'

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