from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0010_landing_page_setting'),
    ]

    operations = [
        migrations.AddField(
            model_name='landingpagesetting',
            name='writing_enabled',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='landingpagesetting',
            name='reading_enabled',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='landingpagesetting',
            name='speaking_enabled',
            field=models.BooleanField(default=False),
        ),
    ]
