from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('gestures', '0004_userprofile'),
    ]

    operations = [
        migrations.AddField(
            model_name='presentationasset',
            name='last_opened_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name='presentationasset',
            index=models.Index(
                fields=['user', 'last_opened_at'],
                name='gest_pr_usr_last_open_idx',
            ),
        ),
    ]
