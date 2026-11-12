"""Stage 03.4 opt-in worker publication. No existing profiles are auto-published."""
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0007_client_privacy')]

    operations = [
        migrations.AddField(
            model_name='workerprofile', name='provider_type',
            field=models.CharField(
                choices=[('individual', 'Частный мастер'), ('company', 'Компания')],
                default='individual', max_length=10, verbose_name='Тип исполнителя',
            ),
        ),
        migrations.AddField(
            model_name='workerprofile', name='display_name',
            field=models.CharField(
                blank=True, default='', max_length=120,
                verbose_name='Публичное имя или компания',
            ),
        ),
        migrations.AddField(
            model_name='workerprofile', name='spoken_languages',
            field=models.JSONField(blank=True, default=list, verbose_name='Языки общения'),
        ),
        migrations.AddField(
            model_name='workerprofile', name='pricing_details',
            field=models.CharField(
                blank=True, default='', max_length=240,
                verbose_name='Цены или принцип расчёта',
            ),
        ),
        migrations.AddField(
            model_name='workerprofile', name='availability',
            field=models.CharField(
                choices=[
                    ('available', 'Принимаю заказы'),
                    ('limited', 'Ограниченная доступность'),
                    ('unavailable', 'Пока не принимаю заказы'),
                ],
                default='available', max_length=12, verbose_name='Доступность',
            ),
        ),
        migrations.AddField(
            model_name='workerprofile', name='working_hours',
            field=models.CharField(blank=True, default='', max_length=200,
                verbose_name='График работы'),
        ),
        migrations.AddField(
            model_name='workerprofile', name='is_published',
            field=models.BooleanField(default=False, verbose_name='Опубликован'),
        ),
        migrations.AddField(
            model_name='workerprofile', name='published_at',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Опубликован с'),
        ),
    ]
