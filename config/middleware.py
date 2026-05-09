"""Custom middleware for deployment-specific behavior."""

from django.conf import settings


class FrameAncestorsCSPMiddleware:
    """
    Append Content-Security-Policy frame-ancestors for Moodle LTI embedding.

    In production (DEBUG=False), X_FRAME_OPTIONS is omitted (None) so browsers
    rely on this directive instead of X-Frame-Options: DENY, which would block
    Moodle's iframe of Zentrol.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        csp = getattr(settings, 'LTI_FRAME_ANCESTORS_CSP', '') or ''
        if csp:
            response.headers['Content-Security-Policy'] = csp
        return response
