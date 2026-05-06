from django.db import models
import uuid


class Lip2SpeechInference(models.Model):
    """Audit log for each lip-to-speech inference request."""

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('success', 'Success'),
        ('error', 'Error'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    # Result files (relative to MEDIA_ROOT)
    video_path = models.CharField(max_length=512, blank=True)
    audio_path = models.CharField(max_length=512, blank=True)

    # Inference metrics
    num_frames = models.IntegerField(default=0)
    mel_frames = models.IntegerField(default=0)
    duration_seconds = models.FloatField(default=0.0)
    processing_time_ms = models.FloatField(default=0.0)

    # Status
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    error_message = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Lip2Speech Inference'
        verbose_name_plural = 'Lip2Speech Inferences'

    def __str__(self):
        return f"Inference {self.id} [{self.status}] — {self.duration_seconds:.2f}s audio"
