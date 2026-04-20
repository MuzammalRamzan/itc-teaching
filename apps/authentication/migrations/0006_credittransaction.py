from django.db import migrations, models
import django.db.models.deletion
import uuid


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0005_user_free_credits_claimed_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='CreditTransaction',
            fields=[
                ('id', models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('entry_type', models.CharField(choices=[('debit', 'Debit'), ('credit', 'Credit')], max_length=20)),
                ('delta', models.IntegerField()),
                ('balance_after', models.IntegerField(default=0)),
                ('description', models.CharField(max_length=255)),
                ('source_type', models.CharField(blank=True, default='', max_length=50)),
                ('source_id', models.CharField(blank=True, default='', max_length=100)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='credit_transactions', to='authentication.user')),
            ],
            options={
                'db_table': 'credit_transactions',
                'ordering': ['-created_at'],
            },
        ),
    ]
