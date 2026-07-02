from .models import City


def get_active_cities():
    """Получить все активные города."""
    return City.objects.filter(is_active=True).order_by('name_ru')
