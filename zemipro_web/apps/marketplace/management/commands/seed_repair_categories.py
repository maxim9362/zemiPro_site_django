from django.core.management.base import BaseCommand

from apps.marketplace.models import Category, Subcategory


CATEGORIES_DATA = [
    {
        'name_ru': 'Сантехника',
        'slug': 'plumbing',
        'emoji': '🚰',
        'description': 'Устранение протечек, замена кранов, ремонт труб, унитазов, бойлеров и другой сантехники.',
        'sort_order': 10,
        'subcategories': [
            ('Протечка воды', 'leak-repair'),
            ('Замена крана', 'faucet-replacement'),
            ('Ремонт унитаза', 'toilet-repair'),
            ('Засор', 'drain-clogging'),
            ('Установка бойлера', 'water-heater-installation'),
            ('Замена труб', 'pipe-replacement'),
            ('Срочный сантехник', 'emergency-plumber'),
        ],
    },
    {
        'name_ru': 'Электрика',
        'slug': 'electricity',
        'emoji': '⚡',
        'description': 'Ремонт электрики, розеток, автоматов, освещения, щитков и диагностика неисправностей.',
        'sort_order': 20,
        'subcategories': [
            ('Ремонт розеток', 'outlet-repair'),
            ('Замена выключателя', 'switch-replacement'),
            ('Проблемы со светом', 'lighting-issues'),
            ('Электрощиток', 'electrical-panel'),
            ('Короткое замыкание', 'short-circuit'),
            ('Установка светильников', 'light-fixture-installation'),
            ('Срочный электрик', 'emergency-electrician'),
        ],
    },
    {
        'name_ru': 'Кондиционеры',
        'slug': 'air-conditioners',
        'emoji': '❄️',
        'description': 'Ремонт, установка, чистка и обслуживание кондиционеров.',
        'sort_order': 30,
        'subcategories': [
            ('Ремонт кондиционера', 'ac-repair'),
            ('Установка кондиционера', 'ac-installation'),
            ('Чистка кондиционера', 'ac-cleaning'),
            ('Заправка газа', 'ac-gas-refill'),
            ('Кондиционер не охлаждает', 'ac-not-cooling'),
            ('Демонтаж кондиционера', 'ac-removal'),
            ('Обслуживание кондиционера', 'ac-maintenance'),
        ],
    },
    {
        'name_ru': 'Ремонт квартир',
        'slug': 'apartment-renovation',
        'emoji': '🏠',
        'description': 'Частичный и комплексный ремонт квартир, комнат, кухонь, ванных и офисов.',
        'sort_order': 40,
        'subcategories': [
            ('Ремонт комнаты', 'room-renovation'),
            ('Ремонт кухни', 'kitchen-renovation'),
            ('Ремонт ванной', 'bathroom-renovation'),
            ('Покраска стен', 'wall-painting'),
            ('Шпаклёвка', 'putty-work'),
            ('Плиточные работы', 'tiling'),
            ('Мелкий ремонт', 'minor-repair'),
        ],
    },
    {
        'name_ru': 'Мастер на час',
        'slug': 'handyman',
        'emoji': '🛠️',
        'description': 'Мелкие домашние работы, установка полок, ремонт дверей, сборка и другие задачи по дому.',
        'sort_order': 50,
        'subcategories': [
            ('Повесить полку', 'shelf-installation'),
            ('Ремонт двери', 'door-repair'),
            ('Установка карниза', 'curtain-rod-installation'),
            ('Мелкий ремонт', 'minor-handyman'),
            ('Замена ручки', 'handle-replacement'),
            ('Установка зеркала', 'mirror-installation'),
            ('Домашний мастер', 'general-handyman'),
        ],
    },
    {
        'name_ru': 'Сборка мебели',
        'slug': 'furniture-assembly',
        'emoji': '🪑',
        'description': 'Сборка шкафов, кроватей, кухонь, столов, стульев и другой мебели.',
        'sort_order': 60,
        'subcategories': [
            ('Сборка шкафа', 'wardrobe-assembly'),
            ('Сборка кровати', 'bed-assembly'),
            ('Сборка кухни', 'kitchen-assembly'),
            ('Сборка стола', 'table-assembly'),
            ('Сборка мебели IKEA', 'ikea-assembly'),
            ('Разборка мебели', 'furniture-disassembly'),
            ('Перенос мебели', 'furniture-moving'),
        ],
    },
    {
        'name_ru': 'Бытовая техника',
        'slug': 'appliance-repair',
        'emoji': '🔧',
        'description': 'Ремонт и подключение бытовой техники: стиральных машин, посудомоек, духовок и холодильников.',
        'sort_order': 70,
        'subcategories': [
            ('Ремонт стиральной машины', 'washing-machine-repair'),
            ('Ремонт посудомойки', 'dishwasher-repair'),
            ('Ремонт духовки', 'oven-repair'),
            ('Ремонт холодильника', 'refrigerator-repair'),
            ('Подключение техники', 'appliance-installation'),
            ('Техника не включается', 'appliance-not-starting'),
            ('Диагностика техники', 'appliance-diagnostics'),
        ],
    },
    {
        'name_ru': 'Аварийные работы',
        'slug': 'emergency-repair',
        'emoji': '🚨',
        'description': 'Срочный вызов мастера при протечке, отключении света, поломке замка или другой аварийной ситуации.',
        'sort_order': 80,
        'subcategories': [
            ('Срочный сантехник', 'emergency-plumber'),
            ('Срочный электрик', 'emergency-electrician'),
            ('Аварийная протечка', 'emergency-leak'),
            ('Нет электричества', 'power-outage'),
            ('Срочный ремонт замка', 'emergency-lock-repair'),
            ('Срочный мастер', 'emergency-handyman'),
            ('Ночная заявка', 'night-emergency'),
        ],
    },
]


class Command(BaseCommand):
    help = 'Создаёт или обновляет категории и подкатегории ремонта'

    def handle(self, *args, **options):
        created_categories = 0
        updated_categories = 0
        created_subcategories = 0
        updated_subcategories = 0

        for cat_data in CATEGORIES_DATA:
            subcategories_data = cat_data['subcategories']
            category_defaults = {
                key: value for key, value in cat_data.items() if key != 'subcategories'
            }

            category, created = Category.objects.get_or_create(
                slug=cat_data['slug'],
                defaults=category_defaults,
            )
            if created:
                created_categories += 1
                self.stdout.write(f'  + Категория: {category.name_ru}')
            else:
                updated_categories += 1

            for sub_name, sub_slug in subcategories_data:
                sub, sub_created = Subcategory.objects.get_or_create(
                    category=category,
                    slug=sub_slug,
                    defaults={'name_ru': sub_name},
                )
                if sub_created:
                    created_subcategories += 1
                else:
                    updated_subcategories += 1

        self.stdout.write(self.style.SUCCESS(
            f'\nГотово!'
            f'\n  Категории: создано {created_categories}, уже существовало {updated_categories}'
            f'\n  Подкатегории: создано {created_subcategories}, уже существовало {updated_subcategories}'
        ))
