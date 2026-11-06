from django.db import models
from django.utils.translation import get_language


class City(models.Model):
    """Город Израиля."""

    name_ru = models.CharField(max_length=100, verbose_name='Название (рус)')
    name_he = models.CharField(max_length=100, blank=True, default='', verbose_name='Название (иврит)')
    name_en = models.CharField(max_length=100, blank=True, default='', verbose_name='Название (англ)')
    slug = models.SlugField(unique=True, verbose_name='Slug')
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

    def __str__(self):
        return self.localized_name
