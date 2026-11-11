"""Stage 01 security fix: durable shared POST counters, no existing data changes."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0002_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='SensitivePostCounter',
            fields=[
                ('bucket_hash', models.CharField(max_length=64, primary_key=True, serialize=False)),
                ('attempts', models.PositiveIntegerField(default=0)),
                ('expires_at', models.DateTimeField(db_index=True)),
            ],
            options={'db_table': 'accounts_sensitive_post_counter'},
        ),
    ]
