"""Stage 05.2: optional explicitly managed, city-scoped service neighborhoods.

No neighborhood names or assignments are auto-generated: old city-wide
service semantics remain unchanged until a worker selects a specific area.
"""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('locations', '0002_district_city_alias'),
    ]

    operations = [
        migrations.CreateModel(
            name='Neighborhood',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('slug', models.SlugField()),
                ('name_ru', models.CharField(max_length=100)),
                ('name_en', models.CharField(max_length=100, blank=True, default='')),
                ('name_he', models.CharField(max_length=100, blank=True, default='')),
                ('is_active', models.BooleanField(default=True)),
                ('city', models.ForeignKey(
                    to='locations.city', on_delete=django.db.models.deletion.PROTECT,
                    related_name='neighborhoods',
                )),
            ],
            options={
                'db_table': 'locations_neighborhood',
                'ordering': ['city_id', 'slug'],
            },
        ),
        migrations.AddConstraint(
            model_name='neighborhood',
            constraint=models.UniqueConstraint(
                fields=['city', 'slug'], name='unique_neighborhood_city_slug',
            ),
        ),
    ]
