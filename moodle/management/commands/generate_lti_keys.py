"""
Management command: generate_lti_keys

Generates an RSA-2048 key pair and creates (or updates) an LTITool record
so that Zentrol is ready to act as an LTI 1.3 tool provider.

Usage:
    python manage.py generate_lti_keys \
        --name "My University Moodle" \
        --issuer https://moodle.example.com \
        --client-id <client_id_from_moodle> \
        --auth-login-url https://moodle.example.com/mod/lti/auth.php \
        --auth-token-url https://moodle.example.com/mod/lti/token.php \
        --key-set-url https://moodle.example.com/mod/lti/certs.php \
        --deployment-ids dep1 dep2

Run without --issuer to only print a new key pair (useful for testing).
"""

import json

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = 'Generate an RSA-2048 key pair for LTI 1.3 and optionally register an LTITool.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--name', default='Moodle LTI Tool',
            help='Friendly name for the LTI tool record.',
        )
        parser.add_argument(
            '--issuer', default=None,
            help='Moodle site URL (issuer). If omitted, only prints the generated keys.',
        )
        parser.add_argument('--client-id', default='', dest='client_id')
        parser.add_argument('--auth-login-url', default='', dest='auth_login_url')
        parser.add_argument('--auth-token-url', default='', dest='auth_token_url')
        parser.add_argument('--key-set-url', default='', dest='key_set_url')
        parser.add_argument(
            '--deployment-ids', nargs='*', default=[],
            dest='deployment_ids',
            help='One or more deployment IDs (space-separated).',
        )
        parser.add_argument(
            '--update', action='store_true',
            help='Re-generate keys and update an existing LTITool record.',
        )

    def handle(self, *args, **options):
        try:
            from cryptography.hazmat.primitives import serialization
            from cryptography.hazmat.primitives.asymmetric import rsa
            from cryptography.hazmat.backends import default_backend
        except ImportError:
            raise CommandError(
                'The "cryptography" package is required. '
                'Install it with: pip install cryptography'
            )

        # ── Generate RSA-2048 key pair ─────────────────────────────────────────
        private_key = rsa.generate_private_key(
            public_exponent=65537,
            key_size=2048,
            backend=default_backend(),
        )
        private_pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ).decode()
        public_pem = private_key.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        ).decode()

        self.stdout.write(self.style.SUCCESS('\n── Generated RSA-2048 key pair ──'))
        self.stdout.write('\nPRIVATE KEY (keep secret — store in LTITool.tool_private_key):')
        self.stdout.write(private_pem)
        self.stdout.write('\nPUBLIC KEY (share with Moodle when registering the external tool):')
        self.stdout.write(public_pem)

        issuer = options['issuer']
        if not issuer:
            self.stdout.write(
                self.style.WARNING(
                    '\nNo --issuer supplied. Keys printed only — no database record created.\n'
                    'Re-run with --issuer to create/update an LTITool record.'
                )
            )
            return

        # ── Create or update the LTITool record ───────────────────────────────
        from moodle.models import LTITool

        defaults = {
            'tool_private_key': private_pem,
            'tool_public_key': public_pem,
            'client_id': options['client_id'],
            'auth_login_url': options['auth_login_url'],
            'auth_token_url': options['auth_token_url'],
            'key_set_url': options['key_set_url'],
            'deployment_ids': options['deployment_ids'],
        }

        if options['update']:
            tool, created = LTITool.objects.update_or_create(
                issuer=issuer,
                defaults={'name': options['name'], **defaults},
            )
        else:
            if LTITool.objects.filter(issuer=issuer).exists() and not options['update']:
                raise CommandError(
                    f'An LTITool for issuer={issuer!r} already exists. '
                    'Use --update to regenerate its keys.'
                )
            tool = LTITool.objects.create(name=options['name'], issuer=issuer, **defaults)
            created = True

        action = 'Created' if created else 'Updated'
        self.stdout.write(
            self.style.SUCCESS(f'\n{action} LTITool pk={tool.pk} name={tool.name!r}')
        )
        self.stdout.write(
            f'\nNext steps:\n'
            f'  1. In Moodle: Site admin → Plugins → External tools → Add tool\n'
            f'     Tool URL: <your-zentrol-host>/moodle/lti/config/\n'
            f'     (Moodle will auto-fill most fields from the config endpoint)\n'
            f'  2. Paste the PUBLIC KEY above into the Moodle "Public key" field.\n'
            f'  3. Copy the Client ID Moodle assigns and run:\n'
            f'     python manage.py generate_lti_keys --issuer {issuer} '
            f'--client-id <id> --update\n'
        )
