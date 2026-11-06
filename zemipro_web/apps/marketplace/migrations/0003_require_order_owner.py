from django.db import migrations, models
import django.db.models.deletion


def ensure_every_order_has_owner(apps, schema_editor):
    Order = apps.get_model('marketplace', 'Order')
    anonymous_count = Order.objects.filter(client__isnull=True).count()
    if anonymous_count:
        raise RuntimeError(
            f'Cannot require order owners: {anonymous_count} existing order(s) '
            'have no client. Assign registered owners before applying this migration.'
        )


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0002_initial'),
        ('marketplace', '0002_order_customer_name_order_customer_phone_and_more'),
    ]

    operations = [
        migrations.RunPython(
            ensure_every_order_has_owner,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='order',
            name='client',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name='client_orders',
                to='accounts.user',
                verbose_name='Заказчик',
            ),
        ),
    ]
