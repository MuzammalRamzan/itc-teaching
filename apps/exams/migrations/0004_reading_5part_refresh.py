"""
Wipes legacy reading data and updates ReadingPart.part_number choices to the
new 5-part layout (Signs / Gap Fill / Text Matching / People ↔ Place / Long
Reading). Old shapes for parts 2/3/4/5 do not match the new content schema,
and part 6 (Open Cloze) was removed entirely — admins must re-upload reading
exams in the new JSON format after this migration runs.

Side effects:
  • Deletes ALL ReadingPart rows.
  • Deletes ALL ReadingResponse rows (foreign-keyed reading attempts).
"""
from django.db import migrations, models


def wipe_reading_data(apps, schema_editor):
    ReadingPart = apps.get_model('exams', 'ReadingPart')
    ReadingResponse = apps.get_model('attempts', 'ReadingResponse')
    ReadingResponse.objects.all().delete()
    ReadingPart.objects.all().delete()


def noop_reverse(apps, schema_editor):
    # No reverse — once wiped, legacy content can't be reconstructed.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('exams', '0003_exam_is_deleted'),
        ('attempts', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(wipe_reading_data, noop_reverse),
        migrations.AlterField(
            model_name='readingpart',
            name='part_number',
            field=models.IntegerField(choices=[
                (1, 'Signs & Notices'),
                (2, 'Gap Fill'),
                (3, 'Text Matching'),
                (4, 'People ↔ Place'),
                (5, 'Long Reading'),
            ]),
        ),
    ]
