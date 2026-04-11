from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attempts', '0002_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='writingresponse',
            name='credits_refunded',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='speakingresponse',
            name='credits_refunded',
            field=models.BooleanField(default=False),
        ),
    ]
