from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attempts', '0005_examattempt_bypass_ai_credits'),
    ]

    operations = [
        migrations.AddField(
            model_name='writingresponse',
            name='submission_group_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
    ]
