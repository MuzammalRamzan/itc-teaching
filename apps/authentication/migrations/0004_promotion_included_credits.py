from django.db import migrations, models


def seed_included_credits(apps, schema_editor):
    Promotion = apps.get_model('authentication', 'Promotion')
    defaults = {
        'promo': 2,
        'basic': 0,
        'ai': 10,
    }
    for plan, credits in defaults.items():
        Promotion.objects.filter(plan=plan).update(included_credits=credits)


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0003_seed_plan_packages'),
    ]

    operations = [
        migrations.AddField(
            model_name='promotion',
            name='included_credits',
            field=models.IntegerField(default=0),
        ),
        migrations.RunPython(seed_included_credits, migrations.RunPython.noop),
    ]
