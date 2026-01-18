from django.contrib import admin
from .models import GestureLog, PresentationSession, SystemPerformance

@admin.register(GestureLog)
class GestureLogAdmin(admin.ModelAdmin):
    list_display = ['gesture_type', 'confidence', 'session_id', 'created_at', 'detection_time_ms']
    list_filter = ['gesture_type', 'created_at', 'browser']
    search_fields = ['session_id', 'browser', 'user_agent']
    readonly_fields = ['created_at']
    
    fieldsets = (
        ('Detection Info', {
            'fields': ('gesture_type', 'confidence', 'frame_count')
        }),
        ('Performance', {
            'fields': ('detection_time_ms', 'frame_processing_time_ms')
        }),
        ('System Info', {
            'fields': ('session_id', 'browser', 'screen_resolution')
        }),
        ('Timestamps', {
            'fields': ('created_at',)
        }),
    )

@admin.register(PresentationSession)
class PresentationSessionAdmin(admin.ModelAdmin):
    list_display = ['session_id', 'gesture_count', 'avg_latency_ms', 'started_at', 'last_activity']
    list_filter = ['started_at', 'is_presenting']
    search_fields = ['session_id']
    readonly_fields = ['started_at', 'last_activity']
    
    fieldsets = (
        ('Session Info', {
            'fields': ('session_id', 'user', 'gesture_count')
        }),
        ('Presentation State', {
            'fields': ('current_slide', 'total_slides', 'is_fullscreen', 'is_presenting')
        }),
        ('Performance', {
            'fields': ('avg_latency_ms',)
        }),
        ('Timestamps', {
            'fields': ('started_at', 'last_activity', 'ended_at')
        }),
    )

@admin.register(SystemPerformance)
class SystemPerformanceAdmin(admin.ModelAdmin):
    list_display = ['session', 'fps', 'latency_ms', 'recorded_at']
    list_filter = ['recorded_at']
    readonly_fields = ['recorded_at']