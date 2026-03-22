"""DRF throttles for public / low-trust endpoints."""

from rest_framework.throttling import AnonRateThrottle


class GestureLogAnonThrottle(AnonRateThrottle):
    """Rate-limit anonymous gesture logging (browser clients)."""

    scope = 'gesture_log'
