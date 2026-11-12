"""Stage 03.1: retain the legacy role and select the matching dashboard."""
from django.db import migrations, models


def migrate_legacy_role(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    # No profile is created or deleted: empty worker profiles must not become
    # public merely because an old role value was 'worker'. Existing OneToOne
    # constraints already disallow duplicate profiles per User.
    User.objects.using(schema_editor.connection.alias).filter(role='worker').update(
        active_role='worker'
    )


class Migration(migrations.Migration):
    dependencies = [('accounts', '0004_worker_service_zones')]

    operations = [
        migrations.AddField(
            model_name='user',
            name='active_role',
            field=models.CharField(
                choices=[('client', 'Заказчик'), ('worker', 'Исполнитель')],
                default='client', max_length=10,
                verbose_name='Выбранный кабинет',
                help_text='Только выбор интерфейса; права определяются профилями и доступом к объекту.',
            ),
        ),
        migrations.RunPython(migrate_legacy_role, migrations.RunPython.noop),
    ]
