from django.db import models
from django.contrib.auth.models import User
import uuid

class GestureLog(models.Model):
    """Log of all gesture detections for analytics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    session_id = models.CharField(max_length=100, db_index=True)
    
    # Gesture details
    gesture_type = models.CharField(max_length=50, choices=[
        ('thumbs_up', '👍 Thumbs Up'),
        ('fist', '✊ Fist'),
        ('open_palm', '🖐️ Open Palm'),
        ('victory', '✌️ Victory'),
        ('ok', '👌 OK'),
        ('unknown', '❓ Unknown'),
    ])
    
    # Detection confidence
    confidence = models.FloatField(default=0.0)
    frame_count = models.IntegerField(default=0)  # Frames detected
    
    # Hand position (normalized 0-1)
    hand_x = models.FloatField(null=True, blank=True)
    hand_y = models.FloatField(null=True, blank=True)
    hand_z = models.FloatField(null=True, blank=True)
    
    # Performance metrics
    detection_time_ms = models.FloatField(default=0.0)
    frame_processing_time_ms = models.FloatField(default=0.0)
    
    # System info
    browser = models.CharField(max_length=100, blank=True)
    user_agent = models.TextField(blank=True)
    screen_resolution = models.CharField(max_length=50, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        indexes = [
            models.Index(fields=['session_id', 'created_at']),
            models.Index(fields=['gesture_type', 'created_at']),
        ]
        ordering = ['-created_at']
    
    def __str__(self):
        return f"{self.get_gesture_type_display()} ({self.confidence:.2f}) - {self.created_at}"

class PresentationSession(models.Model):
    """Track presentation sessions"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    session_id = models.CharField(max_length=100, unique=True, db_index=True)
    
    # Presentation state
    current_slide = models.IntegerField(default=0)
    total_slides = models.IntegerField(default=0)
    is_fullscreen = models.BooleanField(default=False)
    is_presenting = models.BooleanField(default=False)
    
    # Performance
    avg_latency_ms = models.FloatField(default=0.0)
    gesture_count = models.IntegerField(default=0)
    
    # Timing
    started_at = models.DateTimeField(auto_now_add=True)
    last_activity = models.DateTimeField(auto_now=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    
    class Meta:
        ordering = ['-started_at']
    
    def __str__(self):
        return f"Session {self.session_id} - {self.gesture_count} gestures"

class SystemPerformance(models.Model):
    """System performance metrics"""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(PresentationSession, on_delete=models.CASCADE)
    
    # Performance metrics
    fps = models.FloatField(default=0.0)  # Frames per second
    latency_ms = models.FloatField(default=0.0)
    cpu_usage = models.FloatField(null=True, blank=True)
    memory_usage_mb = models.FloatField(null=True, blank=True)
    
    # Detection metrics
    false_positives = models.IntegerField(default=0)
    false_negatives = models.IntegerField(default=0)
    true_positives = models.IntegerField(default=0)
    
    recorded_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        ordering = ['-recorded_at']
    
    def accuracy(self):
        if self.true_positives + self.false_positives + self.false_negatives == 0:
            return 0
        return self.true_positives / (self.true_positives + self.false_positives + self.false_negatives)