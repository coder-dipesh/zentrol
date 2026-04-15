import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class Lip2SpeechConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'lip2speech'
    verbose_name = 'Lip to Speech'

    # Singleton pipeline — loaded once at startup, reused across requests.
    pipeline = None

    def ready(self):
        """Load Lip2Speech model weights once when Django starts.

        Django's dev-server StatReloader spawns two processes; both call
        ready().  We skip loading in the reloader (parent) process so the
        265 MB weights are only loaded once — in the actual server process.
        """
        import os
        if os.environ.get('RUN_MAIN') != 'true':
            # This is the reloader watchdog process, not the server process.
            return

        from django.conf import settings

        try:
            from .inference import Lip2SpeechPipeline

            weights_path = getattr(settings, 'LIP2SPEECH_WEIGHTS_PATH', None)
            Lip2SpeechConfig.pipeline = Lip2SpeechPipeline.load(weights_path=weights_path)
            logger.info(
                "Lip2Speech pipeline ready (device=%s)", Lip2SpeechConfig.pipeline.device
            )
        except Exception as exc:
            # Log the failure but don't prevent Django from starting.
            # The synthesize view will surface a proper error when called.
            logger.error("Failed to load Lip2Speech pipeline at startup: %s", exc)
