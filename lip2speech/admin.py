from django.contrib import admin
from .models import Lip2SpeechInference


@admin.register(Lip2SpeechInference)
class Lip2SpeechInferenceAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'num_frames', 'duration_seconds', 'processing_time_ms', 'created_at')
    list_filter = ('status',)
    readonly_fields = ('id', 'created_at')
    search_fields = ('id',)
