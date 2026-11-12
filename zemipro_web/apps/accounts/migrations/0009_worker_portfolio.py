"""03.5: worker portfolio metadata only, no files or existing rows modified."""
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [('accounts', '0008_worker_publication')]

    operations = [
        migrations.CreateModel(
            name='WorkerPortfolioPhoto',
            fields=[
                ('id', models.BigAutoField(
                    auto_created=True, primary_key=True, serialize=False,
                    verbose_name='ID',
                )),
                ('file_key', models.CharField(max_length=96, unique=True)),
                ('caption', models.CharField(
                    blank=True, default='', max_length=300,
                )),
                ('sort_order', models.PositiveSmallIntegerField(default=0)),
                ('is_public', models.BooleanField(default=False)),
                ('rights_confirmed_at', models.DateTimeField()),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('worker', models.ForeignKey(
                    on_delete=django.db.models.deletion.PROTECT,
                    related_name='portfolio_photos', to='accounts.workerprofile',
                )),
            ],
            options={
                'db_table': 'accounts_worker_portfolio_photo',
                'ordering': ['sort_order', 'pk'],
            },
        ),
        migrations.AddConstraint(
            model_name='workerportfoliophoto',
            constraint=models.CheckConstraint(
                condition=models.Q(sort_order__lte=999),
                name='worker_portfolio_sort_order_max_999',
            ),
        ),
    ]
