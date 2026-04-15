import uuid
from pathlib import Path

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _avatar_upload_to(instance, filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp', '.gif'):
        ext = '.jpg'
    return f'avatars/{instance.user_id}/{uuid.uuid4().hex}{ext}'


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('gestures', '0003_presentationasset_is_favorite_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='UserProfile',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('avatar', models.ImageField(blank=True, null=True, upload_to=_avatar_upload_to)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='profile', to=settings.AUTH_USER_MODEL)),
            ],
        ),
    ]
