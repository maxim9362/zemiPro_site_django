from django.db.models import F

from .models import GlobalStats, CategoryStats


def increment_global_stat(metric_name, amount=1):
    """Увеличить глобальную статистику на amount."""
    stat, created = GlobalStats.objects.get_or_create(
        metric_name=metric_name, defaults={'count': 0}
    )
    stat.count = F('count') + amount
    stat.save(update_fields=['count', 'updated_at'])
    stat.refresh_from_db()
    return stat


def increment_category_completed(category, amount=1):
    """Увеличить счётчик завершённых заказов категории."""
    stat, created = CategoryStats.objects.get_or_create(
        category=category, defaults={'completed_count': 0}
    )
    stat.completed_count = F('completed_count') + amount
    stat.save(update_fields=['completed_count', 'updated_at'])
    stat.refresh_from_db()
    return stat
