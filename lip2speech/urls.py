from django.urls import path
from . import views

urlpatterns = [
    path('', views.lip2speech_page, name='lip2speech'),
]

api_urlpatterns = [
    path('synthesize/', views.synthesize, name='lip2speech_synthesize'),
    path('logs/', views.inference_logs, name='lip2speech_logs'),
]
