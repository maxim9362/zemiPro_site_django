"""Stage 03.3: account locale, optional update preference and privacy requests."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('accounts', '0006_contact_verification')]

    operations = [
        migrations.AddField(
            model_name='user', name='preferred_language',
            field=models.CharField(
                choices=[('ru', 'Русский'), ('en', 'English'), ('he', 'עברית')],
                default='ru', max_length=2,
                verbose_name='Предпочитаемый язык',
            ),
        ),
        migrations.AddField(
            model_name='clientprofile', name='receive_optional_updates',
            field=models.BooleanField(
                default=True, verbose_name='Дополнительные уведомления',
            ),
        ),
        migrations.CreateModel(
            name='PrivacyRequest',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('kind', models.CharField(
                    choices=[('export', 'Экспорт данных'),
                             ('delete', 'Удаление данных')],
                    max_length=10,
                )),
                ('status', models.CharField(
                    choices=[('pending', 'Ожидает обработки'),
                             ('processing', 'На рассмотрении'),
                             ('completed', 'Выполнен'),
                             ('rejected', 'Отклонён')],
                    default='pending', max_length=12,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='privacy_requests',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'accounts_privacy_request',
                'ordering': ['-created_at', '-pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='privacyrequest',
            constraint=models.UniqueConstraint(
                fields=('user', 'kind'),
                condition=models.Q(status='pending'),
                name='accounts_unique_pending_privacy_request',
            ),
        ),
        migrations.CreateModel(
            name='FavoriteWorker',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('client', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='favorite_workers',
                    to=settings.AUTH_USER_MODEL,
                )),
                ('worker', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='favorited_by',
                    to='accounts.workerprofile',
                )),
            ],
            options={'db_table': 'accounts_favorite_worker'},
        ),
        migrations.AddConstraint(
            model_name='favoriteworker',
            constraint=models.UniqueConstraint(
                fields=('client', 'worker'),
                name='accounts_unique_client_favorite_worker',
            ),
        ),
    ]
