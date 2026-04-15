from django.urls import path, include
from django.contrib.auth import views as auth_views
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'gesture-logs', views.GestureLogViewSet)

urlpatterns = [
    path('', views.home, name='home'),
    path('register/', views.register_view, name='register'),
    path('login/', auth_views.LoginView.as_view(template_name='registration/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('password-reset/', auth_views.PasswordResetView.as_view(template_name='registration/password_reset_form.html'), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(template_name='registration/password_reset_done.html'), name='password_reset_done'),
    path('password-reset-confirm/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(template_name='registration/password_reset_confirm.html'), name='password_reset_confirm'),
    path('password-reset-complete/', auth_views.PasswordResetCompleteView.as_view(template_name='registration/password_reset_complete.html'), name='password_reset_complete'),
    path('password-change/', auth_views.PasswordChangeView.as_view(template_name='registration/password_change_form.html'), name='password_change'),
    path('password-change/done/', auth_views.PasswordChangeDoneView.as_view(template_name='registration/password_change_done.html'), name='password_change_done'),
    path('dashboard/', views.dashboard_view, name='dashboard'),
    path('dashboard/account/', views.update_account_profile, name='update_account_profile'),
    path('dashboard/account/sign-out-everywhere/', views.logout_all_sessions_view, name='logout_all_sessions'),
    path(
        'dashboard/account/sessions/<str:session_key>/logout/',
        views.logout_single_session_view,
        name='logout_single_session',
    ),
    path('dashboard/account/delete/', views.delete_account_view, name='delete_account'),
    path('dashboard/upload/', views.upload_presentation, name='upload_presentation'),
    path('dashboard/delete/<uuid:asset_id>/', views.delete_presentation, name='delete_presentation'),
    path('dashboard/favorite/<uuid:asset_id>/', views.toggle_favorite, name='toggle_favorite'),
    path('presentation/', views.presentation_view, name='presentation'),
    path('api/log-gesture/', views.api_log_gesture, name='log_gesture'),
    path('api/', include(router.urls)),
    path('test/', views.test_view, name='test'),
]