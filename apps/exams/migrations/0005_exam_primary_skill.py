"""
Adds Exam.primary_skill so reading and writing exam libraries can live
side-by-side in the admin panel. Existing rows are backfilled by inspecting
which content they actually carry:

  • Has WritingQuestion → 'writing'
  • Else has ReadingPart with content → 'reading'
  • Else has SpeakingPart with content → 'speaking'
  • Else fall back to 'writing' (the historical default)
"""
from django.db import migrations, models


def backfill_primary_skill(apps, schema_editor):
    Exam = apps.get_model('exams', 'Exam')
    WritingQuestion = apps.get_model('exams', 'WritingQuestion')
    ReadingPart = apps.get_model('exams', 'ReadingPart')
    SpeakingPart = apps.get_model('exams', 'SpeakingPart')

    writing_ids = set(WritingQuestion.objects.values_list('exam_id', flat=True))
    reading_ids = set(
        ReadingPart.objects
        .filter(has_content=True)
        .values_list('exam_id', flat=True)
    )
    speaking_ids = set(
        SpeakingPart.objects
        .filter(has_content=True)
        .values_list('exam_id', flat=True)
    )

    for exam in Exam.objects.all().only('id'):
        if exam.id in writing_ids:
            exam.primary_skill = 'writing'
        elif exam.id in reading_ids:
            exam.primary_skill = 'reading'
        elif exam.id in speaking_ids:
            exam.primary_skill = 'speaking'
        else:
            exam.primary_skill = 'writing'
        exam.save(update_fields=['primary_skill'])


def noop_reverse(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0004_reading_5part_refresh'),
    ]

    operations = [
        migrations.AddField(
            model_name='exam',
            name='primary_skill',
            field=models.CharField(
                max_length=20,
                choices=[('writing', 'Writing'), ('reading', 'Reading'), ('speaking', 'Speaking')],
                default='writing',
            ),
        ),
        migrations.RunPython(backfill_primary_skill, noop_reverse),
    ]
