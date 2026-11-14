"""Stage 06.4: agreement versions, decisions and PostgreSQL append-only guards."""
import uuid

from django.db import migrations, models
import django.db.models.deletion


SQL = """
CREATE OR REPLACE FUNCTION zemipro_stage06_immutable() RETURNS TRIGGER AS $$
BEGIN
    RAISE EXCEPTION 'stage06 history is append-only';
END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER response_revision_immutable BEFORE UPDATE OR DELETE
    ON marketplace_response_revision FOR EACH ROW EXECUTE FUNCTION zemipro_stage06_immutable();
CREATE TRIGGER agreement_version_immutable BEFORE UPDATE OR DELETE
    ON marketplace_order_agreement_version FOR EACH ROW EXECUTE FUNCTION zemipro_stage06_immutable();
CREATE TRIGGER agreement_decision_immutable BEFORE UPDATE OR DELETE
    ON marketplace_order_agreement_decision FOR EACH ROW EXECUTE FUNCTION zemipro_stage06_immutable();
"""

REVERSE = """
DROP TRIGGER IF EXISTS response_revision_immutable ON marketplace_response_revision;
DROP TRIGGER IF EXISTS agreement_version_immutable ON marketplace_order_agreement_version;
DROP TRIGGER IF EXISTS agreement_decision_immutable ON marketplace_order_agreement_decision;
DROP FUNCTION IF EXISTS zemipro_stage06_immutable();
"""


class Migration(migrations.Migration):
    dependencies = [('marketplace', '0017_stage06_offers')]

    operations = [
        migrations.CreateModel(
            name='OrderAgreementVersion',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('number', models.PositiveIntegerField()),
                ('response_revision', models.PositiveIntegerField()),
                ('operation_key', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('price_kind', models.CharField(
                    choices=[
                        ('negotiable', 'По договорённости'), ('fixed', 'Фиксированная цена'),
                        ('range', 'Диапазон'), ('method', 'Способ расчёта'),
                    ], max_length=12,
                )),
                ('amount_min_ils', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=9, null=True,
                )),
                ('amount_max_ils', models.DecimalField(
                    blank=True, decimal_places=2, max_digits=9, null=True,
                )),
                ('pricing_method', models.CharField(blank=True, default='', max_length=240)),
                ('estimated_timeline', models.CharField(blank=True, default='', max_length=160)),
                ('terms', models.TextField(blank=True, default='')),
                ('note', models.TextField(blank=True, default='')),
                ('proposed_at', models.DateTimeField(auto_now_add=True)),
                ('order', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='agreement_versions', to='marketplace.order',
                )),
                ('response', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='agreement_versions', to='marketplace.response',
                )),
                ('proposed_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='proposed_agreements', to='accounts.user',
                )),
            ],
            options={
                'db_table': 'marketplace_order_agreement_version',
                'ordering': ['number', 'pk'],
            },
        ),
        migrations.CreateModel(
            name='OrderAgreementDecision',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False, verbose_name='ID',
                )),
                ('result', models.CharField(
                    choices=[('accepted', 'Принято'), ('rejected', 'Отклонено')],
                    max_length=8,
                )),
                ('operation_key', models.UUIDField(default=uuid.uuid4, editable=False)),
                ('decided_at', models.DateTimeField(auto_now_add=True)),
                ('actor', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='agreement_decisions', to='accounts.user',
                )),
                ('agreement', models.OneToOneField(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='decision', to='marketplace.orderagreementversion',
                )),
            ],
            options={'db_table': 'marketplace_order_agreement_decision'},
        ),
        migrations.AddConstraint(
            model_name='orderagreementversion',
            constraint=models.UniqueConstraint(
                fields=('order', 'number'), name='agreement_version_number_unique',
            ),
        ),
        migrations.AddConstraint(
            model_name='orderagreementversion',
            constraint=models.UniqueConstraint(
                fields=('order', 'operation_key'), name='agreement_version_operation_unique',
            ),
        ),
        migrations.RunSQL(SQL, reverse_sql=REVERSE),
    ]
