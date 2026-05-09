"""
Algolia search integration for the dashboard ⌘K "Jump to" search.

Design notes
------------
* Indexing is fully **opt-in**. If ``settings.ALGOLIA_ENABLED`` is False (the
  default — admin / app-id env vars unset), every public function in this
  module is a no-op. Production code never has to guard around it.
* Auto-sync is wired with Django ``post_save`` / ``post_delete`` signals from
  ``gestures.signals`` so the index stays consistent with the database
  without requiring application code to call us explicitly.
* Multi-tenancy is enforced with **secured API keys** scoped to a
  ``userID`` filter. Every browser session gets a short-lived key that can
  *only* return that user's own decks, even though search runs entirely
  client-side. The admin key never leaves the server.
* Failures here must NEVER break the main request. All write paths swallow
  network / auth errors and log a warning so the dashboard, upload, delete
  and favorite endpoints stay green even if Algolia is down.
"""

from __future__ import annotations

import logging
from typing import Any, Iterable

from django.conf import settings

logger = logging.getLogger(__name__)

# Cached lazily so importing this module never crashes when the package
# isn't installed and Algolia is disabled.
_client = None
_index = None


def is_enabled() -> bool:
    """Return True when Algolia is configured and ready to use."""
    return bool(getattr(settings, 'ALGOLIA_ENABLED', False))


def _get_client():
    """Return a cached Algolia ``SearchClient`` (admin key)."""
    global _client
    if _client is not None:
        return _client
    from algoliasearch.search_client import SearchClient
    _client = SearchClient.create(
        settings.ALGOLIA_APP_ID,
        settings.ALGOLIA_ADMIN_API_KEY,
    )
    return _client


def _get_index():
    """Return a cached index handle for the configured presentations index."""
    global _index
    if _index is not None:
        return _index
    _index = _get_client().init_index(settings.ALGOLIA_INDEX_NAME)
    return _index


def _ts(value) -> int | None:
    """Convert a ``datetime`` (or None) to a Unix timestamp for Algolia."""
    if value is None:
        return None
    try:
        return int(value.timestamp())
    except Exception:  # pragma: no cover — defensive
        return None


def serialize(asset) -> dict[str, Any]:
    """Build the Algolia record for a ``PresentationAsset``.

    The ``objectID`` is the asset UUID so save/delete are idempotent. ``userID``
    is indexed as a *filterable* attribute so we can constrain browser queries
    with a secured API key.
    """
    slides = asset.slides_json or []
    thumbnail_url = ''
    text_chunks: list[str] = []

    for slide in slides:
        if not isinstance(slide, dict):
            continue
        if not thumbnail_url and slide.get('imageUrl'):
            thumbnail_url = slide.get('imageUrl') or ''
        slide_text = (slide.get('text') or '').strip()
        if slide_text:
            text_chunks.append(slide_text)

    # Cap concatenated body to keep records small (Algolia hard limit is 100KB
    # per record on the free tier; 80KB is a safe budget for content).
    body = ' '.join(text_chunks)[:80_000]

    return {
        'objectID': str(asset.id),
        'userID': asset.user_id,
        'title': asset.title or '',
        'source_filename': asset.source_filename or '',
        'body': body,
        'thumbnail_url': thumbnail_url,
        'slide_count': asset.slide_count or 0,
        'is_favorite': bool(asset.is_favorite),
        'created_at_ts': _ts(asset.created_at),
        'updated_at_ts': _ts(asset.updated_at),
        'last_opened_at_ts': _ts(asset.last_opened_at),
    }


def index_asset(asset) -> None:
    """Push a single asset to Algolia. Best-effort; never raises."""
    if not is_enabled():
        return
    try:
        _get_index().save_object(serialize(asset))
    except Exception:
        logger.warning(
            "Algolia index_asset failed for asset_id=%s", asset.id, exc_info=True
        )


def delete_asset(asset) -> None:
    """Delete a single asset from Algolia. Best-effort; never raises."""
    if not is_enabled():
        return
    try:
        _get_index().delete_object(str(asset.id))
    except Exception:
        logger.warning(
            "Algolia delete_asset failed for asset_id=%s", asset.id, exc_info=True
        )


def bulk_reindex(assets: Iterable | None = None) -> int:
    """Push every (or a subset of) ``PresentationAsset`` records to Algolia.

    Used by the ``reindex_algolia`` management command for first-time setup
    or to recover from drift. Returns the number of records pushed.
    """
    if not is_enabled():
        return 0

    from .models import PresentationAsset

    if assets is None:
        assets = PresentationAsset.objects.all().iterator(chunk_size=200)

    index = _get_index()
    batch: list[dict[str, Any]] = []
    pushed = 0
    for asset in assets:
        batch.append(serialize(asset))
        if len(batch) >= 500:
            index.save_objects(batch)
            pushed += len(batch)
            batch = []
    if batch:
        index.save_objects(batch)
        pushed += len(batch)
    return pushed


def configure_index() -> None:
    """Apply searchable / ranking / faceting settings to the index.

    Idempotent — safe to run multiple times. Called by the reindex command
    and by tests, so the index works correctly out of the box.
    """
    if not is_enabled():
        return
    _get_index().set_settings({
        # Order matters: earlier attributes are weighted higher in ranking.
        'searchableAttributes': [
            'unordered(title)',
            'unordered(source_filename)',
            'unordered(body)',
        ],
        # ``filterOnly`` makes ``userID`` available for filters but not for
        # facet UI — that's exactly what multi-tenancy needs.
        'attributesForFaceting': [
            'filterOnly(userID)',
            'filterOnly(is_favorite)',
        ],
        # When two records tie on text relevance, prefer recently updated
        # decks, then favorites.
        'customRanking': [
            'desc(updated_at_ts)',
            'desc(is_favorite)',
        ],
        'attributesToHighlight': ['title', 'source_filename', 'body'],
        'attributesToSnippet': ['body:24'],
        'snippetEllipsisText': '…',
        'highlightPreTag': '<mark>',
        'highlightPostTag': '</mark>',
        'hitsPerPage': 8,
    })


def secured_search_key_for(user_id: int, ttl_seconds: int = 3600) -> str | None:
    """Mint a per-user search-only API key.

    The returned key can be safely embedded in HTML — it can ONLY query the
    configured index, can ONLY return records where ``userID == <user_id>``,
    and expires after ``ttl_seconds``. Returns ``None`` if Algolia is
    disabled OR no public ``ALGOLIA_SEARCH_API_KEY`` is configured (in which
    case the dashboard falls back to the static "first 6 decks" list).
    """
    if not is_enabled():
        return None
    parent_key = (getattr(settings, 'ALGOLIA_SEARCH_API_KEY', '') or '').strip()
    if not parent_key:
        return None
    try:
        import time
        from algoliasearch.search_client import SearchClient
        return SearchClient.generate_secured_api_key(
            parent_key,
            {
                'filters': f'userID:{int(user_id)}',
                'validUntil': int(time.time()) + int(ttl_seconds),
            },
        )
    except Exception:
        logger.warning(
            "Algolia secured_search_key_for failed for user_id=%s",
            user_id,
            exc_info=True,
        )
        return None
