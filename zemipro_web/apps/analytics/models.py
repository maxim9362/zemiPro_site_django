from django.db import models


class GlobalStats(models.Model):
    """Глобальная статистика платформы."""

    metric_name = models.CharField(max_length=100, unique=True, verbose_name='Метрика')
    count = models.PositiveIntegerField(default=0, verbose_name='Значение')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Глобальная статистика'
        verbose_name_plural = 'Глобальная статистика'
        db_table = 'analytics_global_stats'

    def __str__(self):
        return f'{self.metric_name}: {self.count}'


class CategoryStats(models.Model):
    """Статистика по категории."""

    category = models.OneToOneField(
        'marketplace.Category', on_delete=models.CASCADE,
        related_name='stats', verbose_name='Категория'
    )
    completed_count = models.PositiveIntegerField(
        default=0, verbose_name='Завершено заказов'
    )
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлено')

    class Meta:
        verbose_name = 'Статистика категории'
        verbose_name_plural = 'Статистика категорий'
        db_table = 'analytics_category_stats'

    def __str__(self):
        return f'{self.category.name_ru}: {self.completed_count}'
