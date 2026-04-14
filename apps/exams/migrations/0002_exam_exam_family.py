from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='exam',
            name='exam_family',
            field=models.CharField(
                choices=[('general', 'General'), ('fet', 'FET')],
                default='general',
                max_length=20,
            ),
        ),
    ]
