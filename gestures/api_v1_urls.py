"""
API v1 URL routes — versioned JSON surface for clients and probes.
"""
from django.urls import path

from . import views

urlpatterns = [
    path('health/', views.api_v1_health, name='api_v1_health'),
]
