# DJANGO_SETUP.md — Запуск Django-проекта ZemiPro

> **ИСТОРИЧЕСКИЙ ДОКУМЕНТ.** Он фиксирует раннее состояние Django-прототипа и не является нормативным описанием архитектуры или production-развёртывания. Актуальные решения: один Django + PostgreSQL, без Telegram/PSEO/SQLite и импорта старых баз; создание и управление заказом доступны только зарегистрированному пользователю. До обновления окружений в 01.1 команды и имена Docker-файлов ниже следует сверять с текущим деревом и `README.md`.

## Структура проекта

```
zemipro_web/
├── manage.py                    # ТочкаВхода Django
├── requirements.txt             # Зависимости
├── .env.example                 # Пример переменных окружения
├── Dockerfile.django            # Docker-образ для Django
├── docker-compose.django.yml    # Docker Compose для Django
├── core/                        # Настройки проекта
│   ├── __init__.py
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
├── apps/                        # Django-приложения
│   ├── __init__.py
│   ├── accounts/                # Пользователи, роли, авторизация
│   ├── marketplace/             # Категории, заявки, отклики
│   ├── locations/               # Города и районы
│   ├── seo/                     # SEO-страницы
│   ├── notifications/           # Уведомления
│   ├── moderation/              # Модерация
│   └── analytics/               # Статистика
├── templates/                   # HTML-шаблоны
│   ├── base.html
│   └── pages/
│       ├── home.html
│       ├── categories.html
│       ├── category_detail.html
│       ├── cities.html
│       ├── city_detail.html
│       ├── order_create.html
│       └── 404.html
└── static/                      # Статические файлы
    ├── css/style.css
    └── js/main.js
```

## Быстрый старт (локально)

### 1. Перейти в папку проекта

```bash
cd zemipro_web
```

### 2. Создать виртуальное окружение

```bash
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # macOS/Linux
```

### 3. Установить зависимости

```bash
pip install -r requirements.txt
```

### 4. Настроить переменные окружения

```bash
cp .env.example .env
```

Отредактируйте `.env` — укажите реальные данные PostgreSQL:

```
DJANGO_SECRET_KEY=your-real-secret-key
DJANGO_DEBUG=True
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1

DB_NAME=zemipro_db
DB_USER=postgres
DB_PASSWORD=your-password
DB_HOST=localhost
DB_PORT=5432
```

### 5. Создать базу данных

В PostgreSQL создайте базу данных:

```sql
CREATE DATABASE zemipro_db;
```

### 6. Выполнить миграции

```bash
python manage.py migrate
```

### 7. Создать суперпользователя

```bash
python manage.py createsuperuser
```

### 8. Заполнить категории и города

```bash
python manage.py seed_repair_categories
python manage.py seed_israel_cities
```

### 9. Запустить сервер

```bash
python manage.py runserver
```

Сайт доступен: http://127.0.0.1:8000/
Админ-панель: http://127.0.0.1:8000/admin/

## Запуск через Docker

### 1. Создать `.env` (см. выше)

### 2. Запустить

```bash
docker-compose -f docker-compose.django.yml up --build
```

Сайт доступен: http://localhost:8000/

## Доступные URL

| URL | Описание |
|-----|----------|
| `/` | Главная страница |
| `/categories/` | Все категории |
| `/categories/<slug>/` | Страница категории |
| `/cities/` | Все города |
| `/cities/<slug>/` | Страница города |
| `/orders/create/` | Создание заявки |
| `/orders/<id>/` | Просмотр заявки |
| `/orders/<id>/respond/` | Отклик на заявку |
| `/orders/<id>/responses/<id>/accept/` | Выбор мастера (POST) |
| `/orders/<id>/cancel/` | Отмена заявки (POST) |
| `/orders/<id>/complete/` | Завершение заявки (POST) |
| `/orders/<id>/review/` | Оставить отзыв |
| `/worker/<id>/` | Публичный профиль мастера |
| `/client/dashboard/` | Кабинет клиента |
| `/worker/dashboard/` | Кабинет мастера |
| `/accounts/register/` | Регистрация |
| `/accounts/login/` | Вход |
| `/accounts/logout/` | Выход |
| `/accounts/client/profile/` | Профиль клиента |
| `/accounts/worker/profile/` | Профиль мастера |
| `/notifications/` | Уведомления |
| `/notifications/<id>/read/` | Отметить прочитанным (POST) |
| `/notifications/read-all/` | Отметить все прочитанными (POST) |
| `/moderation/complaint/` | Подать жалобу |
| `/admin/` | Django Admin |

## Что сделано на Этапе 2

- Инициализирован Django проект
- Создано 7 apps: accounts, marketplace, locations, seo, notifications, moderation, analytics
- Настроена PostgreSQL через переменные окружения
- Создан базовый шаблон `base.html`
- Создана главная страница с категориями и CTA
- Созданы страницы категорий, городов, формы заявки
- Создан CSS-дизайн (базовый, адаптивный)
- Подготовлен Docker-композ для деплоя

## Что сделано на Этапе 3

- Созданы модели: User, ClientProfile, WorkerProfile, City, Category, Subcategory, Order, Response, Rating, GlobalStats, CategoryStats
- Настроен кастомный `AUTH_USER_MODEL`
- Зарегистрированы модели в Django Admin
- Созданы заготовки services.py

## Что сделано на Этапе 4

- Создана management-команда `seed_repair_categories` (8 категорий, 56 подкатегорий)
- Создана management-команда `seed_israel_cities` (25 городов)
- Обновлена документация

## Что сделано на Этапе 5

- Добавлены поля `customer_name` и `customer_phone` в модель `Order`
- Поле `client` первоначально было nullable; миграция `0003_require_order_owner` сделала владельца обязательным. Анонимные заявки запрещены.
- Создана форма `OrderCreateForm` с валидацией
- Созданы views: `order_create_view`, `order_detail_view`
- Созданы шаблоны: `order_create.html`, `order_detail.html`
- Добавлен маршрут `/orders/<id>/`
- Обновлён Django Admin для отображения контактных данных
- Views подключены к БД (категории, города загружаются из моделей)

## Как создать тестовую заявку

1. Заполните seed-данные:
```bash
python manage.py seed_repair_categories
python manage.py seed_israel_cities
```

2. Запустите сервер:
```bash
python manage.py runserver
```

3. Зарегистрируйте тестового заказчика и войдите в аккаунт: http://127.0.0.1:8000/accounts/register/

4. Откройте http://127.0.0.1:8000/orders/create/ в авторизованной сессии. Гость будет перенаправлен на страницу входа.

5. Заполните форму синтетическими данными:
   - Имя: Тест
   - Телефон: +972501234567
   - Категория: Сантехника
   - Город: Тель-Авив
   - Адрес: Herzl 45
   - Описание: Протекает кран на кухне, нужно починить или заменить смеситель
   - Бюджет: 300

6. Нажмите «Отправить заявку»

7. Откроется страница заказа с номером и статусом; владельцем будет текущий пользователь.

8. Заявку можно посмотреть в Django Admin: http://127.0.0.1:8000/admin/

## Как проверить кабинет мастера

1. Запустите миграции и seed:
```bash
python manage.py migrate
python manage.py seed_repair_categories
python manage.py seed_israel_cities
```

2. Зарегистрируйте отдельные тестовые аккаунты заказчика и мастера. Не используйте одну заявку для отклика её владельца.

3. Под аккаунтом заказчика создайте тестовую заявку: http://127.0.0.1:8000/orders/create/

4. Заполните профиль мастера: http://127.0.0.1:8000/worker/profile/
   - Выберите город
   - Укажите контакт
   - Опишите услуги (минимум 20 символов)
   - Выберите категории работ

5. Откройте кабинет мастера: http://127.0.0.1:8000/worker/dashboard/
   - Увидите подходящие заявки
   - Нажмите «Откликнуться» на любой заявке

6. Отправьте отклик (сообщение необязательно)

7. Проверьте отклик в Django Admin: http://127.0.0.1:8000/admin/marketplace/response/

## Что сделано на Этапе 6

- Создана регистрация, вход, выход (Django auth)
- Создана форма `WorkerProfileForm` для профиля мастера
- Создана форма `ResponseCreateForm` для отклика
- Созданы services: `create_or_update_worker_profile`, `get_worker_profile`, `get_available_orders_for_worker`, `create_response`
- Созданы views: `worker_profile_view`, `worker_dashboard_view`, `order_respond_view`
- Созданы шаблоны: `login.html`, `register.html`, `worker_profile.html`, `worker_dashboard.html`, `order_respond.html`
- Обновлён `order_detail.html` — кнопка «Откликнуться» для мастеров
- Обновлена навигация — ссылки на кабинет, профиль, вход/выход
- Обновлён Django Admin для Response и WorkerProfile
- Обновлён `LOGIN_REDIRECT_URL` → `/worker/dashboard/`

## Как проверить полный сценарий клиент → мастер → отзыв

1. Запустите миграции и seed:
```bash
python manage.py migrate
python manage.py seed_repair_categories
python manage.py seed_israel_cities
```

2. Зарегистрируйте клиента: http://127.0.0.1:8000/accounts/register/

3. Заполните профиль клиента: http://127.0.0.1:8000/accounts/client/profile/
   - Город: Тель-Авив
   - Контакт: +972501234567

4. Создайте заявку: http://127.0.0.1:8000/orders/create/
   - Категория: Сантехника
   - Город: Тель-Авив
   - Описание: Протекает кран на кухне, нужно починить смеситель (минимум 30 символов)

5. Выйдите и зарегистрируйте мастера: http://127.0.0.1:8000/accounts/register/

6. Заполните профиль мастера: http://127.0.0.1:8000/accounts/worker/profile/
   - Город: Тель-Авив
   - Категории: Сантехника

7. Откройте кабинет мастера: http://127.0.0.1:8000/worker/dashboard/
   - Нажмите «Откликнуться» на заявке

8. Войдите как клиент, откройте заявку
   - Нажмите «Выбрать мастера»

9. Отметьте заявку выполненной (кнопка «Отметить выполненной»)

10. Оставьте отзыв (кнопка «Оставить отзыв»)

11. Проверьте всё в Django Admin: http://127.0.0.1:8000/admin/

## Что сделано на Этапе 7

- Создана `ClientProfileForm` для профиля клиента
- Создана `RatingCreateForm` для отзывов
- Созданы services: `create_or_update_client_profile`, `get_client_profile`, обновлён `accept_response`
- Созданы views: `client_profile_view`, `client_dashboard_view`, `order_accept_response_view`, `order_cancel_view`, `order_complete_view`, `rating_create_view`
- Созданы шаблоны: `client_profile.html`, `client_dashboard.html`, `rating_create.html`
- Обновлён `order_detail.html` — отклики для владельца, кнопки выбора/отмены/завершения, блок отзыва
- Обновлена навигация — кабинет клиента, профиль клиента
- Обновлён Django Admin — client/worker в list_display Order, created_at для Rating

## Следующие шаги (Этап 8)

1. Публичный профиль мастера (SEO)
2. Пагинация
3. Фильтрация по городу и категории
4. Модерация

## Уведомления в браузере

### Где находится страница уведомлений

http://127.0.0.1:8000/notifications/

### Как создаются уведомления

Уведомления создаются автоматически при ключевых бизнес-событиях:

| Событие | Получатель | Тип |
|---------|-----------|-----|
| Клиент создал заявку | Клиент | `order_created` |
| Мастер откликнулся | Клиент (если авторизован) | `new_response` |
| Клиент выбрал мастера | Выбранный мастер | `response_accepted` |
| Клиент выбрал мастера | Остальные мастера | `response_rejected` |
| Клиент отменил заявку | Все откликнувшиеся мастера | `order_cancelled` |
| Клиент завершил заявку | Мастер | `order_completed` |
| Клиент оставил отзыв | Мастер | `review_created` |

### Как проверить вручную

1. Зарегистрируйте двух пользователей (клиента и мастера)
2. Создайте заявку как клиент → клиент получит уведомление
3. Откликнитесь как мастер → клиент получит уведомление
4. Выберите мастера как клиент → мастер получит уведомление
5. Откройте http://127.0.0.1:8000/notifications/
6. Проверьте счётчик в шапке сайта

### Технические детали

- Модель: `apps.notifications.models.Notification`
- Сервис: `apps.notifications.services`
- Context processor: `apps.notifications.context_processors.notifications_counter`
- Шаблон: `templates/notifications/notification_list.html`

## Что сделано на Этапе 9

- Создана модель `Notification` с индексами
- Созданы services: `create_notification`, `get_user_notifications`, `get_unread_count`, `mark_notification_read`, `mark_all_notifications_read`
- Создан context processor `notifications_counter` для шапки сайта
- Созданы views: `notification_list_view`, `notification_mark_read_view`, `notification_mark_all_read_view`
- Создан шаблон `notification_list.html`
- Добавлены уведомления во все бизнес-события (заявка, отклики, выбор мастера, отмена, завершение, отзыв)
- Обновлена навигация — ссылка «Уведомления» с бейджем количества непрочитанных
- Обновлён Django Admin для Notification

## Что сделано на Этапе 10

### Публичный профиль мастера

- Создан view `worker_public_profile_view` по URL `/worker/<int:pk>/`
- Создан шаблон `worker_public_profile.html` — имя, город, описание, категории, рейтинг, отзывы
- Ссылки на профиль мастера доступны со страниц категорий и городов

### Пагинация

- Кабинет мастера (список доступных заказов) — 10 на страницу
- Список мастеров на странице категории — 10 на страницу
- Список мастеров на странице города — 10 на страницу
- Список уведомлений — 20 на страницу
- Навигация: Назад / Страница X из Y / Далее

### Фильтрация

- Страница категории: фильтр по городу (select)
- Страница города: фильтр по категории (select)
- Фильтры работают через GET-параметры, сохраняют состояние при пагинации

### Новые URL

| URL | Описание |
|-----|----------|
| `/worker/<id>/` | Публичный профиль мастера |

## Что сделано на Этапе 11

### Модерация и жалобы

- Создана модель `Complaint` с причинами: спам, мошенничество, неприемлемый контент, фейковый профиль, плохое качество, другое
- Создана форма `ComplaintForm` для подачи жалоб
- Созданы services: `create_complaint`, `resolve_complaint`, `dismiss_complaint`, `block_user`, `unblock_user`
- Создан view `complaint_create_view` — форма подачи жалобы с привязкой к пользователю/заказу/отзыву
- При подаче жалобы админы получают уведомления
- В Django Admin: список жалоб, фильтры, поиск, действия «Рассмотреть», «Отклонить», «Заблокировать», «Разблокировать»
- Кнопка «Пожаловаться» на странице заявки (для не-владельцев)
- Ссылка «Пожаловаться на пользователя» на публичном профиле мастера

### Новые URL

| URL | Описание |
|-----|----------|
| `/moderation/complaint/` | Форма подачи жалобы |
| `/moderation/complaint/?user=<id>` | Жалоба на пользователя |
| `/moderation/complaint/?order=<id>` | Жалоба на заявку |

### Как проверить

1. Откройте публичный профиль мастера: `/worker/<id>/`
2. Нажмите «Пожаловаться на пользователя»
3. Выберите причину, опишите проблему
4. Отправьте жалобу
5. Откройте Django Admin: `/admin/moderation/complaint/`
6. Выберите жалобу, выполните действие «Рассмотреть» или «Заблокировать»

## Следующие шаги (Этап 12)

1. Тестирование всего функционала
2. Подготовка к деплою
3. SEO-оптимизация
