"""Stage 02.5: additive versioned questionnaires; no rewrite of older orders."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0005_catalog_hierarchy')]

    operations = [
        migrations.CreateModel(
            name='ServiceQuestionnaire',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('draft_schema', models.JSONField(blank=True, default=list)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('service', models.OneToOneField(on_delete=django.db.models.deletion.PROTECT, related_name='questionnaire', to='marketplace.subcategory')),
            ],
            options={'db_table': 'marketplace_service_questionnaire', 'verbose_name': 'Анкета услуги', 'verbose_name_plural': 'Анкеты услуг'},
        ),
        migrations.CreateModel(
            name='QuestionnaireVersion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('number', models.PositiveIntegerField()),
                ('schema', models.JSONField(default=list)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('questionnaire', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='versions', to='marketplace.servicequestionnaire')),
            ],
            options={'db_table': 'marketplace_questionnaire_version', 'ordering': ['questionnaire_id', '-number'], 'verbose_name': 'Опубликованная версия анкеты', 'verbose_name_plural': 'Опубликованные версии анкет'},
        ),
        migrations.AddField(
            model_name='servicequestionnaire', name='published_version',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name='+', to='marketplace.questionnaireversion'),
        ),
        migrations.CreateModel(
            name='OrderQuestionnaireAnswer',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('schema_snapshot', models.JSONField(default=list)),
                ('answers', models.JSONField(default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='questionnaire_answer', to='marketplace.order')),
                ('version', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='order_answers', to='marketplace.questionnaireversion')),
            ],
            options={'db_table': 'marketplace_order_questionnaire_answer', 'verbose_name': 'Ответы на анкету заказа', 'verbose_name_plural': 'Ответы на анкеты заказов'},
        ),
        migrations.AddConstraint(
            model_name='questionnaireversion',
            constraint=models.UniqueConstraint(fields=('questionnaire', 'number'), name='unique_questionnaire_version'),
        ),
    ]
