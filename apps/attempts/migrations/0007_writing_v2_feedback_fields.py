from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('attempts', '0006_writingresponse_submission_group_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='writingresponse',
            name='student_level',
            field=models.CharField(blank=True, default='', max_length=4),
        ),
        migrations.AddField(
            model_name='writingresponse',
            name='potential_score',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='writingresponse',
            name='well_done',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='writingresponse',
            name='practice_task',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='writingresponse',
            name='feedback_json',
            field=models.JSONField(blank=True, default=dict, null=True),
        ),
    ]
