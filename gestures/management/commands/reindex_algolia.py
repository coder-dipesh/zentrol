"""
Push every PresentationAsset row to Algolia and (re)apply index settings.

Usage::

    python manage.py reindex_algolia

Run this once after first configuring Algolia (so existing decks become
searchable), and any time you suspect drift between the database and the
remote index. Day-to-day changes are kept in sync automatically by the
``post_save`` / ``post_delete`` signals registered in ``gestures.apps``.
"""

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from gestures import algolia
from gestures.models import PresentationAsset


class Command(BaseCommand):
    help = (
        "Push every PresentationAsset to Algolia and (re)apply index "
        "settings. Requires ALGOLIA_APP_ID and ALGOLIA_ADMIN_API_KEY."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--user',
            type=int,
            default=None,
            help='Optional user ID — only reindex decks owned by this user.',
        )
        parser.add_argument(
            '--skip-settings',
            action='store_true',
            help='Skip applying index settings (searchable attributes, etc).',
        )

    def handle(self, *args, **options):
        if not algolia.is_enabled():
            raise CommandError(
                "Algolia is not configured. Set ALGOLIA_APP_ID and "
                "ALGOLIA_ADMIN_API_KEY in your environment, then re-run."
            )

        index_name = settings.ALGOLIA_INDEX_NAME
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"Reindexing Algolia index '{index_name}'"
            )
        )

        if not options['skip_settings']:
            self.stdout.write(' • applying index settings…', ending='')
            algolia.configure_index()
            self.stdout.write(self.style.SUCCESS(' ok'))

        qs = PresentationAsset.objects.all()
        user_id = options.get('user')
        if user_id:
            qs = qs.filter(user_id=user_id)
            self.stdout.write(f' • restricted to user_id={user_id}')

        total = qs.count()
        self.stdout.write(f' • pushing {total} record(s)…', ending='')
        pushed = algolia.bulk_reindex(qs.iterator(chunk_size=200))
        self.stdout.write(self.style.SUCCESS(f' pushed {pushed}'))

        self.stdout.write(self.style.SUCCESS('Algolia reindex complete.'))
