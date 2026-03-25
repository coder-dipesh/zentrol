import json
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

import fitz
from PIL import Image
from django.conf import settings
from django.core.files.base import ContentFile
from django.contrib import messages
from django.core.validators import ValidationError, validate_email
from django.db.models import DateTimeField
from django.db.models.functions import Coalesce
from django.utils import timezone
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.http import HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from urllib.parse import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action, api_view, permission_classes, throttle_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import GestureLog, PresentationAsset, PresentationSession, UserProfile
from .serializers import GestureLogSerializer
from .throttles import GestureLogAnonThrottle


def _redirect_dashboard_preserving_workspace(request):
    """After account POST, return to the same dashboard filter/view (no open redirects)."""
    q = {}
    f = (request.POST.get('return_filter') or '').strip()
    if f in {'all', 'recent', 'created', 'favorites'}:
        q['filter'] = f
    v = (request.POST.get('return_view') or '').strip()
    if v in {'grid', 'list'}:
        q['view'] = v
    url = reverse('dashboard')
    if q:
        url = f'{url}?{urlencode(q)}'
    return redirect(url)


def _build_media_url(path: Path) -> str:
    rel = path.relative_to(settings.MEDIA_ROOT).as_posix()
    return f"{settings.MEDIA_URL.rstrip('/')}/{rel}"


def _get_user_active_sessions(request):
    """
    Return active (non-expired) DB-backed sessions for the current user.
    Used by Account -> Security -> Devices and sessions.
    """
    if settings.SESSION_ENGINE != 'django.contrib.sessions.backends.db':
        return []

    from django.contrib.sessions.models import Session

    current_key = request.session.session_key
    now = timezone.now()
    sessions = []
    for s in Session.objects.filter(expire_date__gt=now):
        try:
            data = s.get_decoded()
            uid = data.get('_auth_user_id')
            if uid is None or str(uid) != str(request.user.pk):
                continue
        except Exception:
            continue

        # We may not have user-agent/ip info in your current session payload,
        # but the list still shows session key + expiry.
        label = data.get('user_agent') or data.get('browser') or data.get('device') or 'Session'
        sessions.append({
            'session_key': s.session_key,
            'expire_date': s.expire_date,
            'is_current': current_key and s.session_key == current_key,
            'label': label,
        })

    # Sort by most recent expiry (best-effort)
    sessions.sort(key=lambda x: x.get('expire_date') or now, reverse=True)
    return sessions


def _resolve_soffice_binary() -> str:
    candidates = [
        shutil.which('soffice'),
        '/Applications/LibreOffice.app/Contents/MacOS/soffice',
        '/usr/local/bin/soffice',
        '/opt/homebrew/bin/soffice',
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return candidate
    raise RuntimeError('LibreOffice is not installed. Please install it so server-side slide rendering can run.')


def _render_slides_with_libreoffice(uploaded_file, user_id, asset_id):
    media_root = Path(settings.MEDIA_ROOT)
    media_root.mkdir(parents=True, exist_ok=True)
    output_dir = media_root / 'presentations' / str(user_id) / str(asset_id)
    output_dir.mkdir(parents=True, exist_ok=True)

    original_name = Path(uploaded_file.name or 'presentation.pptx').name
    suffix = Path(original_name).suffix or '.pptx'

    with tempfile.TemporaryDirectory(prefix='zentrol-pptx-') as tmp_dir:
        tmp_path = Path(tmp_dir)
        input_path = tmp_path / f"input{suffix}"
        pdf_path = tmp_path / 'deck.pdf'
        with input_path.open('wb+') as dst:
            for chunk in uploaded_file.chunks():
                dst.write(chunk)

        soffice_bin = _resolve_soffice_binary()
        command = [
            soffice_bin,
            '--headless',
            '--convert-to',
            'pdf',
            '--outdir',
            str(tmp_path),
            str(input_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as exc:
            stderr = (exc.stderr or '').strip()
            raise RuntimeError(f'LibreOffice conversion failed: {stderr or "unknown error"}') from exc

        if not pdf_path.exists():
            # LibreOffice can name output after the input file stem.
            alt_pdf = tmp_path / f'{input_path.stem}.pdf'
            if alt_pdf.exists():
                pdf_path = alt_pdf
            else:
                raise RuntimeError('LibreOffice did not produce a PDF for slide export.')

        slides = []
        doc = fitz.open(pdf_path)
        if doc.page_count == 0:
            raise RuntimeError('Converted PDF has no pages.')

        for index in range(doc.page_count):
            page = doc.load_page(index)
            # 2x zoom gives crisp slide previews while keeping size reasonable.
            pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            extracted_text = (page.get_text('text') or '').strip()
            if extracted_text:
                extracted_text = ' '.join(extracted_text.split())
            target_name = f"slide-{index + 1:03d}.png"
            target_path = output_dir / target_name
            pix.save(str(target_path))
            slides.append({
                'imageUrl': _build_media_url(target_path),
                'text': extracted_text[:20000],
                'notes': '',
            })
        doc.close()
    return slides


def home(request):
    """Home page with demo upload."""
    return render(request, 'home.html', {'demo_available': True})


def register_view(request):
    """Register a new user account."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            return redirect('dashboard')
    else:
        form = UserCreationForm()

    return render(request, 'auth/register.html', {'form': form})


@never_cache
@login_required
def dashboard_view(request):
    """Dashboard-style workspace with persisted presentations."""
    view_mode = request.GET.get('view', 'grid')
    if view_mode not in {'grid', 'list'}:
        view_mode = 'grid'
    active_filter = request.GET.get('filter', 'all')
    if active_filter not in {'all', 'recent', 'created', 'favorites'}:
        active_filter = 'all'

    assets = PresentationAsset.objects.filter(user=request.user)
    if active_filter == 'favorites':
        assets = assets.filter(is_favorite=True)

    if active_filter == 'recent':
        # Sort by last time the deck was opened; fall back to last modified until first open.
        assets = assets.annotate(
            _recent_sort=Coalesce('last_opened_at', 'updated_at', output_field=DateTimeField())
        ).order_by('-_recent_sort')
    elif active_filter == 'created':
        assets = assets.order_by('-created_at')
    else:
        assets = assets.order_by('-updated_at')

    user_profile, _ = UserProfile.objects.get_or_create(user=request.user)
    user_sessions = _get_user_active_sessions(request)
    return render(request, 'dashboard.html', {
        'assets': assets,
        'view_mode': view_mode,
        'active_filter': active_filter,
        'user_profile': user_profile,
        'user_sessions': user_sessions,
    })


@login_required
@require_POST
def update_account_profile(request):
    """Update basic profile fields and optional avatar from Account settings modal."""
    user = request.user
    profile, _ = UserProfile.objects.get_or_create(user=user)
    user.first_name = (request.POST.get('first_name') or '')[:150]
    user.last_name = (request.POST.get('last_name') or '')[:150]
    email = (request.POST.get('email') or '').strip()
    if not email:
        messages.error(request, 'Email is required.')
        return _redirect_dashboard_preserving_workspace(request)
    try:
        validate_email(email)
    except ValidationError:
        messages.error(request, 'Please enter a valid email address.')
        return _redirect_dashboard_preserving_workspace(request)
    user.email = email
    user.save(update_fields=['first_name', 'last_name', 'email'])

    avatar_file = request.FILES.get('avatar')
    if avatar_file:
        max_bytes = 2 * 1024 * 1024
        ext = Path(avatar_file.name).suffix.lower()
        if ext not in {'.jpg', '.jpeg', '.png', '.webp', '.gif'}:
            messages.error(request, 'Please upload a JPG, PNG, WebP, or GIF image.')
            return _redirect_dashboard_preserving_workspace(request)
        try:
            data = avatar_file.read()
            img = Image.open(BytesIO(data))
            img.load()
        except Exception:
            messages.error(request, 'Could not read that image. Try another file.')
            return _redirect_dashboard_preserving_workspace(request)

        # Compress oversized avatars instead of rejecting them.
        if len(data) > max_bytes:
            try:
                # Flatten transparency (PNG/GIF) onto white background for JPEG.
                if img.mode in {'RGBA', 'LA'} or (img.mode == 'P' and 'transparency' in img.info):
                    background = Image.new('RGB', img.size, (255, 255, 255))
                    if img.mode in {'RGBA', 'LA'}:
                        background.paste(img, mask=img.split()[-1])
                    else:
                        background.paste(img.convert('RGBA'), mask=img.convert('RGBA').split()[-1])
                    img = background
                else:
                    img = img.convert('RGB')

                compress_targets = [
                    (512, 75),
                    (512, 60),
                    (512, 45),
                    (384, 60),
                    (384, 45),
                    (256, 45),
                ]

                compressed_bytes = None
                for max_dim, quality in compress_targets:
                    tmp = img.copy()
                    tmp.thumbnail((max_dim, max_dim))
                    out = BytesIO()
                    tmp.save(out, format='JPEG', quality=quality, optimize=True)
                    if out.tell() <= max_bytes:
                        compressed_bytes = out.getvalue()
                        ext = '.jpg'
                        break

                if not compressed_bytes:
                    messages.error(request, 'Could not compress profile photo under 2 MB.')
                    return _redirect_dashboard_preserving_workspace(request)

                data = compressed_bytes
            except Exception:
                messages.error(request, 'Profile photo was too large and could not be compressed.')
                return _redirect_dashboard_preserving_workspace(request)

        safe_name = f'{user.pk}_{uuid.uuid4().hex}{ext}'
        if profile.avatar:
            profile.avatar.delete(save=False)
        profile.avatar.save(safe_name, ContentFile(data), save=True)

    messages.success(request, 'Profile updated.')
    return _redirect_dashboard_preserving_workspace(request)


@login_required
@require_POST
def logout_all_sessions_view(request):
    """Delete other database sessions for this user (keeps current session)."""
    if settings.SESSION_ENGINE != 'django.contrib.sessions.backends.db':
        messages.warning(
            request,
            'Sign out everywhere is not available with the current session storage.',
        )
        return redirect('dashboard')
    from django.contrib.sessions.models import Session

    current_key = request.session.session_key
    deleted = 0
    for s in Session.objects.exclude(session_key=current_key):
        try:
            data = s.get_decoded()
            uid = data.get('_auth_user_id')
            if uid is not None and str(request.user.pk) == str(uid):
                s.delete()
                deleted += 1
        except Exception:
            continue
    request.session.cycle_key()
    if deleted:
        messages.success(request, f'Signed out of {deleted} other session(s).')
    else:
        messages.info(request, 'No other active sessions were found.')
    return redirect('dashboard')


@login_required
@require_POST
def logout_single_session_view(request, session_key):
    """
    Delete a single active session for the current user.
    This is used by Account -> Security -> Devices and sessions.
    """
    if settings.SESSION_ENGINE != 'django.contrib.sessions.backends.db':
        messages.warning(
            request,
            'Sign out from individual sessions is not available with the current session storage.',
        )
        return redirect('dashboard')

    from django.contrib.sessions.models import Session

    current_key = request.session.session_key
    if session_key == current_key:
        # User removed the current device; log them out.
        logout(request)
        messages.info(request, 'You have been signed out.')
        return redirect('home')

    try:
        s = Session.objects.get(session_key=session_key)
    except Session.DoesNotExist:
        messages.error(request, 'That session no longer exists.')
        return redirect('dashboard')

    try:
        data = s.get_decoded()
        uid = data.get('_auth_user_id')
        if uid is None or str(uid) != str(request.user.pk):
            messages.error(request, 'You cannot modify this session.')
            return redirect('dashboard')
    except Exception:
        # If decoding fails, don't delete.
        messages.error(request, 'Could not verify that session.')
        return redirect('dashboard')

    s.delete()
    messages.success(request, 'Session removed.')
    return redirect('dashboard')


@login_required
@require_POST
def delete_account_view(request):
    """Permanently delete the signed-in user and related data."""
    if request.POST.get('confirm_delete') != '1':
        messages.error(request, 'Account deletion was not confirmed.')
        return redirect('dashboard')
    user = request.user
    logout(request)
    user.delete()
    messages.info(request, 'Your Zentrol account has been deleted.')
    return redirect('home')


def presentation_view(request):
    """Main presentation view (Django template + static JS)."""
    session_id = request.GET.get('session_id', str(uuid.uuid4()))
    initial_slides = []
    initial_asset_title = ''

    asset_id = request.GET.get('asset')
    if asset_id and request.user.is_authenticated:
        asset = get_object_or_404(PresentationAsset, id=asset_id, user=request.user)
        initial_slides = asset.slides_json or []
        initial_asset_title = asset.title
        PresentationAsset.objects.filter(pk=asset.pk).update(last_opened_at=timezone.now())

    PresentationSession.objects.get_or_create(
        session_id=session_id,
        defaults={'user': request.user if request.user.is_authenticated else None},
    )

    return render(request, 'presentation.html', {
        'session_id': session_id,
        'is_authenticated': request.user.is_authenticated,
        'initial_slides': initial_slides,
        'initial_asset_title': initial_asset_title,
    })


def test_view(request):
    return render(request, 'test_mediapipe.html')


@login_required
def upload_presentation(request):
    """Persist a presentation uploaded from dashboard."""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')

    uploaded_file = request.FILES.get('presentation')
    if uploaded_file is not None:
        filename = (uploaded_file.name or '').lower()
        if not (filename.endswith('.pptx') or filename.endswith('.ppt')):
            return JsonResponse({'ok': False, 'error': 'Only .ppt and .pptx files are supported'}, status=400)

        source_filename = Path(uploaded_file.name or '').name[:255]
        title = Path(source_filename).stem[:255] or 'Untitled presentation'
        asset = PresentationAsset.objects.create(
            user=request.user,
            title=title,
            source_filename=source_filename,
            slides_json=[],
            slide_count=0,
        )

        try:
            slides = _render_slides_with_libreoffice(uploaded_file, request.user.id, asset.id)
        except Exception as exc:
            asset.delete()
            return JsonResponse({'ok': False, 'error': str(exc)}, status=400)

        asset.slides_json = slides
        asset.slide_count = len(slides)
        asset.save(update_fields=['slides_json', 'slide_count', 'updated_at'])
        return JsonResponse({'ok': True, 'asset_id': str(asset.id)})

    # Backward-compatible JSON fallback
    raw_body = request.body or b''
    try:
        data = json.loads(raw_body.decode('utf-8', errors='replace')) if raw_body else {}
    except Exception as exc:
        return JsonResponse({'ok': False, 'error': f'Invalid payload: {exc}'}, status=400)

    slides = data.get('slides') or []
    if not isinstance(slides, list) or not slides:
        return JsonResponse({'ok': False, 'error': 'No slides provided'}, status=400)

    source_filename = str(data.get('source_filename') or '').strip()[:255]
    title = str(data.get('title') or source_filename or 'Untitled presentation').strip()[:255] or 'Untitled presentation'

    normalized = []
    for slide in slides:
        if isinstance(slide, dict):
            normalized.append({
                'imageUrl': slide.get('imageUrl') or None,
                'text': (slide.get('text') or '')[:20000],
                'notes': (slide.get('notes') or '')[:20000],
            })

    if not normalized:
        return JsonResponse({'ok': False, 'error': 'No valid slides provided'}, status=400)

    asset = PresentationAsset.objects.create(
        user=request.user,
        title=title,
        source_filename=source_filename,
        slides_json=normalized,
        slide_count=len(normalized),
    )
    return JsonResponse({'ok': True, 'asset_id': str(asset.id)})


@login_required
def delete_presentation(request, asset_id):
    """Delete a presentation owned by the current user."""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')

    asset = get_object_or_404(PresentationAsset, id=asset_id, user=request.user)
    media_dir = Path(settings.MEDIA_ROOT) / 'presentations' / str(request.user.id) / str(asset.id)
    if media_dir.exists():
        shutil.rmtree(media_dir, ignore_errors=True)
    asset.delete()
    return JsonResponse({'ok': True})


@login_required
def toggle_favorite(request, asset_id):
    """Toggle favorite flag for a presentation owned by current user."""
    if request.method != 'POST':
        return HttpResponseBadRequest('POST required')

    asset = get_object_or_404(PresentationAsset, id=asset_id, user=request.user)
    asset.is_favorite = not asset.is_favorite
    asset.save(update_fields=['is_favorite', 'updated_at'])
    return JsonResponse({'ok': True, 'is_favorite': asset.is_favorite})


@extend_schema(
    summary='Log gesture (anonymous)',
    description='Used by static gesture scripts. Throttled; optional shared secret.',
    tags=['Gestures'],
)
@api_view(['POST'])
@permission_classes([AllowAny])
@throttle_classes([GestureLogAnonThrottle])
def api_log_gesture(request):
    """Log gesture detection — not for direct public abuse: throttle + optional shared secret."""
    secret = getattr(settings, 'GESTURE_LOG_SHARED_SECRET', '') or ''
    if secret:
        got = request.headers.get('X-Zentrol-Gesture-Log-Secret', '')
        if got != secret:
            return Response({'status': 'error', 'message': 'Forbidden'}, status=status.HTTP_403_FORBIDDEN)

    try:
        data = request.data
        if not isinstance(data, dict):
            data = {}

        gesture_type = data.get('gesture_type') or data.get('action') or 'unknown'

        log = GestureLog.objects.create(
            user=request.user if request.user.is_authenticated else None,
            session_id=data.get('session_id', 'anonymous'),
            gesture_type=gesture_type,
            confidence=float(data.get('confidence', 0.0)),
            frame_count=int(data.get('frame_count', 1)),
            hand_x=data.get('hand_x'),
            hand_y=data.get('hand_y'),
            hand_z=data.get('hand_z'),
            detection_time_ms=float(data.get('detection_time_ms', 0.0)),
            frame_processing_time_ms=float(data.get('frame_processing_time_ms', 0.0)),
            browser=data.get('browser', ''),
            user_agent=request.META.get('HTTP_USER_AGENT', ''),
            screen_resolution=data.get('screen_resolution', ''),
        )

        sid = data.get('session_id')
        if sid:
            try:
                session = PresentationSession.objects.get(session_id=sid)
                session.gesture_count += 1
                session.last_activity = datetime.now()
                session.save()
            except PresentationSession.DoesNotExist:
                pass

        return Response({'status': 'success', 'log_id': str(log.id)})

    except (TypeError, ValueError) as e:
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    except Exception as e:
        return Response({'status': 'error', 'message': str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

# REST API Views
class GestureLogViewSet(viewsets.ModelViewSet):
    """REST API for gesture logs"""
    queryset = GestureLog.objects.all().order_by('-created_at')
    serializer_class = GestureLogSerializer
    permission_classes = [permissions.IsAuthenticated]
    
    @action(detail=False, methods=['get'])
    def session_stats(self, request):
        """Get statistics for a session"""
        session_id = request.query_params.get('session_id')
        if not session_id:
            return Response({'error': 'session_id required'}, status=400)
        
        logs = self.queryset.filter(session_id=session_id)
        total = logs.count()
        
        stats = {
            'total_gestures': total,
            'gesture_types': {},
            'avg_confidence': 0,
            'avg_latency': 0,
        }
        
        if total > 0:
            for log in logs:
                stats['gesture_types'][log.gesture_type] = stats['gesture_types'].get(log.gesture_type, 0) + 1
            
            stats['avg_confidence'] = sum(log.confidence for log in logs) / total
            stats['avg_latency'] = sum(log.detection_time_ms for log in logs) / total
        
        return Response(stats)


@extend_schema(
    summary='Health check',
    description='Liveness probe for the API (no database access).',
    tags=['Health'],
)
@api_view(['GET'])
@permission_classes([AllowAny])
def api_v1_health(request):
    """Lightweight health check for load balancers (no DB hit)."""
    # This is a minimal, fast API health check endpoint (no DB hit).
    # Add any additional quick non-DB checks here if needed in future.
    return Response({
        'status': 'ok',
        'service': 'zentrol-api',
        'version': '1',
    })
