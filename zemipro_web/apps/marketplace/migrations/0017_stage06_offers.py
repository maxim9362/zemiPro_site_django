"""Stage 06.1: non-destructive offer fields and private immutable snapshots."""
import uuid

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0016_rating_public_snapshot'),
    ]

    operations = [
        migrations.AddField(
            model_name='response', name='price_kind',
            field=models.CharField(
                choices=[('negotiable', 'По договорённости'), ('fixed', 'Фиксированная цена'),
                         ('range', 'Диапазон'), ('method', 'Способ расчёта')],
                default='negotiable', max_length=12,
            ),
        ),
        migrations.AddField(
            model_name='response', name='amount_min_ils',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=9, null=True,
            ),
        ),
        migrations.AddField(
            model_name='response', name='amount_max_ils',
            field=models.DecimalField(
                blank=True, decimal_places=2, max_digits=9, null=True,
            ),
        ),
        migrations.AddField(
            model_name='response', name='pricing_method',
            field=models.CharField(blank=True, default='', max_length=240),
        ),
        migrations.AddField(
            model_name='response', name='estimated_timeline',
            field=models.CharField(blank=True, default='', max_length=160),
        ),
        migrations.AddField(
            model_name='response', name='terms',
            field=models.TextField(blank=True, default=''),
        ),
        migrations.AddField(
            model_name='response', name='revision',
            field=models.PositiveIntegerField(default=1, editable=False),
        ),
        migrations.AlterField(
            model_name='response', name='status',
            field=models.CharField(
                choices=[
                    ('pending', 'Исторический отклик'), ('cancelled', 'Исторически отменён'),
                    ('sent', 'Отправлено'), ('viewed', 'Просмотрено'),
                    ('negotiating', 'Обсуждение'), ('accepted', 'Принято'),
                    ('rejected', 'Отклонено'), ('withdrawn', 'Отозвано'),
                    ('expired', 'Истекло'),
                ],
                default='pending', max_length=20, verbose_name='Статус',
            ),
        ),
        migrations.RemoveConstraint(
            model_name='response', name='response_status_allowed',
        ),
        migrations.AddConstraint(
            model_name='response',
            constraint=models.CheckConstraint(
                condition=models.Q(
                    status__in=[
                        'pending', 'cancelled', 'sent', 'viewed', 'negotiating',
                        'accepted', 'rejected', 'withdrawn', 'expired',
                    ],
                ), name='response_status_allowed',
            ),
        ),
        migrations.AddConstraint(
            model_name='response',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(
                        price_kind__in=['negotiable', 'method'],
                        amount_min_ils__isnull=True, amount_max_ils__isnull=True,
                    ) | models.Q(
                        price_kind='fixed', amount_min_ils__gte=0,
                        amount_max_ils__isnull=True,
                    ) | models.Q(
                        price_kind='range', amount_min_ils__gte=0,
                        amount_max_ils__gte=models.F('amount_min_ils'),
                    )
                ), name='response_price_valid',
            ),
        ),
        migrations.CreateModel(
            name='ResponseRevision',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('number', models.PositiveIntegerField()),
                ('operation_key', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('action', models.CharField(max_length=16)),
                ('status', models.CharField(max_length=20)),
                ('message', models.TextField(blank=True, default='')),
                ('price_kind', models.CharField(max_length=12)),
                ('amount_min_ils', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=9, null=True,
                )),
                ('amount_max_ils', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=9, null=True,
                )),
                ('pricing_method', models.CharField(blank=True, default='', max_length=240)),
                ('estimated_timeline', models.CharField(blank=True, default='', max_length=160)),
                ('terms', models.TextField(blank=True, default='')),
                ('occurred_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='offer_actions', to='accounts.user',
                )),
                ('response', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='revisions', to='marketplace.response',
                )),
            ],
            options={
                'db_table': 'marketplace_response_revision',
                'ordering': ['number', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='responserevision',
            constraint=models.UniqueConstraint(
                fields=('response', 'number'), name='offer_revision_number_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='responserevision',
            constraint=models.UniqueConstraint(
                fields=('response', 'operation_key'), name='offer_revision_operation_unique',
            ),
        ),
    ]
