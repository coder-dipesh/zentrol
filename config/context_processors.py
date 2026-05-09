"""Template context shared across deployments."""

from django.conf import settings


def deployment(_request):
    """Expose serverless flag for conditional UI (smaller Vercel bundles)."""
    return {'IS_SERVERLESS': getattr(settings, 'IS_SERVERLESS', False)}
