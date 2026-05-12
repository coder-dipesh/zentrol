"""Template context shared across deployments."""

from django.conf import settings


def deployment(_request):
    """Expose serverless flag for conditional UI (smaller Vercel bundles)."""
    return {
        'IS_SERVERLESS': getattr(settings, 'IS_SERVERLESS', False),
        'hero_intro_video_url': getattr(settings, 'HERO_INTRO_VIDEO_URL', '') or '',
        'dashboard_max_request_body_bytes': getattr(
            settings, 'SERVERLESS_MAX_REQUEST_BODY_BYTES', None
        ),
    }
