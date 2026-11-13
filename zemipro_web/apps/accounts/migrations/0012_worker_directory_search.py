"""Stage 05.1: explicit services and optional owner-declared numeric pricing.

No historical text price is parsed. No existing profile is automatically
assigned a concrete service or price, and no user data is removed.
"""
from django.core.validators import MinValueValidator
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0011_user_email_verification_required'),
        ('marketplace', '0005_catalog_hierarchy'),
    ]

    operations = [
        migrations.AddField(
            model_name='workerprofile',
            name='services',
            field=models.ManyToManyField(
                blank=True, related_name='workers',
                to='marketplace.subcategory',
                verbose_name='Конкретные услуги',
            ),
        ),
        migrations.AddField(
            model_name='workerprofile',
            name='starting_price_ils',
            field=models.DecimalField(
                max_digits=10, decimal_places=2, blank=True, null=True,
                validators=[MinValueValidator(0)], db_index=True,
                verbose_name='Заявленная стартовая цена, ₪',
                help_text='Необязательная цена от мастера; текст не преобразуется в число.',
            ),
        ),
        migrations.AddIndex(
            model_name='workerprofile',
            index=models.Index(
                fields=['is_published', 'city', 'availability'],
                name='worker_public_search_idx',
            ),
        ),
    ]
