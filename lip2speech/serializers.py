from rest_framework import serializers
from .models import Lip2SpeechInference


class Lip2SpeechInferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = Lip2SpeechInference
        fields = [
            'id', 'status', 'num_frames', 'mel_frames',
            'duration_seconds', 'processing_time_ms',
            'audio_path', 'error_message', 'created_at',
        ]
        read_only_fields = fields
