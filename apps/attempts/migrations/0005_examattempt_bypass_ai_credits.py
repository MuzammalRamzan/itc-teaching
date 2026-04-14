from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attempts', '0004_writing_credit_on_completion'),
    ]

    operations = [
        migrations.AddField(
            model_name='examattempt',
            name='bypass_ai_credits',
            field=models.BooleanField(default=False),
        ),
    ]
