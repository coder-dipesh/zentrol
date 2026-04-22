from django.urls import path

from . import views

app_name = 'moodle'

urlpatterns = [
    # ── LTI 1.3 endpoints ────────────────────────────────────────────────────
    # Step 1: Moodle initiates OIDC login here
    path('lti/login/', views.lti_login, name='lti_login'),
    # Step 2: Moodle posts the signed JWT here after OIDC handshake
    path('lti/launch/', views.lti_launch, name='lti_launch'),
    # Public key set — Moodle fetches this to verify Zentrol's JWTs
    path('lti/jwks/', views.lti_jwks, name='lti_jwks'),
    # Tool configuration JSON — paste this URL in Moodle "External Tools" setup
    path('lti/config/', views.lti_config, name='lti_config'),
    # Grade passback — called by frontend after a presentation session ends
    path('lti/grade/<str:launch_id>/', views.lti_grade_passback, name='lti_grade_passback'),
]
