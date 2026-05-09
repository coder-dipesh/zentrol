"""Custom middleware for deployment-specific behavior."""

from django.conf import settings


class FrameAncestorsCSPMiddleware:
    """
    Append Content-Security-Policy frame-ancestors for Moodle LTI embedding.

    In production (DEBUG=False), settings use X_FRAME_OPTIONS=ALLOWALL so Django's
    clickjacking middleware does not 500; restrictive framing is enforced via
    this CSP frame-ancestors directive for Moodle LTI.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        csp = getattr(settings, 'LTI_FRAME_ANCESTORS_CSP', '') or ''
        if csp:
            response.headers['Content-Security-Policy'] = csp
        return response
