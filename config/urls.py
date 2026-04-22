from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from lip2speech.urls import api_urlpatterns as lip2speech_api_urls

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('gestures.api_v1_urls')),
    path('api/', include('gestures.urls')),
    path('api/lip2speech/', include((lip2speech_api_urls, 'lip2speech_api'))),
    # path('analytics/', include('analytics.urls')),
    path('lip2speech/', include('lip2speech.urls')),
    path('', include('gestures.urls')),  # Main app URLs
    path('moodle/', include('moodle.urls', namespace='moodle')),
]

# OpenAPI / Swagger — off in production unless SPECTACULAR_PUBLIC=True (or DEBUG).
if settings.DEBUG or getattr(settings, 'SPECTACULAR_PUBLIC', False):
    urlpatterns = [
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    ] + urlpatterns

if settings.DEBUG:
    # Use finder-based URLs so /static/ works without `collectstatic` (STATIC_ROOT may be empty).
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)