from django.db import migrations, models
import uuid


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Lip2SpeechInference',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('video_path', models.CharField(blank=True, max_length=512)),
                ('audio_path', models.CharField(blank=True, max_length=512)),
                ('num_frames', models.IntegerField(default=0)),
                ('mel_frames', models.IntegerField(default=0)),
                ('duration_seconds', models.FloatField(default=0.0)),
                ('processing_time_ms', models.FloatField(default=0.0)),
                ('status', models.CharField(
                    choices=[
                        ('pending', 'Pending'),
                        ('processing', 'Processing'),
                        ('success', 'Success'),
                        ('error', 'Error'),
                    ],
                    default='pending',
                    max_length=20,
                )),
                ('error_message', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Lip2Speech Inference',
                'verbose_name_plural': 'Lip2Speech Inferences',
                'ordering': ['-created_at'],
            },
        ),
    ]
