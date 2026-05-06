from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='LTITool',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(help_text="Friendly label, e.g. 'University Moodle'", max_length=200)),
                ('issuer', models.URLField(help_text='Moodle site URL used as the LTI issuer, e.g. https://moodle.example.com', unique=True)),
                ('client_id', models.CharField(help_text='Client ID assigned by Moodle when registering the external tool', max_length=255)),
                ('deployment_ids', models.JSONField(default=list, help_text='Deployment IDs for this tool (from Moodle admin → External Tools)')),
                ('auth_login_url', models.URLField(help_text='Moodle OIDC authorisation endpoint (Site admin → Plugins → Authentication → LTI → Platform login URL)')),
                ('auth_token_url', models.URLField(help_text='Moodle OAuth 2.0 token endpoint (used for grade passback)')),
                ('key_set_url', models.URLField(help_text="Moodle JWKS endpoint — used to verify the platform's JWT signatures")),
                ('tool_private_key', models.TextField(help_text='RSA-2048 private key (PEM) used to sign Zentrol\'s JWTs')),
                ('tool_public_key', models.TextField(help_text="RSA-2048 public key (PEM) served at /moodle/lti/jwks/")),
                ('is_active', models.BooleanField(default=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'verbose_name': 'LTI Tool (Moodle Platform)',
                'verbose_name_plural': 'LTI Tools (Moodle Platforms)',
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='LTIUserMapping',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('lti_user_id', models.CharField(max_length=255)),
                ('moodle_email', models.EmailField(blank=True, max_length=254)),
                ('moodle_full_name', models.CharField(blank=True, max_length=255)),
                ('moodle_roles', models.JSONField(default=list, help_text='LTI roles from last launch')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('django_user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='lti_mapping', to=settings.AUTH_USER_MODEL)),
                ('lti_tool', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='user_mappings', to='moodle.ltitool')),
            ],
            options={
                'verbose_name': 'LTI User Mapping',
                'verbose_name_plural': 'LTI User Mappings',
                'unique_together': {('lti_tool', 'lti_user_id')},
            },
        ),
        migrations.CreateModel(
            name='LTISession',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('launch_id', models.CharField(db_index=True, max_length=255, unique=True)),
                ('course_id', models.CharField(blank=True, max_length=255)),
                ('course_title', models.CharField(blank=True, max_length=500)),
                ('resource_link_id', models.CharField(blank=True, max_length=255)),
                ('resource_link_title', models.CharField(blank=True, max_length=500)),
                ('ags_lineitems_url', models.URLField(blank=True, help_text='AGS lineitems container endpoint (for creating new line items)')),
                ('ags_lineitem_url', models.URLField(blank=True, help_text='AGS pre-created lineitem endpoint (for direct score submission)')),
                ('is_completed', models.BooleanField(default=False)),
                ('score', models.FloatField(blank=True, help_text='Score in [0.0, 1.0] sent back to Moodle gradebook', null=True)),
                ('completed_at', models.DateTimeField(blank=True, null=True)),
                ('launched_at', models.DateTimeField(auto_now_add=True)),
                ('lti_tool', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='sessions', to='moodle.ltitool')),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lti_sessions', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name': 'LTI Session',
                'verbose_name_plural': 'LTI Sessions',
                'ordering': ['-launched_at'],
            },
        ),
    ]
