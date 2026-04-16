from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0004_promotion_included_credits'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='free_credits_claimed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
