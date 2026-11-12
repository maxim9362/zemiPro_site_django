"""Stage 02.1 additive catalog hierarchy, without rewriting legacy rows/IDs."""
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('marketplace', '0004_status_constraints'),
    ]

    operations = [
        migrations.CreateModel(
            name='ServiceSection',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name_ru', models.CharField(max_length=100, verbose_name='Раздел (рус)')),
                ('name_en', models.CharField(max_length=100, blank=True, default='', verbose_name='Раздел (англ)')),
                ('name_he', models.CharField(max_length=100, blank=True, default='', verbose_name='Раздел (иврит)')),
                ('slug', models.SlugField(unique=True, verbose_name='Slug')),
                ('description_ru', models.TextField(blank=True, default='')),
                ('description_en', models.TextField(blank=True, default='')),
                ('description_he', models.TextField(blank=True, default='')),
                ('seo_title_ru', models.CharField(max_length=180, blank=True, default='')),
                ('seo_title_en', models.CharField(max_length=180, blank=True, default='')),
                ('seo_title_he', models.CharField(max_length=180, blank=True, default='')),
                ('seo_description_ru', models.CharField(max_length=320, blank=True, default='')),
                ('seo_description_en', models.CharField(max_length=320, blank=True, default='')),
                ('seo_description_he', models.CharField(max_length=320, blank=True, default='')),
                ('is_active', models.BooleanField(default=True)),
                ('sort_order', models.PositiveIntegerField(default=0)),
            ],
            options={
                'verbose_name': 'Раздел услуг', 'verbose_name_plural': 'Разделы услуг',
                'db_table': 'marketplace_service_section', 'ordering': ['sort_order', 'pk'],
            },
        ),
        migrations.AddField(
            model_name='category', name='section',
            field=models.ForeignKey(
                blank=True, null=True, on_delete=django.db.models.deletion.PROTECT,
                related_name='categories', to='marketplace.servicesection', verbose_name='Раздел',
            ),
        ),
        migrations.AddField(model_name='category', name='description_en', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='category', name='description_he', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='category', name='seo_title_ru', field=models.CharField(max_length=180, blank=True, default='')),
        migrations.AddField(model_name='category', name='seo_title_en', field=models.CharField(max_length=180, blank=True, default='')),
        migrations.AddField(model_name='category', name='seo_title_he', field=models.CharField(max_length=180, blank=True, default='')),
        migrations.AddField(model_name='category', name='seo_description_ru', field=models.CharField(max_length=320, blank=True, default='')),
        migrations.AddField(model_name='category', name='seo_description_en', field=models.CharField(max_length=320, blank=True, default='')),
        migrations.AddField(model_name='category', name='seo_description_he', field=models.CharField(max_length=320, blank=True, default='')),
        migrations.AddField(model_name='subcategory', name='description_ru', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='subcategory', name='description_en', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='subcategory', name='description_he', field=models.TextField(blank=True, default='')),
        migrations.AddField(model_name='subcategory', name='seo_title_ru', field=models.CharField(max_length=180, blank=True, default='')),
        migrations.AddField(model_name='subcategory', name='seo_title_en', field=models.CharField(max_length=180, blank=True, default='')),
        migrations.AddField(model_name='subcategory', name='seo_title_he', field=models.CharField(max_length=180, blank=True, default='')),
        migrations.AddField(model_name='subcategory', name='seo_description_ru', field=models.CharField(max_length=320, blank=True, default='')),
        migrations.AddField(model_name='subcategory', name='seo_description_en', field=models.CharField(max_length=320, blank=True, default='')),
        migrations.AddField(model_name='subcategory', name='seo_description_he', field=models.CharField(max_length=320, blank=True, default='')),
        migrations.AddField(model_name='category', name='work_mode', field=models.CharField(max_length=10, choices=[('onsite', 'Выезд'), ('online', 'Онлайн'), ('both', 'Выезд и онлайн')], default='onsite')),
        migrations.AddField(model_name='subcategory', name='work_mode', field=models.CharField(max_length=10, choices=[('onsite', 'Выезд'), ('online', 'Онлайн'), ('both', 'Выезд и онлайн')], default='onsite')),
    ]
