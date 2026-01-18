from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.contrib.auth.decorators import login_required
from rest_framework import viewsets, permissions
from rest_framework.decorators import action
from rest_framework.response import Response
import json
import uuid
from datetime import datetime

from .models import GestureLog, PresentationSession
from .serializers import GestureLogSerializer

def home(request):
    """Home page with demo"""
    return render(request, 'home.html', {
        'demo_available': True,
    })

def presentation_view(request):
    """Main presentation view"""
    session_id = request.GET.get('session_id', str(uuid.uuid4()))
    
    # Create or get session
    session, created = PresentationSession.objects.get_or_create(
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

@csrf_exempt
@require_POST
def log_gesture(request):
    """API endpoint to log gesture detection"""
    try:
        data = json.loads(request.body)
        
        log = GestureLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_id=data.get('session_id', 'anonymous'),
            gesture_type=data.get('gesture_type', 'unknown'),
            confidence=data.get('confidence', 0.0),
            frame_count=data.get('frame_count', 1),
            hand_x=data.get('hand_x'),
            hand_y=data.get('hand_y'),
            hand_z=data.get('hand_z'),
            detection_time_ms=data.get('detection_time_ms', 0.0),
            frame_processing_time_ms=data.get('frame_processing_time_ms', 0.0),
            browser=data.get('browser', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            screen_resolution=data.get('screen_resolution', ''),
        )
        
        # Update session
        try:
            session = PresentationSession.objects.get(session_id=data.get('session_id'))
            session.gesture_count += 1
            session.last_activity = datetime.now()
            session.save()
        except PresentationSession.DoesNotExist:
            pass
        
        return JsonResponse({'status': 'success', 'log_id': str(log.id)})
        
    except json.JSONDecodeError:
        return JsonResponse({'status': 'error', 'message': 'Invalid JSON'}, status=400)
    except Exception as e:
        return JsonResponse({'status': 'error', 'message': str(e)}, status=500)

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