"""Ensure DB schema on serverless cold starts when deploy-time migrate did not run."""

from django.conf import settings
from django.core.management import call_command


def ensure_serverless_schema() -> None:
    """Apply migrations + DB cache table when running on Vercel/Lambda-style hosts."""
    if not getattr(settings, 'IS_SERVERLESS', False):
        return
    if getattr(settings, 'SKIP_SERVERLESS_STARTUP_MIGRATE', False):
        return
    call_command('migrate', '--noinput', verbosity=0)
    call_command('createcachetable', verbosity=0)
