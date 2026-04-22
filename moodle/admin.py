"""
Django admin for Moodle LTI integration.

Provides:
  - LTITool registration (one row per Moodle site)
  - LTIUserMapping read-only view
  - LTISession activity log with inline grade passback status
"""

from django.contrib import admin
from django.utils.html import format_html

from .models import LTISession, LTITool, LTIUserMapping


@admin.register(LTITool)
class LTIToolAdmin(admin.ModelAdmin):
    list_display = ('name', 'issuer', 'client_id', 'is_active', 'created_at')
    list_filter = ('is_active',)
    search_fields = ('name', 'issuer', 'client_id')
    readonly_fields = ('created_at', 'updated_at')

    fieldsets = (
        ('Identity', {
            'fields': ('name', 'is_active'),
        }),
        ('Moodle Platform', {
            'fields': ('issuer', 'client_id', 'deployment_ids'),
            'description': (
                'Values from Moodle: Site administration → Plugins → '
                'Activity modules → External tool → Manage tools.'
            ),
        }),
        ('Moodle Endpoints', {
            'fields': ('auth_login_url', 'auth_token_url', 'key_set_url'),
            'description': (
                'auth_login_url: Moodle OIDC auth endpoint.<br>'
                'auth_token_url: OAuth 2.0 token endpoint (grade passback).<br>'
                'key_set_url: Moodle JWKS endpoint.'
            ),
        }),
        ('Tool Key Pair', {
            'fields': ('tool_private_key', 'tool_public_key'),
            'classes': ('collapse',),
            'description': (
                'Generate with: <code>python manage.py generate_lti_keys</code>. '
                'Register the public key in Moodle when setting up the external tool.'
            ),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
            'classes': ('collapse',),
        }),
    )


@admin.register(LTIUserMapping)
class LTIUserMappingAdmin(admin.ModelAdmin):
    list_display = ('moodle_full_name', 'moodle_email', 'django_user', 'lti_tool', 'created_at')
    list_filter = ('lti_tool',)
    search_fields = ('moodle_full_name', 'moodle_email', 'django_user__username', 'lti_user_id')
    readonly_fields = ('lti_user_id', 'lti_tool', 'django_user', 'created_at', 'updated_at')

    def has_add_permission(self, request):
        # Mappings are created automatically on LTI launch — not manually
        return False


@admin.register(LTISession)
class LTISessionAdmin(admin.ModelAdmin):
    list_display = (
        'user', 'course_title', 'lti_tool', 'launched_at',
        'is_completed', 'score_display',
    )
    list_filter = ('lti_tool', 'is_completed')
    search_fields = ('user__username', 'course_title', 'launch_id')
    readonly_fields = (
        'user', 'lti_tool', 'launch_id',
        'course_id', 'course_title', 'resource_link_id', 'resource_link_title',
        'ags_lineitems_url', 'ags_lineitem_url',
        'launched_at', 'is_completed', 'score', 'completed_at',
    )

    @admin.display(description='Score')
    def score_display(self, obj):
        if obj.score is None:
            return '—'
        pct = obj.score * 100
        colour = '#2ecc71' if pct >= 80 else '#e67e22' if pct >= 50 else '#e74c3c'
        return format_html(
            '<span style="color:{};font-weight:bold;">{:.0f}%</span>',
            colour, pct,
        )

    def has_add_permission(self, request):
        return False
