"""
Auto-sync ``PresentationAsset`` rows into Algolia.

Wired from :class:`gestures.apps.GesturesConfig.ready` so it runs once per
process. Both handlers are no-ops when Algolia is disabled, and never raise
— failures are logged inside ``algolia.index_asset`` / ``algolia.delete_asset``.
"""

from __future__ import annotations

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from . import algolia
from .models import PresentationAsset


@receiver(post_save, sender=PresentationAsset)
def _algolia_sync_on_save(sender, instance: PresentationAsset, **_kwargs) -> None:
    if not algolia.is_enabled():
        return
    algolia.index_asset(instance)


@receiver(post_delete, sender=PresentationAsset)
def _algolia_sync_on_delete(sender, instance: PresentationAsset, **_kwargs) -> None:
    if not algolia.is_enabled():
        return
    algolia.delete_asset(instance)
