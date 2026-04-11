from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attempts', '0002_refund_flags'),
    ]

    operations = [
        migrations.AddField(
            model_name='examattempt',
            name='speaking_chat_credit_charged',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='speakingresponse',
            name='credits_charged',
            field=models.IntegerField(default=2),
        ),
    ]
