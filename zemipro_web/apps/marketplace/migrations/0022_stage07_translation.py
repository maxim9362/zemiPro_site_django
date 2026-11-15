"""Stage 07.6: optional, private, append-only machine translations."""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0021_stage07_reviews'),
    ]

    operations = [
        migrations.CreateModel(
            name='MessageTranslation',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True,
                    serialize=False, verbose_name='ID',
                )),
                ('target_language', models.CharField(
                    max_length=2, choices=[
                        ('ru', 'Русский'), ('en', 'English'), ('he', 'עברית'),
                    ],
                )),
                ('translated_body', models.TextField()),
                ('engine', models.CharField(max_length=32, default='gemini')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('message', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='machine_translations', to='marketplace.message',
                )),
                ('requested_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='requested_chat_translations', to='accounts.user',
                )),
            ],
            options={
                'db_table': 'marketplace_message_translation',
                'ordering': ['created_at', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='messagetranslation',
            constraint=models.UniqueConstraint(
                fields=['message', 'target_language'],
                name='chat_translation_target_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='messagetranslation',
            constraint=models.CheckConstraint(
                condition=models.Q(target_language__in=['ru', 'en', 'he']),
                name='chat_translation_language_valid',
            ),
        ),
        migrations.RunSQL(
            sql=(
                "CREATE TRIGGER stage07_machine_translation_immutable "
                "BEFORE UPDATE OR DELETE ON marketplace_message_translation "
                "FOR EACH ROW EXECUTE FUNCTION zemipro_stage06_immutable();"
            ),
            reverse_sql=(
                "DROP TRIGGER IF EXISTS stage07_machine_translation_immutable "
                "ON marketplace_message_translation;"
            ),
        ),
    ]
