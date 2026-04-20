from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0006_credittransaction'),
    ]

    operations = [
        migrations.CreateModel(
            name='PricingPackageContent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('product_key', models.CharField(max_length=50, unique=True)),
                ('kind', models.CharField(default='plan', max_length=20)),
                ('title_ar', models.CharField(blank=True, default='', max_length=200)),
                ('title_en', models.CharField(blank=True, default='', max_length=200)),
                ('subtitle_ar', models.CharField(blank=True, default='', max_length=200)),
                ('subtitle_en', models.CharField(blank=True, default='', max_length=200)),
                ('hook_ar', models.TextField(blank=True, default='')),
                ('hook_en', models.TextField(blank=True, default='')),
                ('description_ar', models.TextField(blank=True, default='')),
                ('description_en', models.TextField(blank=True, default='')),
                ('cta_ar', models.CharField(blank=True, default='', max_length=200)),
                ('cta_en', models.CharField(blank=True, default='', max_length=200)),
                ('features_ar', models.JSONField(blank=True, default=list)),
                ('features_en', models.JSONField(blank=True, default=list)),
                ('badge_ar', models.CharField(blank=True, default='', max_length=120)),
                ('badge_en', models.CharField(blank=True, default='', max_length=120)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'pricing_package_contents',
                'ordering': ['product_key'],
            },
        ),
    ]
