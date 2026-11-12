from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('accounts', '0010_remove_legacy_telegram_id')]

    operations = [
        migrations.AddField(
            model_name='user',
            name='email_verification_required',
            field=models.BooleanField(
                default=False,
                help_text=(
                    'Включается только для новых email-регистраций. Значение по '
                    'умолчанию сохраняет доступ исторических username/password аккаунтов.'
                ),
                verbose_name='Требуется подтверждение email для доступа',
            ),
        ),
    ]
