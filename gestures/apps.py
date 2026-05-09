from django.apps import AppConfig


class GesturesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "gestures"

    def ready(self) -> None:
        # Register Algolia auto-sync receivers (no-ops when Algolia disabled).
        from . import signals  # noqa: F401
