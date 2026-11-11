"""Stage 02.2: additive statistical district / canonical city aliases."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('locations', '0001_initial')]

    operations = [
        migrations.CreateModel(
            name='District',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name_ru', models.CharField(max_length=100, verbose_name='Округ (рус)')),
                ('name_en', models.CharField(max_length=100, blank=True, default='', verbose_name='Округ (англ)')),
                ('name_he', models.CharField(max_length=100, blank=True, default='', verbose_name='Округ (иврит)')),
                ('slug', models.SlugField(unique=True, verbose_name='Slug')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активен')),
            ],
            options={
                'db_table': 'locations_district',
                'verbose_name': 'Округ',
                'verbose_name_plural': 'Округа',
                'ordering': ['slug'],
            },
        ),
        migrations.AddField(
            model_name='city', name='district',
            field=models.ForeignKey(
                to='locations.district', on_delete=django.db.models.deletion.PROTECT,
                null=True, blank=True, related_name='cities', verbose_name='Округ',
            ),
        ),
        migrations.CreateModel(
            name='CityAlias',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField(unique=True, verbose_name='Alias slug')),
                ('city', models.ForeignKey(
                    to='locations.city', on_delete=django.db.models.deletion.PROTECT,
                    related_name='aliases', verbose_name='Город',
                )),
            ],
            options={
                'db_table': 'locations_city_alias',
                'verbose_name': 'Алиас города',
                'verbose_name_plural': 'Алиасы городов',
                'ordering': ['slug'],
            },
        ),
    ]
