"""Stage 04.4: structured order data and private sanitized attachments.

Additive only: the existing textual price, historical address and Order rows
remain untouched, with legacy sentinel/defaults until explicitly populated.
"""
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0010_order_submission_digest'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='order', name='price_kind',
            field=models.CharField(
                max_length=12, default='legacy',
                choices=[
                    ('legacy', 'Историческая цена'), ('fixed', 'Фиксированная'),
                    ('range', 'Диапазон'), ('negotiable', 'Договорная'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='order', name='amount_min_ils',
            field=models.DecimalField(
                max_digits=9, decimal_places=2, null=True, blank=True,
            ),
        ),
        migrations.AddField(
            model_name='order', name='amount_max_ils',
            field=models.DecimalField(
                max_digits=9, decimal_places=2, null=True, blank=True,
            ),
        ),
        migrations.AddField(
            model_name='order', name='preferred_date',
            field=models.DateField(null=True, blank=True),
        ),
        migrations.AddField(
            model_name='order', name='urgency',
            field=models.CharField(
                max_length=8, default='legacy',
                choices=[
                    ('legacy', 'Не указана'), ('normal', 'Обычная'),
                    ('soon', 'В ближайшие дни'), ('urgent', 'Срочно'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='order', name='work_mode',
            field=models.CharField(
                max_length=8, default='legacy',
                choices=[
                    ('legacy', 'Не указан'), ('onsite', 'На месте'),
                    ('online', 'Онлайн'),
                ],
            ),
        ),
        migrations.AddField(
            model_name='order', name='approximate_area',
            field=models.CharField(max_length=80, blank=True, default=''),
        ),
        migrations.CreateModel(
            name='OrderAttachment',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID',
                )),
                ('file_key', models.CharField(max_length=120, unique=True, editable=False)),
                ('visibility', models.CharField(
                    max_length=9, default='private',
                    choices=[
                        ('private', 'Только заказчик'),
                        ('assignee', 'Выбранный исполнитель'),
                        ('public', 'Публично (по согласию)'),
                    ],
                )),
                ('content_sha256', models.CharField(max_length=64, editable=False)),
                ('byte_size', models.PositiveIntegerField()),
                ('public_consent_at', models.DateTimeField(
                    blank=True, null=True, editable=False,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.ForeignKey(
                    to='marketplace.order', on_delete=django.db.models.deletion.PROTECT,
                    related_name='attachments',
                )),
                ('uploaded_by', models.ForeignKey(
                    to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT,
                    related_name='order_photo_uploads',
                )),
            ],
            options={
                'db_table': 'marketplace_order_attachment',
                'ordering': ('created_at', 'pk'),
            },
        ),
        migrations.AddConstraint(
            model_name='orderattachment',
            constraint=models.UniqueConstraint(
                fields=['order', 'content_sha256', 'visibility'],
                name='order_photo_unique_content_scope',
            ),
        ),
        migrations.AddConstraint(
            model_name='orderattachment',
            constraint=models.CheckConstraint(
                condition=(
                    models.Q(visibility__in=['private', 'assignee', 'public'])
                    & (models.Q(visibility='public', public_consent_at__isnull=False)
                       | ~models.Q(visibility='public'))
                ),
                name='order_photo_visibility_allowed',
            ),
        ),
    ]
