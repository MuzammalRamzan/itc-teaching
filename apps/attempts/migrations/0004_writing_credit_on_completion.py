from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attempts', '0003_speaking_usage_fields'),
    ]

    operations = [
        migrations.AddField(
            model_name='writingresponse',
            name='credits_charged',
            field=models.BooleanField(default=False),
        ),
    ]
