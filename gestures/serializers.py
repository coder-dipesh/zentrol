from rest_framework import serializers
from .models import GestureLog, PresentationSession

class GestureLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = GestureLog
        fields = '__all__'
        read_only_fields = ['id', 'created_at']

class PresentationSessionSerializer(serializers.ModelSerializer):
    duration = serializers.SerializerMethodField()
    
    class Meta:
        model = PresentationSession
        fields = '__all__'
        read_only_fields = ['id', 'started_at', 'last_activity']
    
    def get_duration(self, obj):
        if obj.ended_at:
            return (obj.ended_at - obj.started_at).total_seconds()
        return (obj.last_activity - obj.started_at).total_seconds()