from datetime import timedelta

from django.db import migrations
from django.utils import timezone


def seed_plan_packages(apps, schema_editor):
    Promotion = apps.get_model('authentication', 'Promotion')

    defaults = [
        {
            'code': 'PROMO_TRIAL',
            'plan': 'promo',
            'price': '5.00',
            'is_active': True,
            'expires_at': timezone.now() + timedelta(days=30),
        },
        {
            'code': 'BASIC_PLAN',
            'plan': 'basic',
            'price': '50.00',
            'is_active': True,
            'expires_at': None,
        },
        {
            'code': 'AI_PLAN',
            'plan': 'ai',
            'price': '150.00',
            'is_active': True,
            'expires_at': None,
        },
    ]

    for item in defaults:
        Promotion.objects.update_or_create(
            plan=item['plan'],
            defaults=item,
        )


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0002_user_billing_fields'),
    ]

    operations = [
        migrations.RunPython(seed_plan_packages, migrations.RunPython.noop),
    ]
