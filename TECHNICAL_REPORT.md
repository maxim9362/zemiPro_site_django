# Технический отчёт: аудит проекта ZemiPro и план перехода на Django

---

## Раздел 1. Краткое описание текущего проекта

**Что это за проект:**
Telegram-бот для связи между клиентами (заказчиками) и мастерами (исполнителями) в Израиле. Платформа работает по модели «классифайд» — клиент публикует заявку на услугу, мастер откликается на неё, клиент выбирает мастера, после выполнения — оставляет отзыв.

**Основные технологии:**
- Python 3.11 (Dockerfile) / 3.12+ (требование к Django)
- aiogram 3.24 — асинхронный фреймворк для Telegram Bot API
- asyncpg 0.31 — асинхронный драйвер PostgreSQL
- PostgreSQL 15 (Alpine)
- FastAPI 0.111 + uvicorn 0.30 — объявлены в requirements.txt, но **код web_api отсутствует** в репозитории
- aiohttp + aiohttp_socks — для SOCKS5 прокси (обход блокировок Telegram)
- pytest + pytest-asyncio + Faker — тестирование
- Docker + docker-compose — деплой
- python-dotenv — конфигурация

**База данных:**
PostgreSQL 15. Подключение через asyncpg пул (min=5, max=20, timeout=30с).

**Точка входа:**
`main.py` → класс `TachlesBotApp` → метод `start()` → polling.

**Контейнеры Docker (docker-compose.yml):**
1. `bot_main` — основной Telegram-бот (`python main.py`)
2. `bot_admin` — админ-бот (`python -m admin_bot.admin_main`)
3. `db` — PostgreSQL 15
4. `web_api` — FastAPI сервер (`python -m web_api.server`) — **код отсутствует**

**Реализованные сценарии:**
- Регистрация заказчика (имя, город, контакт)
- Регистрация исполнителя (имя, город, контакт, навыки, описание)
- Создание заказа клиентом (категория, адрес, описание, цена)
- Редактирование/удаление заказа клиентом
- Просмотр откликов на заказ клиентом
- Выбор исполнителя клиентом
- Отклики исполнителей на заказы
- Предложение заказа клиентом конкретному мастеру (прямое предложение)
- Просмотр заказов исполнителем (фильтрация по навыкам)
- Просмотр/редактирование/удаление профиля (обе роли)
- Оставление отзыва и рейтинга (1-5 звёзд)
- Статистика платформы (админ-бот)
- Поиск пользователей (админ-бот)
- Блокировка пользователей (админ-бот)
- Отправка ошибок админу через отдельный admin_bot
- Автоматическая очистка данных при блокировке бота пользователем
- Ежемесячный сброс счётчиков статистики

---

## Раздел 2. Карта текущей архитектуры Telegram-бота

```
zemiPro_site_django/
├── main.py                    # Точка входа: TachlesBotApp, GlobalMiddleware, SOCKS5-сессия
├── config.py                  # Загрузка API_TOKEN, DATABASE_URL из .env
├── db.py                      # Класс Database: пул, миграции, создание таблиц, seed категорий
├── user_status.py             # Обработка блокировки/разблокировки бота, очистка данных
├── Dockerfile                 # Python 3.11-slim
├── docker-compose.yml         # 4 сервиса: bot_main, bot_admin, db, web_api
├── .env                       # Токены, пароли, ID админа
├── requirements.txt           # Зависимости
│
├── menu/
│   ├── start.py               # Хендлер /start, выбор роли, главное меню
│   └── Job_support.py         # Тексты справки и поддержки
│
├── customer/
│   ├── registration.py        # Регистрация заказчика (FSM: имя → город → контакт)
│   ├── create_an_order.py     # Создание заказа (FSM: категория → адрес → описание → цена)
│   ├── edit_order.py          # Редактирование заказа (FSM: город → улица → описание)
│   ├── my_orders.py           # Просмотр/управление заказами клиента (отклики, выбор, завершение)
│   ├── select_specialist.py   # Поиск исполнителей, прямое предложение заказа
│   ├── leave_review.py        # Оставление отзыва (FSM: рейтинг → текст)
│   └── profile.py             # Просмотр/редактирование/удаление профиля заказчика
│
├── executor/
│   ├── registration_exe.py    # Регистрация исполнителя (FSM: имя → город → контакт → навыки → описание)
│   ├── new_orders.py          # Просмотр новых заказов, отклики, обработка предложений
│   ├── my_responses.py        # Мои отклики, принятие/отклонение предложений
│   ├── my_profile.py          # Просмотр/удаление профиля исполнителя
│   └── edit_profile.py        # Редактирование профиля исполнителя
│
├── categories/
│   ├── initial_data.py        # Начальные данные: 14 категорий + подкатегории (словарь)
│   └── keyboards.py           # Генерация InlineKeyboard для категорий из БД
│
├── admin_bot/
│   ├── admin_main.py          # Отдельный Telegram-бот для админа: статистика, поиск, бан
│   └── error_reporter.py      # Отправка отчётов об ошибках админу через admin_bot
│
└── tests/
    └── test_business_logic.py # Параллельный стресс-тест: 100 пользователей
```

**Ключевые наблюдения:**

1. **Два отдельных бота:** основной и админский — каждый запускается как отдельный Docker-контейнер.
2. **Нет `__init__.py` файлов** — импорты работают только через PYTHONPATH=/app в Docker.
3. **Web API объявлен, но отсутствует** — docker-compose ссылается на `web_api.server`, но кода нет.
4. **Связь с БД через asyncpg напрямую** — нет ORM, нет миграционной системы, таблицы создаются через raw SQL в `db.py`.
5. **Категории хранятся строкой** — `orders.category` и `workers.skills` работают с текстовыми названиями категорий, а не с foreign key.

---

## Раздел 3. Бизнес-логика, которую нужно сохранить

### 3.1. Создание заявки клиентом
- Клиент нажимает «Создать заказ»
- Выбирает категорию из Inline-кнопок (генерируются из БД)
- Вводит улицу и номер дома (город берётся из профиля клиента)
- Описывает задачу (минимум 30 символов)
- Указывает цену (число или «Договорная»)
- Заказ сохраняется со статусом «В обработке»
- Уведомляются мастера с соответствующими навыками (receive_notifications=TRUE)

### 3.2. Выбор категории
- Категории загружаются из таблицы `categories` (14 штук, из seed)
- Генерируются динамические Inline-кнопки
- Есть текстовая подсказка с описаниями категорий
- Подкатегории определены, но **закомментированы** (seed_subcategories не вызывается)

### 3.3. Города/районы
- Город — **текстовое поле** в профиле клиента/мастера (без привязки к справочнику)
- Нет таблицы городов — город вводится вручную
- Адрес заказа = "город, улица" — одна строка

### 3.4. Логика мастеров
- Регистрация: имя, город, контакт, выбор навыков (множественный), описание
- Навыки хранятся как `TEXT[]` (массив строк PostgreSQL)
- Просмотр заказов: фильтрация по навыкам мастера + статус «В обработке»
- Отклик: создаёт запись в `responses`, мастер получает контакт клиента
- Предложение от клиента: клиент может найти мастера и отправить ему прямое предложение
- Мастер может принять или отклонить предложение

### 3.5. Логика админа
- Отдельный Telegram-бот
- Просмотр статистики (пользователи, заказы, блокировки)
- Поиск пользователей по телефону/ID
- Блокировка пользователей (каскадное удаление профилей)
- Получение отчётов об ошибках от основного бота

### 3.6. Уведомления
- При создании заказа → уведомление мастерам с нужными навыками
- При отклике мастера → уведомление клиенту
- При выборе мастера → уведомление мастеру (с контактом клиента)
- При отмене исполнителя → уведомление мастеру
- При отзыве → уведомление мастеру
- При принятии/отклонении предложения → уведомления обеим сторонам
- Все уведомления отправляются через `bot.send_message()`

### 3.7. Хранение данных
| Таблица | Назначение |
|---------|------------|
| `users` |telegram_id, role, last_active, is_blocked |
| `clients` | user_id→users, full_name, city, contact |
| `workers` | user_id→users, name, city, skills (TEXT[]), contact, description, receive_notifications |
| `categories` | name, emoji, description |
| `subcategories` | category_id→categories, name |
| `worker_subskills` | worker_id→users, subcategory_id→subcategories |
| `orders` | client_id→users, worker_id→users, category, description, city, price, status |
| `responses` | order_id→orders, worker_id→users, message |
| `ratings` | order_id→orders, worker_id→users, client_id→users, rating, review_text |
| `error_logs` | error_text, context |
| `global_stats` | metric_name (PK), count |
| `category_stats` | category (PK), completed_count |

### 3.8. Статусы заказов
- `В обработке` — создан, ждёт откликов
- `В процессе` — выбран исполнитель
- `Выполнен` — работа завершена
- `Отменен` — удалён клиентом

### 3.9. Специальные статусы откликов
- `Предложение от заказчика` — клиент предложил заказ мастеру
- `Принял предложение заказчика` — мастер принял
- `Отказался` — мастер отклонил
- `Отстранен` — клиент заменил мастера

---

## Раздел 4. Что нужно изменить из-за перехода на Django

### 4.1. Отказ от FSM-диалогов
**Сейчас:** aiogram FSM (Finite State Machine) — состояния `full_name → city → contact → skills → description` в цепочке сообщений.
**Нужно:** Django Forms / Django Widgets на HTML-страницах. Один POST-запрос вместо 5 последовательных сообщений.

### 4.2. Замена Inline-кнопок на HTML-элементы
**Сейчас:** InlineKeyboardMarkup с callback_data, парсинг строк типа `find_workers_{order_id}_{offset}`.
**Нужно:** HTML-списки, ссылки, формы. Пагинация через GET-параметры.

### 4.3. Замена Reply-клавиатур на навигацию сайта
**Сейчас:** ReplyKeyboardMarkup («Заказчик», «Исполнитель», «Помощь»).
**Нужно:** Навигационное меню сайта, личный кабинет с разделами.

### 4.4. Отказ от `bot.send_message()` для уведомлений
**Сейчас:** Уведомления — прямые сообщения через Telegram Bot API.
**Нужно:** Система уведомлений (email, push, Telegram-бот как отдельный канал). Использовать Celery для фоновых задач.

### 4.5. Замена прямых SQL-запросов на Django ORM
**Сейчас:** asyncpg с raw SQL, пул соединений вручную.
**Нужно:** Django модели, менеджеры, QuerySet, миграции.

### 4.6. Замена role-based auth на Django auth
**Сейчас:** `role` — текстовое поле в таблице `users` ('client'/'worker'), Telegram ID как основной идентификатор.
**Нужно:** Django User model + профили (ClientProfile, WorkerProfile), сессии, авторизация.

### 4.7. Категории: текст → ForeignKey
**Сейчас:** `orders.category = 'Электрика'` (строка), `workers.skills = {'Электрика', 'Сантехника'}` (массив строк).
**Нужно:** Django ForeignKey + ManyToManyField.

### 4.8. Города: текст → справочник
**Сейчас:** Голый текст, без валидации.
**Нужно:** Таблица City, ForeignKey, SEO-оптимизированные URL (`/cities/tel-aviv/`).

### 4.9. Админ-бот → Django Admin + moderation panel
**Сейчас:** Отдельный Telegram-бот со статистикой, поиском и баном.
**Нужно:** Django Admin (встроенная админка) + кастомная страница модерации.

### 4.10. Тесты: pytest-asyncio → Django TestCase
**Сейчас:** Параллельный стресс-тест через asyncio.gather.
**Нужно:** Django TestCase, TransactionTestCase, fixtures.

---

## Раздел 5. Предлагаемая Django-архитектура

### 5.1. `core` — настройки и инфраструктура

**За что отвечает:** Базовые настройки проекта, общие классы, middleware, шаблоны.

**Модели:** Нет (или AbstractBaseUser, если кастомизировать).

**services.py:** Нет.

**Views/pages:**
- Главная страница
- robots.txt
- sitemap.xml
- 404/500 страницы

**Что переносится из бота:** Настройки из `config.py`, тексты из `menu/Job_support.py`.

### 5.2. `accounts` — пользователи и роли

**За что отвечает:** Регистрация, авторизация, профили заказчиков и мастеров, роли.

**Модели:**
```python
class User(AbstractUser):
    # Расширение Django User
    telegram_id = BigIntField(unique=True, null=True)  # для связи с Telegram
    role = CharField(choices=ROLES)  # 'client', 'worker', 'admin'
    is_blocked = BooleanField(default=False)
    last_active = DateTimeField(auto_now=True)

class ClientProfile(models.Model):
    user = OneToOneField(User)
    city = ForeignKey('locations.City')
    contact = CharField()

class WorkerProfile(models.Model):
    user = OneToOneField(User)
    city = ForeignKey('locations.City')
    contact = CharField()
    description = TextField()
    skills = ManyToManyField('marketplace.Category')
    receive_notifications = BooleanField(default=True)
```

**services.py:**
- `ClientRegistrationService` — регистрация/обновление заказчика
- `ExecutorRegistrationService` — регистрация/обновление мастера
- `ProfileService` — просмотр/редактирование/удаление профиля

**Views/pages:**
- `/register/` — регистрация
- `/login/` — авторизация
- `/profile/` — личный кабинет
- `/profile/edit/` — редактирование
- `/worker/<id>/` — публичный профиль мастера (SEO)

**Что переносится:**
- `customer/registration.py` → `accounts/services.py`
- `executor/registration_exe.py` → `accounts/services.py`
- `customer/profile.py` → `accounts/views.py`
- `executor/my_profile.py` → `accounts/views.py`
- `executor/edit_profile.py` → `accounts/views.py`

### 5.3. `marketplace` — категории, заявки, отклики

**За что отвечает:** Создание/управление заказами, отклики мастеров, статусы, отзывы.

**Модели:**
```python
class Category(models.Model):
    name = CharField(unique=True)
    slug = SlugField(unique=True)
    emoji = CharField(max_length=10)
    description = TextField(blank=True)

class Subcategory(models.Model):
    category = ForeignKey(Category)
    name = CharField()
    slug = SlugField()

class Order(models.Model):
    STATUSES = [('new', 'В обработке'), ('in_progress', 'В процессе'),
                ('completed', 'Выполнен'), ('cancelled', 'Отменен')]
    client = ForeignKey(User)
    worker = ForeignKey(User, null=True)
    category = ForeignKey(Category)
    subcategory = ForeignKey(Subcategory, null=True)
    description = TextField()
    city = ForeignKey('locations.City')
    address = CharField()
    price = CharField(default='Договорная')
    status = CharField(choices=STATUSES, default='new')
    created_at = DateTimeField(auto_now_add=True)

class Response(models.Model):
    order = ForeignKey(Order)
    worker = ForeignKey(User)
    message = TextField(blank=True)
    created_at = DateTimeField(auto_now_add=True)

class Rating(models.Model):
    order = OneToOneField(Order)
    worker = ForeignKey(User)
    client = ForeignKey(User)
    rating = IntegerField(validators=[MinValue(1), MaxValue(5)])
    review_text = TextField(blank=True)
    created_at = DateTimeField(auto_now_add=True)
```

**services.py:**
- `OrderService` — создание, редактирование, удаление заказа
- `ResponseService` — отклики, принятие/отклонение предложений
- `OrderMatchingService` — поиск мастеров для заказа, поиск заказов для мастера
- `RatingService` — отзывы и рейтинги

**Views/pages:**
- `/orders/` — список заказов
- `/orders/create/` — создание заказа (форма)
- `/orders/<id>/` — детали заказа
- `/orders/<id>/edit/` — редактирование
- `/orders/<id>/responses/` — отклики на заказ
- `/orders/<id>/select/<worker_id>/` — выбор мастера
- `/worker/dashboard/` — кабинет мастера (список доступных заказов + мои отклики)

**Что переносится:**
- `customer/create_an_order.py` → `marketplace/services.py`
- `customer/edit_order.py` → `marketplace/services.py`
- `customer/my_orders.py` → `marketplace/views.py`
- `customer/select_specialist.py` → `marketplace/services.py`
- `customer/leave_review.py` → `marketplace/services.py`
- `executor/new_orders.py` → `marketplace/views.py`
- `executor/my_responses.py` → `marketplace/views.py`

### 5.4. `locations` — города и районы

**За что отвечает:** Справочник городов и районов Израля.

**Модели:**
```python
class City(models.Model):
    name = CharField(unique=True)
    slug = SlugField(unique=True)
    is_active = BooleanField(default=True)

class District(models.Model):  # опционально, для будущего
    city = ForeignKey(City)
    name = CharField()
    slug = SlugField()
```

**services.py:** Минимальный — `CityService` для получения списка городов.

**Views/pages:**
- `/cities/` — список городов (SEO)
- `/cities/<slug>/` — страница города (SEO)
- `/cities/<slug>/<category>/` — город + категория (SEO)

**Что переносится:** Города из текстовых полей → справочник. Город в `client.city` и `worker.city` → ForeignKey.

### 5.5. `seo` — SEO-страницы

**За что отвечает:** Meta-теги, sitemap, SEO-оптимизированные страницы.

**Модели:**
```python
class SEOPage(models.Model):
    slug = SlugField(unique=True)
    title = CharField(max_length=200)
    meta_title = CharField(max_length=70)
    meta_description = CharField(max_length=160)
    content = TextField()
    is_published = BooleanField(default=True)
```

**services.py:** `SEOService` — генерация meta-тегов для динамических страниц.

**Views/pages:**
- `/sitemap.xml` — автогенерация
- `/robots.txt`
- Динамические SEO-страницы для категорий и городов

### 5.6. `notifications` — уведомления

**За что отвечает:** Отправка уведомлений пользователям.

**Модели:**
```python
class Notification(models.Model):
    user = ForeignKey(User)
    title = CharField()
    message = TextField()
    is_read = BooleanField(default=False)
    notification_type = CharField()  # 'order', 'response', 'review', etc.
    created_at = DateTimeField(auto_now_add=True)
```

**services.py:**
- `NotificationService` — создание и отправка уведомлений
- `TelegramNotificationService` — отправка через Telegram Bot API (опционально)

**Views/pages:**
- `/notifications/` — список уведомлений (AJAX)
- `/notifications/read/<id>/` — пометка как прочитанного

**Что переносится:** Логика `bot.send_message()` → фоновые задачи Celery.

### 5.7. `moderation` — жалобы и блокировки

**За что отвечает:** Жалобы, ручная проверка, блокировки.

**Модели:**
```python
class Complaint(models.Model):
    reporter = ForeignKey(User)
    target_user = ForeignKey(User, null=True)
    target_order = ForeignKey(Order, null=True)
    reason = TextField()
    status = CharField()  # 'pending', 'resolved', 'dismissed'
    admin_note = TextField(blank=True)
    created_at = DateTimeField(auto_now_add=True)
```

**services.py:** `ModerationService` — обработка жалоб, блокировка.

**Views/pages:**
- `/moderation/` — панель модерации (только для админов)
- `/complaint/create/` — форма подачи жалобы

### 5.8. `analytics` — статистика

**За что отвечает:** Базовая статистика платформы.

**Модели:**
```python
class GlobalStats(models.Model):
    metric_name = CharField(unique=True)
    count = IntegerField(default=0)

class CategoryStats(models.Model):
    category = OneToOneField(Category)
    completed_count = IntegerField(default=0)
```

**services.py:** `AnalyticsService` — сбор и агрегация статистики.

**Views/pages:**
- `/analytics/` — страница статистики (только для админов)

**Что переносится:**
- Логика сброса статистики из `db.py`
- `admin_bot/admin_main.py` → `analytics/views.py` + Django Admin

---

## Раздел 6. Минимальная рабочая версия сайта (production-ready, без платежей)

### Обязательные страницы и функционал:

**Страницы:**
1. **Главная страница** (`/`) — Hero-блок, список категорий, CTA «Создать заявку»
2. **Категории ремонта** (`/categories/`) — все категории с описаниями
3. **Страница категории** (`/categories/<slug>/`) — список мастеров в категории
4. **Города** (`/cities/`) — список городов Израиля
5. **Страница города** (`/cities/<slug>/`) — заявки и мастера города
6. **Город + категория** (`/cities/<slug>/<category>/`) — фильтрованный список
7. **Создание заявки** (`/orders/create/`) — форма (категория, адрес, описание, цена)
8. **Детали заявки** (`/orders/<id>/`) — полная информация
9. **Кабинет мастера** (`/worker/dashboard/`) — доступные заказы + мои отклики
10. **Профиль мастера** (`/worker/<id>/`) — публичная страница (SEO)
11. **Личный кабинет** (`/profile/`) — данные, мои заявки
12. **Админ-панель** (`/admin/`) — Django Admin

**Функционал:**
- Регистрация/авторизация (email + пароль)
- Создание заявки с формой
- Сохранение в PostgreSQL
- Уведомление админа о новой заявке (email)
- Базовая админка (Django Admin)
- Кабинет мастера (список заявок)
- SEO title/description для каждой страницы
- sitemap.xml
- robots.txt
- Чистая URL-структура

**Стек:**
- Django 5.x + PostgreSQL
- Django Templates (SSR) или HTMX для динамики
- Django Admin
- Celery + Redis (для уведомлений, поэтапно)

---

## Раздел 7. Что пока НЕ делать

| Функционал | Причина отсрочки |
|------------|-----------------|
| Платежи / подписки | Бизнес-модель ещё не определена |
| Покупка лидов | Нет монетизации |
| Сложный risk score | Нет данных для ML |
| Сложный рейтинг | Базового рейтинга достаточно |
| PostGIS radius search | Город — текст, нет координат |
| Сложные отзывы | Базовый рейтинг + текст足够 |
| Мобильное приложение | Веб-версия в приоритете |
| Многоролевая система (3+ ролей) | Две роли пока достаточно |
| Интеграция с Telegram как основной канал | Сайт — приоритет, Telegram — дополнение |
| A/B тестирование | Нет трафика |
| Кэширование (Redis) | Нет нагрузки |
| API для мобильного приложения | Нет приложения |

**Но архитектура должна_allow добавить это позже:**
- Модель Order уже содержит `price` — легко добавить оплату
- Модель User уже содержит `role` — легко добавить новые роли
- Category/Subcategory уже есть — легко добавить новые
- City уже есть как ForeignKey — легко добавить PostGIS
- Notification уже есть — легко добавить email/push/Telegram

---

## Раздел 8. План поэтапной переделки

### Этап 1 — Аудит текущего Telegram-бота ✅
- Изучить весь код (выполнено в рамках данного отчёта)
- Документировать бизнес-логику
- Определить что переносить, что переписывать
- Составить маппинг моделей: asyncpg → Django ORM

### Этап 2 — Создание Django-каркаса
- Инициализация Django-проекта (рядом или отдельно)
- Настройка PostgreSQL
- Создание структуры apps: core, accounts, marketplace, locations
- Настройка static/media
- Базовый шаблон (base.html)
- Навигация

### Этап 3 — Перенос моделей данных
- User (расширение AbstractUser)
- ClientProfile, WorkerProfile
- Category, Subcategory
- Order, Response, Rating
- City
- Создание миграций, проверка

### Этап 4 — Перенос категорий и городов
- Перенести `INITIAL_CATEGORIES` → Django data migration
- Создать справочник городов Израиля
- Создать slug для категорий и городов
- Заполнить данные

### Этап 5 — Создание формы заявки
- Django Form для создания заказа
- Валидация (категория, адрес, описание ≥30 символов, цена)
- Сохранение в БД
- Страница со списком заявок
- Детали заявки

### Этап 6 — Создание админки
- Django Admin для всех моделей
- Кастомизация отображения
- Фильтры, поиск
- Базовая статистика

### Этап 7 — Создание кабинета мастера
- Авторизация мастера
- Список доступных заказов (фильтрация по навыкам)
- Отклик на заказ
- Мои отклики
- Профиль мастера (просмотр/редактирование)

### Этап 8 — SEO-страницы
- Meta title/description для каждой страницы
- sitemap.xml (django.contrib.sites + django.contrib.sitemaps)
- robots.txt
- Canonical URLs
- Open Graph теги

### Этап 9 — Уведомления
- Подключить Redis
- Подключить Celery
- Email-уведомления о новых заявках
- Уведомления мастерам о новых откликах
- Уведомления клиентам о выборе мастера

### Этап 10 — Тестирование и подготовка к деплою
- Unit-тесты для services
- Интеграционные тесты дляcreateView
- Нагрузочное тестирование
- Настройка CI/CD
- Dockerfile для Django
- Деплой (VPS/Render/ Railway)

---

## Раздел 9. Риски

### 9.1. Технические риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Потеря данных при переносе | Средняя | Высокое | Data migration, резервное копирование |
| Несовместимость asyncpg ↔ Django ORM | Высокая | Среднее | Полный переход на Django ORM |
| Telegram-зависимость (telegram_id как PK) | Высокая | Среднее | Добавить email-авторизацию, telegram_id → nullable |
| Текстовые категории (без FK) | Средняя | Низкое | Data migration categories → slug |
| Отсутствие `__init__.py` | Низкая | Низкое | Добавить при создании Django-проекта |
| Сломать работающий бот при параллельной разработке | Средняя | Высокое | Django-проект в отдельном репозитории или ветке |

### 9.2. Архитектурные риски

1. **`telegram_id` как основной идентификатор** — в текущем боте все запросы идут через `telegram_id`. В Django нужно будет добавить email-авторизацию и сделать `telegram_id` опциональным полем.

2. **Текстовые категории в `orders.category`** — сейчас хранится строка `'Электрика'`. При переносе нужно: (а) создать таблицу Category с slug, (б) сделать data migration, (в) обновить FK.

3. **Массив `workers.skills`** — PostgreSQL TEXT[]. В Django это ManyToManyField. Миграция потребует ручного преобразования.

4. **Город как голый текст** — нет валидации, нет справочника. Вjango нужно: таблица City, ForeignKey, валидация.

5. **Статусы заказов как текст** — `'В обработке'`, `'В процессе'`, `'Выполнен'`, `'Отменен'`. В Django: choices на уровне модели.

6. **Два Docker-контейнера для ботов** — при переходе на Django один контейнер заменяется Django-приложением. Бот может остаться как отдельный сервис для уведомлений.

7. **Web API отсутствует** — docker-compose ссылается на `web_api.server`, но кода нет. Это можно игнорировать или удалить из compose.

### 9.3. Файлы, требующие осторожности

- `db.py` — содержит все миграции и seed. **Не трогать** до создания Django-моделей.
- `categories/initial_data.py` — начальные данные. Переносить как data migration.
- `admin_bot/error_reporter.py` — используется во всех файлах. Заменять последним.
- `.env` — содержит секреты. Не коммитить, не удалять.

---

## Раздел 10. Итоговая рекомендация

### Можно ли использовать текущий Telegram-бот как основу?

**Для бизнес-логики — да. Для кодовой базы — нет.**

Текущий бот написан на aiogram 3.x с прямым доступом к PostgreSQL через asyncpg. Это совершенно другая парадигма, чем Django. Копировать код напрямую нельзя — только переносить бизнес-логику.

### Что стоит сохранить:
1. **Структуру моделей данных** — `users`, `clients`, `workers`, `orders`, `responses`, `ratings`, `categories` — это хорошая основа
2. **Бизнес-логику** — создание заказа, отклики, выбор мастера, отзывы, уведомления
3. **Начальные данные категорий** — `INITIAL_CATEGORIES` и `INITIAL_SUBCATEGORIES`
4. **Статусы заказов** — `В обработке → В процессе → Выполнен`
5. **Специальные статусы откликов** — `Предложение от заказчика`, `Отказался`, `Отстранен`
6. **Логику каскадного удаления** — при удалении профиля

### Что стоит переписать:
1. **Весь UI** — Telegram-кнопки → HTML-формы
2. **Авторизацию** — Telegram ID → Django auth + email
3. **Доступ к БД** — asyncpg → Django ORM
4. **Уведомления** — `bot.send_message()` → Celery + email/Telegram
5. **Админ-панель** — Telegram-бот → Django Admin
6. **Тесты** — pytest-asyncio → Django TestCase

### С какого этапа лучше начинать:
**Этап 2 — создание Django-каркаса.** Не пытаться «переписать бот на Django» за один раз. Создать чистый Django-проект, постепенно переносить бизнес-логику.

### Первый безопасный шаг после анализа:
**Создать Django-проект с базовой структурой apps и подключить к той же PostgreSQL базе (read-only).** Это позволит:
1. Проверить совместимость с существующими данными
2. Не потерять ничего в текущем боте
3. Постепенно добавлять Django-модели рядом с raw SQL
4. Запускать бота и сайт параллельно на время перехода

Критически важно: **не пытаться остановить бота до полного готовности сайта.** Переход должен быть поэтапным и непрерывным — бот продолжает работать, пока сайт не наберет enough функциональности.
