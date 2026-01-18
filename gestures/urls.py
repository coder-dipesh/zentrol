from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'gesture-logs', views.GestureLogViewSet)

urlpatterns = [
    path('', views.home, name='home'),
    path('presentation/', views.presentation_view, name='presentation'),
    path('api/log-gesture/', views.log_gesture, name='log_gesture'),
    path('api/', include(router.urls)),
    path('test/', views.test_view, name='test'),
]