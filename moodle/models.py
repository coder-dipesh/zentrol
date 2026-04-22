"""
Moodle LTI 1.3 integration models.

Flow:
  1. Admin registers a Moodle platform via LTITool (stores issuer, client_id, keys).
  2. On first LTI launch, a Django User is created and linked via LTIUserMapping.
  3. Each launch creates an LTISession capturing course context and grade-passback URLs.
"""

from django.db import models
from django.contrib.auth.models import User


class LTITool(models.Model):
    """
    Represents one registered Moodle platform (LTI 1.3 tool configuration).
    One row per Moodle site that is allowed to launch Zentrol.
    """

    name = models.CharField(max_length=200, help_text="Friendly label, e.g. 'University Moodle'")

    # ── Moodle platform identity ──────────────────────────────────────────────
    issuer = models.URLField(
        unique=True,
        help_text="Moodle site URL used as the LTI issuer, e.g. https://moodle.example.com",
    )
    client_id = models.CharField(
        max_length=255,
        help_text="Client ID assigned by Moodle when registering the external tool",
    )
    deployment_ids = models.JSONField(
        default=list,
        help_text="Deployment IDs for this tool (from Moodle admin → External Tools)",
    )

    # ── Moodle OIDC / token endpoints ────────────────────────────────────────
    auth_login_url = models.URLField(
        help_text="Moodle OIDC authorisation endpoint "
                  "(Site admin → Plugins → Authentication → LTI → Platform login URL)",
    )
    auth_token_url = models.URLField(
        help_text="Moodle OAuth 2.0 token endpoint (used for grade passback)",
    )
    key_set_url = models.URLField(
        help_text="Moodle JWKS endpoint — used to verify the platform's JWT signatures",
    )

    # ── Tool (Zentrol) RSA key pair ───────────────────────────────────────────
    # Generate with: python manage.py generate_lti_keys --tool-name "University Moodle"
    tool_private_key = models.TextField(
        help_text="RSA-2048 private key (PEM) used to sign Zentrol's JWTs",
    )
    tool_public_key = models.TextField(
        help_text="RSA-2048 public key (PEM) served at /moodle/lti/jwks/",
    )

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'LTI Tool (Moodle Platform)'
        verbose_name_plural = 'LTI Tools (Moodle Platforms)'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.issuer})"


class LTIUserMapping(models.Model):
    """
    Links a Moodle user (identified by LTI `sub` claim) to a Django User.
    Created automatically on the first LTI launch from a given Moodle user.
    """

    django_user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='lti_mapping',
    )
    lti_tool = models.ForeignKey(
        LTITool, on_delete=models.CASCADE, related_name='user_mappings',
    )
    # `sub` claim from the LTI JWT — unique per Moodle site
    lti_user_id = models.CharField(max_length=255)

    # Cached Moodle profile (updated on each launch)
    moodle_email = models.EmailField(blank=True)
    moodle_full_name = models.CharField(max_length=255, blank=True)
    moodle_roles = models.JSONField(default=list, help_text="LTI roles from last launch")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('lti_tool', 'lti_user_id')
        verbose_name = 'LTI User Mapping'
        verbose_name_plural = 'LTI User Mappings'

    def __str__(self):
        return f"{self.moodle_full_name or self.lti_user_id} → {self.django_user.username}"


class LTISession(models.Model):
    """
    Records every LTI launch event. Stores course context and grade-passback
    endpoints so Zentrol can report completion back to Moodle.
    """

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='lti_sessions')
    lti_tool = models.ForeignKey(LTITool, on_delete=models.CASCADE, related_name='sessions')

    # Unique ID assigned by PyLTI1p3 for this launch (used as cache key)
    launch_id = models.CharField(max_length=255, unique=True, db_index=True)

    # ── Course / resource context ─────────────────────────────────────────────
    course_id = models.CharField(max_length=255, blank=True)
    course_title = models.CharField(max_length=500, blank=True)
    resource_link_id = models.CharField(max_length=255, blank=True)
    resource_link_title = models.CharField(max_length=500, blank=True)

    # ── Assignment and Grade Services (AGS) ───────────────────────────────────
    ags_lineitems_url = models.URLField(
        blank=True,
        help_text="AGS lineitems container endpoint (for creating new line items)",
    )
    ags_lineitem_url = models.URLField(
        blank=True,
        help_text="AGS pre-created lineitem endpoint (for direct score submission)",
    )

    # ── Completion / grade passback ───────────────────────────────────────────
    is_completed = models.BooleanField(default=False)
    score = models.FloatField(
        null=True, blank=True,
        help_text="Score in [0.0, 1.0] sent back to Moodle gradebook",
    )
    completed_at = models.DateTimeField(null=True, blank=True)

    launched_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-launched_at']
        verbose_name = 'LTI Session'
        verbose_name_plural = 'LTI Sessions'

    def __str__(self):
        return (
            f"{self.user.username} — {self.course_title or self.course_id} "
            f"({self.launched_at.date()})"
        )
