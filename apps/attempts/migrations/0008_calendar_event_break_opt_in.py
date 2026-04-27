import uuid
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attempts', '0007_writing_v2_feedback_fields'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='CalendarEvent',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('name', models.CharField(max_length=120)),
                ('starts_at', models.DateField()),
                ('ends_at', models.DateField()),
                ('accent', models.CharField(choices=[('green', 'Green'), ('orange', 'Orange'), ('blue', 'Blue'), ('purple', 'Purple'), ('red', 'Red')], default='green', max_length=10)),
                ('hint', models.CharField(blank=True, default='', max_length=60)),
                ('description', models.TextField(blank=True, default='')),
                ('recommended_minutes_per_day', models.IntegerField(default=0, help_text='0 = full rest, 15 = light review, 25 = adjusted hours')),
                ('is_active', models.BooleanField(default=True)),
                ('order', models.IntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'calendar_events',
                'ordering': ['order', 'starts_at'],
            },
        ),
        migrations.CreateModel(
            name='UserBreakOptIn',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('away', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('event', models.ForeignKey(on_delete=models.CASCADE, related_name='opt_ins', to='attempts.calendarevent')),
                ('user', models.ForeignKey(on_delete=models.CASCADE, related_name='break_opt_ins', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'user_break_opt_ins',
                'unique_together': {('user', 'event')},
            },
        ),
    ]
