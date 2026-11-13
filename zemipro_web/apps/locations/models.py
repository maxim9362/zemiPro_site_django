from django.core.exceptions import ValidationError
from django.db import models
from django.utils.translation import get_language


class District(models.Model):
    """Israel's statistical administrative districts, not service boundaries."""

    name_ru = models.CharField(max_length=100, verbose_name='Округ (рус)')
    name_en = models.CharField(max_length=100, blank=True, default='', verbose_name='Округ (англ)')
    name_he = models.CharField(max_length=100, blank=True, default='', verbose_name='Округ (иврит)')
    slug = models.SlugField(unique=True, verbose_name='Slug')
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    class Meta:
        db_table = 'locations_district'
        verbose_name = 'Округ'
        verbose_name_plural = 'Округа'
        ordering = ['slug']

    @property
    def localized_name(self):
        language = (get_language() or 'ru').split('-')[0]
        name = getattr(self, f'name_{language}', '') if language in ('ru', 'en', 'he') else ''
        return name or self.name_ru

    def __str__(self):
        return self.localized_name


class City(models.Model):
    """Город Израиля."""

    name_ru = models.CharField(max_length=100, verbose_name='Название (рус)')
    name_he = models.CharField(max_length=100, blank=True, default='', verbose_name='Название (иврит)')
    name_en = models.CharField(max_length=100, blank=True, default='', verbose_name='Название (англ)')
    slug = models.SlugField(unique=True, verbose_name='Slug')
    district = models.ForeignKey(
        District, on_delete=models.PROTECT, null=True, blank=True,
        related_name='cities', verbose_name='Округ',
    )
    is_active = models.BooleanField(default=True, verbose_name='Активен')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Город'
        verbose_name_plural = 'Города'
        db_table = 'locations_city'
        ordering = ['name_ru']

    @property
    def localized_name(self):
        """Return the city name for the active Django language with RU fallback."""
        language = (get_language() or 'ru').split('-')[0]
        if language == 'he' and self.name_he:
            return self.name_he
        if language == 'en' and self.name_en:
            return self.name_en
        return self.name_ru

    def clean(self):
        super().clean()
        if self.slug and CityAlias.objects.filter(slug=self.slug).exists():
            raise ValidationError({
                'slug': 'Канонический slug города уже используется как алиас.'
            })

    def __str__(self):
        return self.localized_name


class CityAlias(models.Model):
    """Alternative spellings; canonical City PK/slug are never replaced."""

    slug = models.SlugField(unique=True, verbose_name='Alias slug')
    city = models.ForeignKey(
        City, on_delete=models.PROTECT, related_name='aliases', verbose_name='Город',
    )

    class Meta:
        db_table = 'locations_city_alias'
        verbose_name = 'Алиас города'
        verbose_name_plural = 'Алиасы городов'
        ordering = ['slug']

    def clean(self):
        super().clean()
        if self.slug and City.objects.filter(slug=self.slug).exists():
            raise ValidationError({
                'slug': 'Алиас не должен совпадать с каноническим slug города.'
            })

    def __str__(self):
        return f'{self.slug} → {self.city.slug}'


class Neighborhood(models.Model):
    """Optional verified service area inside a city; not a public city gate."""

    city = models.ForeignKey(
        City, on_delete=models.PROTECT, related_name='neighborhoods',
    )
    slug = models.SlugField()
    name_ru = models.CharField(max_length=100)
    name_en = models.CharField(max_length=100, blank=True, default='')
    name_he = models.CharField(max_length=100, blank=True, default='')
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'locations_neighborhood'
        ordering = ['city_id', 'slug']
        constraints = [
            models.UniqueConstraint(
                fields=['city', 'slug'], name='unique_neighborhood_city_slug',
            ),
        ]

    @property
    def localized_name(self):
        language = (get_language() or 'ru').split('-')[0]
        translated = (
            getattr(self, f'name_{language}', '')
            if language in ('en', 'he') else ''
        )
        return translated or self.name_ru

    def __str__(self):
        return f'{self.city.slug} / {self.localized_name}'
