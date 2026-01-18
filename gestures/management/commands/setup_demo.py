from django.core.management.base import BaseCommand
from django.contrib.auth.models import User
from gestures.models import PresentationSession, GestureLog
import random
from datetime import datetime, timedelta

class Command(BaseCommand):
    help = 'Setup demo data for gesture presentation system'
    
    def handle(self, *args, **options):
        self.stdout.write('Setting up demo data...')
        
        # Create demo user
        user, created = User.objects.get_or_create(
            username='demo',
            defaults={
                'email': 'demo@example.com',
                'is_staff': True
            }
        )
        if created:
            user.set_password('demo123')
            user.save()
            self.stdout.write(self.style.SUCCESS('Created demo user'))
        
        # Create demo session
        session, created = PresentationSession.objects.get_or_create(
            session_id='demo-session-001',
            defaults={
                'user': user,
                'total_slides': 5,
                'is_presenting': True,
                'gesture_count': 0,
                'avg_latency_ms': 85.5
            }
        )
        
        # Create sample gesture logs
        gestures = ['thumbs_up', 'fist', 'open_palm', 'victory', 'ok']
        
        for i in range(50):
            gesture_type = random.choice(gestures)
            confidence = random.uniform(0.7, 0.98)
            
            GestureLog.objects.create(
                user=user,
                session_id=session.session_id,
                gesture_type=gesture_type,
                confidence=confidence,
                frame_count=random.randint(5, 10),
                detection_time_ms=random.uniform(50, 120),
                frame_processing_time_ms=random.uniform(10, 30),
                browser=random.choice(['Chrome', 'Firefox', 'Safari']),
                screen_resolution=random.choice(['1920x1080', '1440x900', '1366x768']),
                created_at=datetime.now() - timedelta(minutes=random.randint(0, 60))
            )
        
        session.gesture_count = 50
        session.save()
        
        self.stdout.write(self.style.SUCCESS('Successfully setup demo data'))