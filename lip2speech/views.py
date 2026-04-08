"""
Lip2Speech Django views.

Endpoints:
  GET  /lip2speech/          — UI page
  POST /api/lip2speech/synthesize/  — upload video, get WAV back
  GET  /api/lip2speech/logs/ — list recent inference logs
"""

import logging
import os
import uuid
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import Lip2SpeechInference
from .serializers import Lip2SpeechInferenceSerializer

logger = logging.getLogger(__name__)

# Supported video MIME types
# MediaRecorder may report 'video/webm;codecs=vp9' etc — match by prefix
ALLOWED_VIDEO_PREFIXES = (
    'video/mp4', 'video/webm', 'video/ogg',
    'video/quicktime', 'video/x-msvideo',
)
MAX_UPLOAD_BYTES = 50 * 1024 * 1024  # 50 MB


def lip2speech_page(request):
    """Render the Lip2Speech UI."""
    recent = Lip2SpeechInference.objects.filter(status='success').order_by('-created_at')[:5]
    return render(request, 'lip2speech.html', {'recent_inferences': recent})


@csrf_exempt
@api_view(['POST'])
@permission_classes([AllowAny])
def synthesize(request):
    """
    Accept a video upload and return synthesised speech as a WAV file.

    Request: multipart/form-data with field 'video'.
    Response: audio/wav binary on success, JSON error otherwise.
    """
    video_file = request.FILES.get('video')
    if video_file is None:
        return Response({'error': 'No video file provided (field name: video).'}, status=400)

    content_type = video_file.content_type or ''
    if not any(content_type.startswith(p) for p in ALLOWED_VIDEO_PREFIXES):
        return Response(
            {'error': f'Unsupported file type: {content_type}. Use mp4, webm, or mov.'},
            status=415,
        )

    if video_file.size > MAX_UPLOAD_BYTES:
        return Response({'error': 'Video file exceeds 50 MB limit.'}, status=413)

    # Persist the upload
    upload_dir = Path(settings.MEDIA_ROOT) / 'lip2speech' / 'uploads'
    upload_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(video_file.name).suffix or '.mp4'
    video_filename = f"{uuid.uuid4()}{suffix}"
    video_path = upload_dir / video_filename

    with open(video_path, 'wb') as f:
        for chunk in video_file.chunks():
            f.write(chunk)

    # Create an inference log entry
    log = Lip2SpeechInference.objects.create(
        video_path=str(video_path.relative_to(settings.MEDIA_ROOT)),
        status='processing',
    )

    try:
        from .apps import Lip2SpeechConfig

        pipeline = Lip2SpeechConfig.pipeline
        if pipeline is None:
            # Startup loading failed — attempt lazy load now.
            from .inference import Lip2SpeechPipeline
            weights_path = getattr(settings, 'LIP2SPEECH_WEIGHTS_PATH', None)
            pipeline = Lip2SpeechPipeline.load(weights_path=weights_path)
            Lip2SpeechConfig.pipeline = pipeline

        wav_bytes, meta = pipeline.run(str(video_path))

        # Save audio
        audio_dir = Path(settings.MEDIA_ROOT) / 'lip2speech' / 'audio'
        audio_dir.mkdir(parents=True, exist_ok=True)
        audio_filename = f"{log.id}.wav"
        audio_path = audio_dir / audio_filename
        audio_path.write_bytes(wav_bytes)

        log.status = 'success'
        log.audio_path = str(audio_path.relative_to(settings.MEDIA_ROOT))
        log.num_frames = meta['num_frames']
        log.mel_frames = meta['mel_frames']
        log.duration_seconds = meta['duration_seconds']
        log.processing_time_ms = meta['processing_time_ms']
        log.save()

        response = HttpResponse(wav_bytes, content_type='audio/wav')
        response['Content-Disposition'] = f'attachment; filename="lip2speech_{log.id}.wav"'
        response['X-Inference-ID'] = str(log.id)
        response['X-Duration-Seconds'] = str(meta['duration_seconds'])
        response['X-Processing-Time-MS'] = str(meta['processing_time_ms'])
        return response

    except ImportError as exc:
        msg = f"Missing dependency: {exc}. Install torch, librosa, mediapipe, opencv-python."
        logger.exception(msg)
        log.status = 'error'
        log.error_message = msg
        log.save()
        return Response({'error': msg}, status=503)

    except ValueError as exc:
        msg = str(exc)
        logger.warning("Lip2Speech preprocessing failed: %s", msg)
        log.status = 'error'
        log.error_message = msg
        log.save()
        return Response({'error': msg}, status=422)

    except Exception as exc:
        msg = f"Inference failed: {exc}"
        logger.exception(msg)
        log.status = 'error'
        log.error_message = msg
        log.save()
        return Response({'error': 'Internal inference error. See server logs.'}, status=500)


@api_view(['GET'])
@permission_classes([AllowAny])
def inference_logs(request):
    """Return the 20 most recent inference logs."""
    logs = Lip2SpeechInference.objects.order_by('-created_at')[:20]
    return Response(Lip2SpeechInferenceSerializer(logs, many=True).data)
