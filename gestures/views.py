from django.shortcuts import render
from django.conf import settings
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from drf_spectacular.utils import extend_schema
import uuid
from datetime import datetime

from .models import GestureLog, PresentationSession
from .serializers import GestureLogSerializer
from .throttles import GestureLogAnonThrottle

def home(request):
    """Home page with demo upload."""
    return render(request, 'home.html', {
        'demo_available': True,
    })

def presentation_view(request):
    """Main presentation view (Django template + static JS)."""
    session_id = request.GET.get('session_id', str(uuid.uuid4()))

    PresentationSession.objects.get_or_create(
        session_id=session_id,
        defaults={
            'user': request.user if request.user.is_authenticated else None
        }
    )

    return render(request, 'presentation.html', {
        'session_id': session_id,
        'is_authenticated': request.user.is_authenticated,
    })

def test_view(request):
    return render(request, 'test_mediapipe.html')


@extend_schema(
    summary='Log gesture (anonymous)',
    description='Used by static gesture scripts. Throttled; optional shared secret.',
    tags=['Gestures'],
)
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([GestureLogAnonThrottle])
def api_log_gesture(request):
    """Log gesture detection — not for direct public abuse: throttle + optional shared secret."""
    secret = getattr(settings, 'GESTURE_LOG_SHARED_SECRET', '') or ''
    if secret:
        got = request.headers.get('X-Zentrol-Gesture-Log-Secret', '')
        if got != secret:
            return Response({'status': 'error', 'message': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    try:
        data = request.data
        if not isinstance(data, dict):
            data = {}

        gesture_type = data.get('gesture_type') or data.get('action') or 'unknown'

        log = GestureLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_id=data.get('session_id', 'anonymous'),
            gesture_type=gesture_type,
            confidence=float(data.get('confidence', 0.0)),
            frame_count=int(data.get('frame_count', 1)),
            hand_x=data.get('hand_x'),
            hand_y=data.get('hand_y'),
            hand_z=data.get('hand_z'),
            detection_time_ms=float(data.get('detection_time_ms', 0.0)),
            frame_processing_time_ms=float(data.get('frame_processing_time_ms', 0.0)),
            browser=data.get('browser', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            screen_resolution=data.get('screen_resolution', ''),
        )

        sid = data.get('session_id')
        if sid:
            try:
                session = PresentationSession.objects.get(session_id=sid)
                session.gesture_count += 1
                session.last_activity = datetime.now()
                session.save()
            except PresentationSession.DoesNotExist:
                pass

        return Response({'status': 'success', 'log_id': str(log.id)})

    except (TypeError, ValueError) as e:
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# REST API Views
class GestureLogViewSet(viewsets.ModelViewSet):
    """REST API for gesture logs"""
    queryset = GestureLog.objects.all().order_by('-created_at')
    serializer_class = GestureLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def session_stats(self, request):
        """Get statistics for a session"""
        session_id = request.query_params.get('session_id')
        if not session_id:
            return Response({'error': 'session_id required'}, status=400)
        
        logs = self.queryset.filter(session_id=session_id)
        total = logs.count()
        
        stats = {
            'total_gestures': total,
            'gesture_types': {},
            'avg_confidence': 0,
            'avg_latency': 0,
        }
        
        if total > 0:
            for log in logs:
                stats['gesture_types'][log.gesture_type] = stats['gesture_types'].get(log.gesture_type, 0) + 1
            
            stats['avg_confidence'] = sum(log.confidence for log in logs) / total
            stats['avg_latency'] = sum(log.detection_time_ms for log in logs) / total
        
        return Response(stats)


@extend_schema(
    summary='Health check',
    description='Liveness probe for the API (no database access).',
    tags=['Health'],
)
@api_view(['GET'])
@permission_classes([AllowAny])
def api_v1_health(request):
    """Lightweight health check for load balancers (no DB hit)."""
    # This is a minimal, fast API health check endpoint (no DB hit).
    # Add any additional quick non-DB checks here if needed in future.
    return Response({
        'status': 'ok',
        'service': 'zentrol-api',
        'version': '1',
    })
