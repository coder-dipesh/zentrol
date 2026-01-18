"""
ASGI config for gesture_presentation project.
It exposes the ASGI callable as a module-level variable named ``application``.
"""
import os
from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

# Get ASGI application
application = get_asgi_application()

# For future WebSocket support with Django Channels:
# Uncomment when channels is added to requirements.txt
# from channels.routing import ProtocolTypeRouter, URLRouter
# from channels.auth import AuthMiddlewareStack
# import gestures.routing
# 
# application = ProtocolTypeRouter({
#     "http": get_asgi_application(),
#     "websocket": AuthMiddlewareStack(
#         URLRouter(
#             gestures.routing.websocket_urlpatterns
#         )
#     ),
# })