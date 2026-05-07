from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0011_landing_section_toggles'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='plan_expires_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
