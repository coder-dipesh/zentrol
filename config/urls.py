from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('gestures.api_v1_urls')),
]

if getattr(settings, 'LIP2SPEECH_ENABLED', False):
    from lip2speech.urls import api_urlpatterns as lip2speech_api_urls

    urlpatterns.append(
        path('api/lip2speech/', include((lip2speech_api_urls, 'lip2speech_api'))),
    )
    urlpatterns.append(path('lip2speech/', include('lip2speech.urls')))

urlpatterns += [
    # Must come before catch-all '' — gestures does not define moodle/* routes.
    path('moodle/', include('moodle.urls', namespace='moodle')),
    path('', include('gestures.urls')),
]

# OpenAPI / Swagger — off in production unless SPECTACULAR_PUBLIC=True (or DEBUG).
if settings.DEBUG or getattr(settings, 'SPECTACULAR_PUBLIC', False):
    urlpatterns = [
        path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
        path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    ] + urlpatterns

if settings.DEBUG:
    urlpatterns += staticfiles_urlpatterns()
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
