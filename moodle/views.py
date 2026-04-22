"""
Moodle LTI 1.3 views.

Endpoints:
  GET/POST /moodle/lti/login/   — OIDC initiation (Step 1)
  GET/POST /moodle/lti/launch/  — JWT launch handler (Step 2, user auto-login)
  GET      /moodle/lti/jwks/    — Tool public-key set (Moodle fetches this)
  GET      /moodle/lti/config/  — Tool configuration JSON (easy Moodle setup)
  POST     /moodle/lti/grade/<launch_id>/  — Send score back to Moodle gradebook

LTI 1.3 flow:
  Moodle → OIDC login → Zentrol login view
          → redirect to Moodle auth
          → Moodle → Zentrol launch view (JWT in POST)
          → validate JWT, create/find user, login, redirect to dashboard
"""

import logging

from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET

from pylti1p3.contrib.django import (
    DjangoCacheDataStorage,
    DjangoMessageLaunch,
    DjangoOIDCLogin,
)
from pylti1p3.exception import LtiException
from pylti1p3.grade import Grade

from .lti_config import get_tool_conf
from .models import LTISession, LTITool, LTIUserMapping

logger = logging.getLogger(__name__)

# ── LTI constants ──────────────────────────────────────────────────────────────
_CTX_CLAIM = 'https://purl.imsglobal.org/spec/lti/claim/context'
_RES_CLAIM = 'https://purl.imsglobal.org/spec/lti/claim/resource_link'
_AGS_CLAIM = 'https://purl.imsglobal.org/spec/lti/claim/endpoint'
_ROLES_CLAIM = 'https://purl.imsglobal.org/spec/lti/claim/roles'


# ── Step 1 — OIDC initiation ───────────────────────────────────────────────────

@csrf_exempt
def lti_login(request):
    """
    LTI 1.3 OIDC initiation endpoint.
    Moodle calls this first; we redirect the user's browser back to Moodle to
    complete the OIDC handshake.
    """
    tool_conf = get_tool_conf()
    launch_data_storage = DjangoCacheDataStorage()

    try:
        oidc_login = DjangoOIDCLogin(
            request, tool_conf, launch_data_storage=launch_data_storage
        )
        target_link_uri = (
            request.POST.get('target_link_uri')
            or request.GET.get('target_link_uri', '')
        )
        return oidc_login.enable_check_cookies().redirect(target_link_uri)
    except LtiException as exc:
        logger.exception("LTI OIDC login failed: %s", exc)
        return JsonResponse({'error': 'LTI login failed', 'detail': str(exc)}, status=400)


# ── Step 2 — JWT launch / user provisioning ────────────────────────────────────

@csrf_exempt
def lti_launch(request):
    """
    LTI 1.3 launch endpoint.
    Validates the signed JWT from Moodle, provisions a Django user if needed,
    logs them in, records the session, and redirects to the dashboard.
    """
    tool_conf = get_tool_conf()
    launch_data_storage = DjangoCacheDataStorage()

    try:
        message_launch = DjangoMessageLaunch(
            request, tool_conf, launch_data_storage=launch_data_storage
        )
        launch_data = message_launch.get_launch_data()
    except LtiException as exc:
        logger.exception("LTI launch JWT validation failed: %s", exc)
        return JsonResponse(
            {'error': 'LTI launch failed', 'detail': str(exc)}, status=400
        )

    # ── Extract claims ─────────────────────────────────────────────────────────
    sub = launch_data.get('sub', '')
    email = launch_data.get('email', '')
    given_name = launch_data.get('given_name', '')
    family_name = launch_data.get('family_name', '')
    full_name = launch_data.get('name', f'{given_name} {family_name}'.strip())
    roles = launch_data.get(_ROLES_CLAIM, [])
    issuer = launch_data.get('iss', '')

    context_claim = launch_data.get(_CTX_CLAIM, {})
    resource_claim = launch_data.get(_RES_CLAIM, {})
    ags_claim = launch_data.get(_AGS_CLAIM, {})

    # ── Resolve the Moodle platform record ────────────────────────────────────
    try:
        lti_tool = LTITool.objects.get(issuer=issuer, is_active=True)
    except LTITool.DoesNotExist:
        logger.error("LTI launch from unregistered issuer: %s", issuer)
        return JsonResponse({'error': f'Unknown LTI issuer: {issuer}'}, status=403)

    # ── Find or create Django user ─────────────────────────────────────────────
    django_user = _provision_user(lti_tool, sub, email, given_name, family_name, full_name, roles)

    # ── Authenticate (no password needed for LTI) ─────────────────────────────
    login(request, django_user, backend='django.contrib.auth.backends.ModelBackend')

    # ── Record LTI session ────────────────────────────────────────────────────
    launch_id = message_launch.get_launch_id()
    LTISession.objects.create(
        user=django_user,
        lti_tool=lti_tool,
        launch_id=launch_id,
        course_id=context_claim.get('id', ''),
        course_title=context_claim.get('title', ''),
        resource_link_id=resource_claim.get('id', ''),
        resource_link_title=resource_claim.get('title', ''),
        ags_lineitems_url=ags_claim.get('lineitems', ''),
        ags_lineitem_url=ags_claim.get('lineitem', ''),
    )

    # Persist launch_id in Django session for later grade passback
    request.session['lti_launch_id'] = launch_id
    request.session['lti_course_title'] = context_claim.get('title', '')
    request.session['lti_resource_title'] = resource_claim.get('title', '')

    logger.info(
        "LTI launch: user=%s course=%r issuer=%s",
        django_user.username, context_claim.get('title'), issuer,
    )

    return redirect('dashboard')


# ── JWKS — public key set ──────────────────────────────────────────────────────

@require_GET
def lti_jwks(request):
    """
    Serve the tool's JSON Web Key Set (JWKS).
    Moodle fetches this endpoint to verify JWTs that Zentrol signs.
    """
    tool_conf = get_tool_conf()
    return JsonResponse(tool_conf.get_jwks(), safe=False)


# ── Tool configuration JSON ────────────────────────────────────────────────────

@require_GET
def lti_config(request):
    """
    Return a tool-configuration JSON document.
    Paste the URL of this endpoint into Moodle's "Tool URL" field when
    registering Zentrol as an External Tool to auto-fill most settings.
    """
    base = request.build_absolute_uri('/').rstrip('/')
    config = {
        "title": "Zentrol — Gesture Presentation",
        "description": (
            "Gesture-controlled slide presentations with real-time hand tracking, "
            "AAC communication, and Lip2Speech synthesis."
        ),
        "oidc_initiation_url": f"{base}/moodle/lti/login/",
        "target_link_uri": f"{base}/moodle/lti/launch/",
        "public_jwk_url": f"{base}/moodle/lti/jwks/",
        "scopes": [
            "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem",
            "https://purl.imsglobal.org/spec/lti-ags/scope/lineitem.readonly",
            "https://purl.imsglobal.org/spec/lti-ags/scope/result.readonly",
            "https://purl.imsglobal.org/spec/lti-ags/scope/score",
        ],
        "extensions": [
            {
                "platform": "moodle.net",
                "settings": {
                    "platform": "moodle.net",
                    "placements": [
                        {"placement": "course_navigation", "default": "enabled"},
                        {"placement": "link_selection"},
                    ],
                },
            }
        ],
        "custom_fields": {},
    }
    return JsonResponse(config)


# ── Grade passback (AGS) ───────────────────────────────────────────────────────

@login_required
def lti_grade_passback(request, launch_id: str):
    """
    POST  /moodle/lti/grade/<launch_id>/

    Send the user's score back to the Moodle gradebook for this session.
    Body parameter: score (float 0.0–1.0, default 1.0)

    Called by the frontend JS after the user completes a presentation session.
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    try:
        lti_session = LTISession.objects.select_related('lti_tool', 'user').get(
            launch_id=launch_id,
            user=request.user,
        )
    except LTISession.DoesNotExist:
        return JsonResponse({'error': 'LTI session not found'}, status=404)

    if not lti_session.ags_lineitem_url and not lti_session.ags_lineitems_url:
        return JsonResponse(
            {'error': 'Grade passback not configured for this session'}, status=400
        )

    if lti_session.is_completed:
        return JsonResponse({'status': 'already_submitted', 'score': lti_session.score})

    try:
        score_value = max(0.0, min(1.0, float(request.POST.get('score', 1.0))))
    except (TypeError, ValueError):
        return JsonResponse({'error': 'Invalid score value'}, status=400)

    tool_conf = get_tool_conf(issuer=lti_session.lti_tool.issuer)
    launch_data_storage = DjangoCacheDataStorage()

    try:
        message_launch = DjangoMessageLaunch.from_cache(
            launch_id, request, tool_conf, launch_data_storage=launch_data_storage
        )
    except LtiException as exc:
        logger.warning(
            "Grade passback: launch cache miss for %s — %s. "
            "The LTI session may have expired. Score not sent.",
            launch_id, exc,
        )
        return JsonResponse(
            {
                'error': 'LTI launch data expired. '
                         'Grade passback must be done within the same session.',
                'detail': str(exc),
            },
            status=409,
        )

    if not message_launch.has_ags():
        return JsonResponse({'error': 'AGS not available for this launch'}, status=400)

    try:
        ags = message_launch.get_ags()
        grade = (
            Grade()
            .set_score_given(score_value)
            .set_score_maximum(1.0)
            .set_timestamp(timezone.now().isoformat())
            .set_activity_progress('Completed')
            .set_grading_progress('FullyGraded')
            .set_user_id(lti_session.user.lti_mapping.lti_user_id)
        )
        ags.put_grade(grade)
    except LtiException as exc:
        logger.exception("Grade passback failed for launch_id=%s: %s", launch_id, exc)
        return JsonResponse({'error': 'Grade passback failed', 'detail': str(exc)}, status=502)

    lti_session.is_completed = True
    lti_session.score = score_value
    lti_session.completed_at = timezone.now()
    lti_session.save(update_fields=['is_completed', 'score', 'completed_at'])

    logger.info(
        "Grade passback: user=%s launch=%s score=%.2f",
        request.user.username, launch_id, score_value,
    )
    return JsonResponse({'status': 'ok', 'score': score_value})


# ── Internal helpers ───────────────────────────────────────────────────────────

def _provision_user(
    lti_tool: LTITool,
    sub: str,
    email: str,
    given_name: str,
    family_name: str,
    full_name: str,
    roles: list,
) -> User:
    """
    Find the Django user linked to this Moodle identity, or create one.
    Updates cached profile fields on every launch.
    """
    try:
        mapping = LTIUserMapping.objects.select_related('django_user').get(
            lti_tool=lti_tool, lti_user_id=sub
        )
        # Refresh cached Moodle profile
        mapping.moodle_email = email
        mapping.moodle_full_name = full_name
        mapping.moodle_roles = roles
        mapping.save(update_fields=['moodle_email', 'moodle_full_name', 'moodle_roles', 'updated_at'])
        return mapping.django_user

    except LTIUserMapping.DoesNotExist:
        username = _unique_username(email, given_name, family_name)
        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=given_name[:30],
            last_name=family_name[:150],
        )
        LTIUserMapping.objects.create(
            django_user=user,
            lti_tool=lti_tool,
            lti_user_id=sub,
            moodle_email=email,
            moodle_full_name=full_name,
            moodle_roles=roles,
        )
        logger.info("LTI: provisioned new user %r for Moodle sub=%s", username, sub)
        return user


def _unique_username(email: str, given_name: str, family_name: str) -> str:
    """Derive a unique Django username from Moodle user info."""
    base = (
        email.split('@')[0]
        if email
        else (given_name + family_name).lower().replace(' ', '')
    )
    base = (base or 'ltiuser')[:30]
    username, counter = base, 1
    while User.objects.filter(username=username).exists():
        username = f"{base[:27]}_{counter}"
        counter += 1
    return username
