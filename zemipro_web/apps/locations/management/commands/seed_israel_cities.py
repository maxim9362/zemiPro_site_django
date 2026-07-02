from django.core.management.base import BaseCommand

from apps.locations.models import City


CITIES_DATA = [
    {'name_ru': 'Ашдод', 'slug': 'ashdod'},
    {'name_ru': 'Ашкелон', 'slug': 'ashkelon'},
    {'name_ru': 'Тель-Авив', 'slug': 'tel-aviv'},
    {'name_ru': 'Бат-Ям', 'slug': 'bat-yam'},
    {'name_ru': 'Холон', 'slug': 'holon'},
    {'name_ru': 'Ришон-ле-Цион', 'slug': 'rishon-lezion'},
    {'name_ru': 'Реховот', 'slug': 'rehovot'},
    {'name_ru': 'Явне', 'slug': 'yavne'},
    {'name_ru': 'Ган-Явне', 'slug': 'gan-yavne'},
    {'name_ru': 'Кирьят-Малахи', 'slug': 'kiryat-malakhi'},
    {'name_ru': 'Кирьят-Гат', 'slug': 'kiryat-gat'},
    {'name_ru': 'Сдерот', 'slug': 'sderot'},
    {'name_ru': 'Нетивот', 'slug': 'netivot'},
    {'name_ru': 'Офаким', 'slug': 'ofakim'},
    {'name_ru': 'Беэр-Шева', 'slug': 'beer-sheva'},
    {'name_ru': 'Иерусалим', 'slug': 'jerusalem'},
    {'name_ru': 'Хайфа', 'slug': 'haifa'},
    {'name_ru': 'Нетания', 'slug': 'netanya'},
    {'name_ru': 'Петах-Тиква', 'slug': 'petah-tikva'},
    {'name_ru': 'Рамат-Ган', 'slug': 'ramat-gan'},
    {'name_ru': 'Бней-Брак', 'slug': 'bnei-brak'},
    {'name_ru': 'Герцлия', 'slug': 'herzliya'},
    {'name_ru': 'Раанана', 'slug': 'raanana'},
    {'name_ru': 'Кфар-Саба', 'slug': 'kfar-saba'},
    {'name_ru': 'Модиин', 'slug': 'modiin'},
]


class Command(BaseCommand):
    help = 'Создаёт или обновляет основные города Израиля'

    def handle(self, *args, **options):
        created = 0
        updated = 0

        for city_data in CITIES_DATA:
            city, was_created = City.objects.update_or_create(
                slug=city_data['slug'],
                defaults={
                    'name_ru': city_data['name_ru'],
                    'is_active': True,
                },
            )
            if was_created:
                created += 1
                self.stdout.write(f'  + Город: {city.name_ru}')
            else:
                updated += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово! Создано: {created}, обновлено: {updated}'
        ))
