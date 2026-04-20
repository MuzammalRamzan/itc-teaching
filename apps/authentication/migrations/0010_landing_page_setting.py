from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0009_credit_pack_controls'),
    ]

    operations = [
        migrations.CreateModel(
            name='LandingPageSetting',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('app_key', models.CharField(choices=[('its', 'ITS'), ('fet', 'FET')], max_length=20, unique=True)),
                ('countdown_enabled', models.BooleanField(default=False)),
                ('countdown_target', models.DateTimeField(blank=True, null=True)),
                ('hero_badge_ar', models.CharField(blank=True, default='', max_length=200)),
                ('hero_badge_en', models.CharField(blank=True, default='', max_length=200)),
                ('hero_title_ar', models.CharField(blank=True, default='', max_length=255)),
                ('hero_title_en', models.CharField(blank=True, default='', max_length=255)),
                ('hero_subtitle_ar', models.TextField(blank=True, default='')),
                ('hero_subtitle_en', models.TextField(blank=True, default='')),
                ('primary_cta_ar', models.CharField(blank=True, default='', max_length=200)),
                ('primary_cta_en', models.CharField(blank=True, default='', max_length=200)),
                ('secondary_cta_ar', models.CharField(blank=True, default='', max_length=200)),
                ('secondary_cta_en', models.CharField(blank=True, default='', max_length=200)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={
                'db_table': 'landing_page_settings',
                'ordering': ['app_key'],
            },
        ),
    ]
