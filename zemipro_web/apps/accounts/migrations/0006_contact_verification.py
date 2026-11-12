"""Stage 03.2: add verified contacts and opaque challenge/delivery audit."""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0005_user_active_role'),
    ]

    operations = [
        migrations.AddField(
            model_name='user', name='email_verified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='user', name='phone_verified_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name='ContactChallenge',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('channel', models.CharField(
                    choices=[('email', 'Email'), ('phone', 'Телефон')],
                    max_length=8,
                )),
                ('destination_digest', models.CharField(max_length=64)),
                ('code_digest', models.CharField(max_length=64)),
                ('attempts', models.PositiveSmallIntegerField(default=0)),
                ('expires_at', models.DateTimeField()),
                ('sent_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='contact_challenges',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'db_table': 'accounts_contact_challenge',
                'constraints': [
                    models.UniqueConstraint(
                        fields=('user', 'channel'),
                        name='accounts_one_contact_challenge',
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name='VerifiedContact',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('channel', models.CharField(
                    choices=[('email', 'Email'), ('phone', 'Телефон')],
                    max_length=8,
                )),
                ('fingerprint', models.CharField(max_length=64, unique=True)),
                ('verified_at', models.DateTimeField(default=django.utils.timezone.now)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='verified_contacts',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'db_table': 'accounts_verified_contact'},
        ),
        migrations.CreateModel(
            name='ContactDeliveryEvent',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True,
                                           serialize=False, verbose_name='ID')),
                ('channel', models.CharField(
                    choices=[('email', 'Email'), ('phone', 'Телефон')],
                    max_length=8,
                )),
                ('destination_digest', models.CharField(max_length=64)),
                ('outcome', models.CharField(
                    choices=[
                        ('sent', 'Передано адаптеру'),
                        ('unavailable', 'Доставка не настроена'),
                        ('failed', 'Ошибка доставки'),
                    ],
                    max_length=12,
                )),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('user', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='contact_delivery_events',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'db_table': 'accounts_contact_delivery_event'},
        ),
    ]
