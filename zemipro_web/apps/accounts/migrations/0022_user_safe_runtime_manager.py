"""Record the runtime-only safe User manager without changing the schema."""
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [('accounts', '0021_public_content_snapshots')]

    operations = [
        migrations.AlterModelManagers(name='user', managers=[]),
    ]
