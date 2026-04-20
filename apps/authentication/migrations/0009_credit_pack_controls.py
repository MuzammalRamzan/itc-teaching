from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0008_seed_pricing_package_content'),
    ]

    operations = [
        migrations.AddField(
            model_name='pricingpackagecontent',
            name='credits_override',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='pricingpackagecontent',
            name='is_active',
            field=models.BooleanField(default=True),
        ),
        migrations.AddField(
            model_name='pricingpackagecontent',
            name='price_override',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=8, null=True),
        ),
    ]
