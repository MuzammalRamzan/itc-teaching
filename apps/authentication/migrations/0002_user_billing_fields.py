from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='ai_credits',
            field=models.IntegerField(default=0),
        ),
        migrations.AddField(
            model_name='user',
            name='plan',
            field=models.CharField(choices=[('free', 'Free'), ('promo', 'Promo Trial'), ('basic', 'Basic Practice'), ('ai', 'AI Practice')], default='free', max_length=20),
        ),
        migrations.AddField(
            model_name='user',
            name='plan_purchased_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='Promotion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=100, unique=True)),
                ('plan', models.CharField(choices=[('free', 'Free'), ('promo', 'Promo Trial'), ('basic', 'Basic Practice'), ('ai', 'AI Practice')], default='promo', max_length=20)),
                ('price', models.DecimalField(decimal_places=2, max_digits=8)),
                ('is_active', models.BooleanField(default=True)),
                ('expires_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'db_table': 'promotions',
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PaymentRecord',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('kind', models.CharField(choices=[('plan', 'Plan'), ('credits', 'Credits')], max_length=20)),
                ('target_plan', models.CharField(blank=True, choices=[('free', 'Free'), ('promo', 'Promo Trial'), ('basic', 'Basic Practice'), ('ai', 'AI Practice')], default='', max_length=20)),
                ('credits_amount', models.IntegerField(default=0)),
                ('amount_sar', models.DecimalField(decimal_places=2, max_digits=8)),
                ('currency', models.CharField(default='sar', max_length=10)),
                ('stripe_session_id', models.CharField(blank=True, max_length=255, null=True, unique=True)),
                ('stripe_payment_intent', models.CharField(blank=True, default='', max_length=255)),
                ('status', models.CharField(choices=[('pending', 'Pending'), ('completed', 'Completed'), ('failed', 'Failed'), ('expired', 'Expired')], default='pending', max_length=20)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('applied_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='payment_records', to='authentication.user')),
            ],
            options={
                'db_table': 'payment_records',
                'ordering': ['-created_at'],
            },
        ),
    ]
