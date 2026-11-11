# ZemiPro — инвентаризация существующих реализаций (00.1)

**Срез:** 2026-11-11 · **Статус:** `DONE / INDEPENDENTLY_VERIFIED`.
**Репозитории/ревизии:** единственный runtime — `maxim9362/zemiPro_site_django`, проверенная точка ветки `stage-00-audit@94526454ff0b1102e038f5a74ab5aeb3d3be67f9`; удалённые Telegram/PSEO сведения ниже являются только исторической инвентаризацией. Отдельно существует не объединённая работа этапа 01.
**Источники требований:** `AGENTS.md`, `docs/ROADMAP.md`, `docs/DEVELOPMENT_PLAN.md`, `docs/TECHNICAL_SPEC.md`, ADR-0001/0002/0003. Требования v1.3 PR #5 сохранены в текущей ветке без merge PR #5.
**Граница проверки:** независимый аудит проверил дерево, Django-код, миграции, документы и тесты; 17/17 Django tests, миграции и synthetic PostgreSQL restore прошли. Production, реальные базы/media и секретные значения не открывались. Первоначальные `NOT_RUN` ниже относятся к историческому срезу 2026-11-10 и переопределены текущими результатами там, где это указано.

## Решение владельца 2026-11-10: Telegram исключён из целевой архитектуры

Старый Telegram-бот **не нужен** ZemiPro и **не подлежит переносу, интеграции или дальнейшей поддержке** в Django. Все прежние рекомендации матрицы ниже, где предполагалось `ADAPT` Telegram-код или его бизнес-сценарии, считаются **устаревшими** и заменяются на `REJECT` для будущего runtime. Исторический Telegram-код был источником инвентаризации 00.1; теперь 28 runtime-файлов удалены **из текущего дерева ветки `stage-00-audit`**, но сохраняются в `main` и истории Git до итогового решения. Не переносить Telegram-пользователей/заказы/SQL автоматически. Рабочие БД и серверы не затронуты. См. `docs/STAGE_00_LEGACY_REMOVAL.md`. Основание: прямое решение владельца, запись `docs/DECISIONS/ADR-0001-DJANGO-ONLY-NO-TELEGRAM.md`.

## Решение владельца 2026-11-10: старый PSEO не переносится

Старые Flask/PSEO код, статьи, генераторы, шаблоны и SQLite-данные **не используются** при создании нового Django-сайта. Единственное исключение — список публичных URL/slug, необходимый для оценки поисковой видимости и точечных перенаправлений. Предыдущие предложения матрицы `ADAPT` PSEO-кода/контента переопределяются на `REJECT`; сохраняется только `REVIEW` URL с возможным `301` на подходящий новый адрес. Подробности: `docs/DECISIONS/ADR-0002-REBUILD-WITH-URL-ONLY.md`. Это не означает пересоздания Django-проекта или удаления старого работающего сайта прямо сейчас.

## 1. Структура и главные зависимости

- **Web:** `zemipro_web/` — существующий Django-проект с `apps/accounts`, `marketplace`, `locations`, `seo`, `notifications`, `moderation`, `analytics`; `core/urls.py` соединяет эти приложения; Django ORM + PostgreSQL, миграции в приложениях. В `main` ещё единый `core/settings.py`. Ветка `stage-01-stabilization` уже содержит раздельные конфигурации и дополнительные тесты 01.1; её не переносить в этап 00.
- **Telegram legacy (архив, исключён из разработки):** корневые `main.py`, `db.py`, `customer/`, `executor/`, `admin_bot/`, `categories/`, `tests/`; aiogram/asyncpg и самостоятельная SQL-схема. Не является требованием к функциональности новой платформы, не запускается и не мигрируется автоматически.
- **PSEO:** отдельный Flask-проект с `app.py`, `freez.py`, `data/categories.py`, `data/regions.py`, `templates/`, `index_site/generate_list.py`, локальными SQLite-хранилищами. `FLOW_MAP.master` активен, `FLOW_MAP.uslugi` выключен в проверенной ревизии; активные регионы задаёт код. Наличие маршрута или генератора не подтверждает доступность опубликованного URL.
- **Проверки:** 17 Django-тестов целевой ветки прошли на изолированной PostgreSQL, включая permissions и concurrency: `accounts/tests/test_auth.py` (3), `marketplace/tests/test_order_security.py` (10), `test_order_concurrency.py` (1), `test_catalog.py` (3). Тесты иных веток и удалённых legacy-систем не входят в приёмку 00.1.

## 2. Матрица функций и решений

Определения: **CODE_PRESENT** — исходники/маршруты найдены без гарантии работоспособности; **REPORTED_PASS** — результат ранее сообщённых Codex-тестов, не повторная проверка; **UNVERIFIED** — поведения и/или данные не проверены. Решения `REUSE / ADAPT / REWRITE / REJECT` предварительные для планирования, не разрешение менять код.

| Функция | Источник / код | Состояние и проверки | Решение | Целевой этап |
| --- | --- | --- | --- | --- |
| Регистрация и вход | Django `accounts/models.py`, `forms.py`, `views.py` | CODE_PRESENT; 3 auth-теста, ранее REPORTED_PASS | REUSE; расширить подтверждение контактов | 03.2 |
| Клиент и мастер в одном аккаунте | Django `User`, `ClientProfile`, `WorkerProfile`, `accounts/services.py` | CODE_PRESENT; полный multi-role workflow UNVERIFIED | ADAPT, сохранить единую модель пользователей | 03.1, 03.3–03.4 |
| Категории и подкатегории | Django `marketplace/models.py`, `seed_repair_categories.py`; bot `categories/initial_data.py` | CODE_PRESENT; 3 теста каталога ранее REPORTED_PASS, сквозной импорт не проверен | ADAPT; объединить словари без дублей и потери slug | 02.1, 02.6 |
| Города и языковые имена | Django `locations/models.py`, `seed_israel_cities.py`; PSEO `data/regions.py` | CODE_PRESENT, `City.localized_name`; тесты RU/EN/HE ранее REPORTED_PASS; зоны обслуживания UNVERIFIED | ADAPT; не переносить старые ID вслепую | 02.2–02.4 |
| Создание заявки и право владения | Django `marketplace/Order`, `views.py`, `services.py`, `0003_require_order_owner.py` | CODE_PRESENT; тесты owner/anon и БД ранее REPORTED_PASS; реальные legacy-строки UNVERIFIED | REUSE + адаптация дальнейших правил заказа | 01.2, 04 |
| Приватность заявки/управление по ID | Django `marketplace/views.py`, `services.py`, HTML-шаблоны | CODE_PRESENT; ранее REPORTED_PASS для owner/assignee/staff, запрета чужих операций | REUSE; повторная проверка при появлении API/чата | 03.6, 04, 10 |
| Отклик и назначение одного мастера | Django `Response`, `create_response`, `accept_response` | CODE_PRESENT; тест конкурентного выбора на PostgreSQL ранее REPORTED_PASS, сейчас NOT_RUN | REUSE + ADAPT под полный жизненный цикл | 06 |
| Список доступных заявок мастеру | Django `get_available_orders_for_worker`, `worker_dashboard_view` | CODE_PRESENT; локальная сортировка, self-response и приватные поля тестировались; подбор целиком UNVERIFIED | ADAPT | 05–06 |
| Каталог и публичный профиль мастера | Django `marketplace/views.py`, `worker_public_profile.html`, `category_detail.html` | CODE_PRESENT; агрегация рейтинга и страницы ранее REPORTED_PASS; расширенный поиск UNVERIFIED | ADAPT | 03.4, 05 |
| Отзывы о завершённом заказе | Django `Rating`, `rating_create_view`, `marketplace/admin.py` | CODE_PRESENT; отдельные права доступа частично тестировались; антифрод/полный E2E UNVERIFIED | ADAPT | 07.4 |
| Уведомления | Django `Notification`, `notifications/services.py`, `views.py` | CODE_PRESENT, создание/прочтение; доставка email/push/anti-duplicate UNVERIFIED | ADAPT | 07.3 |
| Жалобы и блокировки | Django `Complaint`, `moderation/services.py`, `views.py` | CODE_PRESENT; `block_user` и `is_blocked` существуют, но полный запрет действий блокированному UNVERIFIED | ADAPT | 03.6, 07.5 |
| Сводная аналитика | Django `analytics/GlobalStats`, `CategoryStats`, `services.py` | CODE_PRESENT; наполнение и точность данных UNVERIFIED | ADAPT | 09 |
| SEO в Django | `apps/seo/models.py`, `views.py`, `urls.py` | Сквозной SEO-контент отсутствует; текущие model/view — заглушки | REWRITE в Django; старый код/контент не использовать, URL только REVIEW | 08 |
| Чат заказчика и мастера | Нет отдельного Django chat app / подтверждённого chat API в `core/urls.py` | NOT_IMPLEMENTED в проверенной web-кодовой базе | REWRITE (добавить общее серверное правило доступа) | 07.1–07.2 |
| Версионированный мобильный REST API | Django URL-конфигурация и приложения | Нет подтверждённого DRF/API v1; Flask PSEO `/api/v1/stats/…` — не мобильный API маркетплейса | REWRITE/ADAPT без дубля бизнес-логики | 10 |
| Историческая регистрация и заявки Telegram | Удалённые `executor/`, `customer/` | Только исторически инвентаризированы; runtime исключён | REJECT код, данные, правила и словари как источник новой реализации | 02–04 |
| Исторические поиск и отклики Telegram | Удалённые `customer/`, `executor/` | Только исторически инвентаризированы | REJECT код, SQL и данные; целевой сценарий проектировать по действующему ТЗ | 05–06 |
| Историческое администрирование Telegram | Удалённый `admin_bot/` | Только исторически инвентаризировано | REJECT; развивать существующие Django Admin/модерацию независимо | 03.6, 07.5 |
| Историческая SQL-схема Telegram | Удалённый `db.py` | Схема не является источником данных для Django | REJECT импорт и сопоставление ID | — |
| Исторические PSEO-хабы и статьи | Удалённый Flask/PSEO | Сохраняется только выборка публичных URL; код и контент недоступны и не требуются | REJECT код/контент; REVIEW только URL без автоматических 301 | 00.4, 08 |
| Исторические PSEO словари и генераторы | Удалённый PSEO | Не являются источником нового каталога или текстов | REJECT полностью | — |
| Четыре целевых UI заказчика/мастера | Утверждённые внешние HTML-макеты; Django `templates/` | Требования зафиксированы, соответствие текущих шаблонов утверждённому UI UNVERIFIED | ADAPT backend contracts, не менять дизайн в 00.1 | 03–07 |

## 3. Карта зависимостей для следующего аудита

1. `accounts.User` → `ClientProfile` / `WorkerProfile` → `marketplace.Order.client` / `Order.worker` → `Response` / `Rating`, а также `Notification` и `Complaint`. Точные FK и действия при удалении сверить по миграциям в 01.2.
2. `Category` / `Subcategory` + `City` — общие справочники для заказов, профилей, поиска и будущего SEO. Единственный source of truth — Django/PostgreSQL; Telegram/PSEO не являются донорами данных.
3. Старые Telegram/PostgreSQL и Flask/SQLite схемы не импортируются, не сопоставляются с Django ID и не входят в план резервного восстановления.
4. Существующий `TECHNICAL_REPORT.md` — исторический архитектурный отчёт, не доказательство текущего успешного выполнения. Статусы подтверждаются тестами и отдельными проверками.
5. `stage-01-stabilization` — отдельная рабочая ветка для этапа 01 (01.1); её не редактировать в ходе этапа 00. После объединения документационного PR #5 синхронизировать активные ветки с обновлённым `main` без force-push.

## 4. Неподтверждённые данные и блокирующие зависимости

- **00.2 — секреты:** в дереве приватного PSEO находятся `.env`, `index_site/service_account.json`; также SQLite `.db`. Проверены только **имена файлов**, не значения и не содержимое. Владельцу нужны проверка действительности, разрешённая ротация/удаление из будущего дерева, закрытый план обработки истории. Не раскрывать секреты в PR.
- **00.3 — backup/restore:** synthetic PostgreSQL backup/restore подтверждён независимым аудитом; существование рабочей Django-БД с ценными пользовательскими данными по доступной конфигурации не подтверждено. Legacy Telegram/PSEO базы не восстанавливать.
- **00.4 — SEO URL:** требуется `docs/SEO_URL_INVENTORY.csv` из генератора, sitemap, фактических HTTP-ответов и (при наличии) GSC. Существующие Flask-маршруты не равны опубликованному списку.
- **00.5 — архитектура:** ADR исключают перенос Telegram/PSEO. Проверяются только Django migrations и новые seed-команды; legacy URL рассматриваются отдельно в 00.4/08.
- **00.6 — диагностика:** нужен воспроизводимый baseline проверок `manage.py check`, isolated migrate, smoke, Docker/ограничения; полученные от Codex результаты 17/20 тестов не повторялись.
- **Риски:** отсутствие работающего чата, REST API и полноценного SEO в Django — предмет следующих этапов, а не ошибки, устраняемые в 00.1. Не запускать production/deploy/изменения DNS до соответствующего gate.

## 5. Критерии приёмки 00.1 и передача на проверку

- [x] Перечислены существующие приложения, старые модули и PSEO активы.
- [x] Для функций указан источник, степень подтверждения и решение `REUSE/ADAPT/REWRITE/REJECT`.
- [x] Связи и риски помечены, неизвестное явно `UNVERIFIED`.
- [x] Секреты и базы не открывались и не включались в документацию.
- [ ] Итоговая сверка матрицы и приёмка после 00.1–00.6 (по решению владельца без промежуточного Codex Cloud). До неё статус 00.1 остаётся `IN_PROGRESS`.

**Проверки 00.1:** `STATIC_INSPECTION: PASS` (структуры и выбранные исходники GitHub), `Django tests: NOT_RUN`, `migrations: NOT_RUN`, `production: NOT_TOUCHED`. Матрица не подтверждает наличие реальных данных или рабочий запуск сервисов.
