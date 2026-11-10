# ZemiPro — инвентаризация существующих реализаций (00.1)

**Срез:** 2026-11-10 · **Статус:** \`IN_PROGRESS / STATICALLY_INVENTORIED\` (техническая инвентаризация выполнена; выборочная независимая проверка и приёмка ещё нужны).
**Репозитории/ревизии:** Django и Telegram \`maxim9362/zemiPro_site_django@ba337737c6912ebaa922ae9b5cafebc722cbd71b\` (\`main\`); PSEO \`maxim9362/zemipro_site_pseo\`, \`main\` (дерево \`def493642dbb86ffe7543efecb81f08fecf50e60\`). Отдельно учтена *не объединённая* разработка \`stage-01-stabilization\` (подэтап 01.1, коммит \`5cdb19c6\`).
**Источники требований:** \`AGENTS.md\`, \`docs/ROADMAP.md\`, \`docs/DEVELOPMENT_PLAN.md\`, \`docs/TECHNICAL_SPEC.md\`; PR #5 с обновлением нормативных документов до v1.3.0 открыт и не является частью этого среза.
**Граница проверки:** читались структуры репозиториев и обычные исходники/модели/тесты; команды, сетевой запуск, миграции, реальный Docker, SQL-запросы и загрузка закрытых данных не выполнялись. Содержимое \`.env\`, JSON учётных данных и файлов баз PSEO **не открывалось**, секреты/PII не копировались в документ.

## 1. Структура и главные зависимости

- **Web:** \`zemipro_web/\` — существующий Django-проект с \`apps/accounts\`, \`marketplace\`, \`locations\`, \`seo\`, \`notifications\`, \`moderation\`, \`analytics\`; \`core/urls.py\` соединяет эти приложения; Django ORM + PostgreSQL, миграции в приложениях. В \`main\` ещё единый \`core/settings.py\`. Ветка \`stage-01-stabilization\` уже содержит раздельные конфигурации и дополнительные тесты 01.1; её не переносить в этап 00.
- **Telegram legacy:** корневые \`main.py\`, \`db.py\`, \`customer/\`, \`executor/\`, \`admin_bot/\`, \`categories/\`, \`tests/\`; aiogram/asyncpg и самостоятельная SQL-схема. Это *источник бизнес-правил*, а не вторая целевая production-БД.
- **PSEO:** отдельный Flask-проект с \`app.py\`, \`freez.py\`, \`data/categories.py\`, \`data/regions.py\`, \`templates/\`, \`index_site/generate_list.py\`, локальными SQLite-хранилищами. \`FLOW_MAP.master\` активен, \`FLOW_MAP.uslugi\` выключен в проверенной ревизии; активные регионы задаёт код. Наличие маршрута или генератора не подтверждает доступность опубликованного URL.
- **Проверки:** в \`main\` присутствуют 17 Django-тестов (по прежнему отчёту Codex: PASS; в этом подэтапе **NOT_RUN**): \`accounts/tests/test_auth.py\` (3), \`marketplace/tests/test_order_security.py\` (10), \`test_order_concurrency.py\` (1), \`test_catalog.py\` (3). Ещё 3 теста конфигураций существуют в \`stage-01-stabilization\`, итого 20 по прежнему отчёту. \`tests/test_business_logic.py\` — тест старого Telegram-потока, не Django; PSEO \`test.py\`, \`test_customer.py\`, \`test_master.py\` — отдельные скрипты, их успешность не подтверждена.

## 2. Матрица функций и решений

Определения: **CODE_PRESENT** — исходники/маршруты найдены без гарантии работоспособности; **REPORTED_PASS** — результат ранее сообщённых Codex-тестов, не повторная проверка; **UNVERIFIED** — поведения и/или данные не проверены. Решения \`REUSE / ADAPT / REWRITE / REJECT\` предварительные для планирования, не разрешение менять код.

| Функция | Источник / код | Состояние и проверки | Решение | Целевой этап |
| --- | --- | --- | --- | --- |
| Регистрация и вход | Django \`accounts/models.py\`, \`forms.py\`, \`views.py\` | CODE_PRESENT; 3 auth-теста, ранее REPORTED_PASS | REUSE; расширить подтверждение контактов | 03.2 |
| Клиент и мастер в одном аккаунте | Django \`User\`, \`ClientProfile\`, \`WorkerProfile\`, \`accounts/services.py\` | CODE_PRESENT; полный multi-role workflow UNVERIFIED | ADAPT, сохранить единую модель пользователей | 03.1, 03.3–03.4 |
| Категории и подкатегории | Django \`marketplace/models.py\`, \`seed_repair_categories.py\`; bot \`categories/initial_data.py\` | CODE_PRESENT; 3 теста каталога ранее REPORTED_PASS, сквозной импорт не проверен | ADAPT; объединить словари без дублей и потери slug | 02.1, 02.6 |
| Города и языковые имена | Django \`locations/models.py\`, \`seed_israel_cities.py\`; PSEO \`data/regions.py\` | CODE_PRESENT, \`City.localized_name\`; тесты RU/EN/HE ранее REPORTED_PASS; зоны обслуживания UNVERIFIED | ADAPT; не переносить старые ID вслепую | 02.2–02.4 |
| Создание заявки и право владения | Django \`marketplace/Order\`, \`views.py\`, \`services.py\`, \`0003_require_order_owner.py\` | CODE_PRESENT; тесты owner/anon и БД ранее REPORTED_PASS; реальные legacy-строки UNVERIFIED | REUSE + адаптация дальнейших правил заказа | 01.2, 04 |
| Приватность заявки/управление по ID | Django \`marketplace/views.py\`, \`services.py\`, HTML-шаблоны | CODE_PRESENT; ранее REPORTED_PASS для owner/assignee/staff, запрета чужих операций | REUSE; повторная проверка при появлении API/чата | 03.6, 04, 10 |
| Отклик и назначение одного мастера | Django \`Response\`, \`create_response\`, \`accept_response\` | CODE_PRESENT; тест конкурентного выбора на PostgreSQL ранее REPORTED_PASS, сейчас NOT_RUN | REUSE + ADAPT под полный жизненный цикл | 06 |
| Список доступных заявок мастеру | Django \`get_available_orders_for_worker\`, \`worker_dashboard_view\` | CODE_PRESENT; локальная сортировка, self-response и приватные поля тестировались; подбор целиком UNVERIFIED | ADAPT | 05–06 |
| Каталог и публичный профиль мастера | Django \`marketplace/views.py\`, \`worker_public_profile.html\`, \`category_detail.html\` | CODE_PRESENT; агрегация рейтинга и страницы ранее REPORTED_PASS; расширенный поиск UNVERIFIED | ADAPT | 03.4, 05 |
| Отзывы о завершённом заказе | Django \`Rating\`, \`rating_create_view\`, \`marketplace/admin.py\` | CODE_PRESENT; отдельные права доступа частично тестировались; антифрод/полный E2E UNVERIFIED | ADAPT | 07.4 |
| Уведомления | Django \`Notification\`, \`notifications/services.py\`, \`views.py\` | CODE_PRESENT, создание/прочтение; доставка email/push/anti-duplicate UNVERIFIED | ADAPT | 07.3 |
| Жалобы и блокировки | Django \`Complaint\`, \`moderation/services.py\`, \`views.py\` | CODE_PRESENT; \`block_user\` и \`is_blocked\` существуют, но полный запрет действий блокированному UNVERIFIED | ADAPT | 03.6, 07.5 |
| Сводная аналитика | Django \`analytics/GlobalStats\`, \`CategoryStats\`, \`services.py\` | CODE_PRESENT; наполнение и точность данных UNVERIFIED | ADAPT | 09 |
| SEO в Django | \`apps/seo/models.py\`, \`views.py\`, \`urls.py\` | Сквозной SEO-контент / миграция отсутствуют; текущие model/view — заглушки | REWRITE/ADAPT на основе PSEO, без второго runtime | 08 |
| Чат заказчика и мастера | Нет отдельного Django chat app / подтверждённого chat API в \`core/urls.py\` | NOT_IMPLEMENTED в проверенной web-кодовой базе | REWRITE (добавить общее серверное правило доступа) | 07.1–07.2 |
| Версионированный мобильный REST API | Django URL-конфигурация и приложения | Нет подтверждённого DRF/API v1; Flask PSEO \`/api/v1/stats/…\` — не мобильный API маркетплейса | REWRITE/ADAPT без дубля бизнес-логики | 10 |
| Регистрация и создание заявки в Telegram | \`executor/registration_exe.py\`, \`customer/create_an_order.py\` | CODE_PRESENT; независимые FSM + asyncpg, runtime не проверен | ADAPT правила/словарь, REJECT как новая runtime-реализация | 02–04 |
| Поиск мастеров, прямые предложения и отклики Telegram | \`customer/select_specialist.py\`, \`executor/new_orders.py\` | CODE_PRESENT, обработчики и SQL; безопасность и совместимость схем UNVERIFIED | ADAPT сценарий и правила, НЕ переносить SQL без сверки | 05–06 |
| Администрирование Telegram | \`admin_bot/admin_main.py\` | CODE_PRESENT; отдельный бот и операции блокировки; runtime UNVERIFIED | ADAPT функции в Django Admin/модерацию | 03.6, 07.5 |
| Историческая SQL-схема Telegram | \`db.py\`: users/clients/workers/categories/subcategories/orders/responses/ratings/stats и др. | CODE_PRESENT, отдельные таблицы через asyncpg; соответствие Django и реальные объемы UNVERIFIED | ADAPT через map/dry-run, REJECT прямую загрузку в целевую БД | 00.5, 01.2 |
| PSEO-хабы и статьи | Flask \`app.py\`, \`freez.py\`, \`templates/\` | CODE_PRESENT: \`/<flow>/<slug>/\`, region/category и article; доступность URL и индексация UNVERIFIED | ADAPT существующий контент/URL, без автоматических 301 | 00.4, 08 |
| PSEO словари и генерация | \`data/categories.py\`, \`data/regions.py\`, \`gemini*.py\`, \`index_site/generate_list.py\` | CODE_PRESENT; качество и происхождение текстов, готовность публичных страниц UNVERIFIED | ADAPT словари, REJECT автогенерацию как обязательный runtime | 02, 08 |
| Четыре целевых UI заказчика/мастера | Утверждённые внешние HTML-макеты; Django \`templates/\` | Требования зафиксированы, соответствие текущих шаблонов утверждённому UI UNVERIFIED | ADAPT backend contracts, не менять дизайн в 00.1 | 03–07 |

## 3. Карта зависимостей для следующего аудита

1. \`accounts.User\` → \`ClientProfile\` / \`WorkerProfile\` → \`marketplace.Order.client\` / \`Order.worker\` → \`Response\` / \`Rating\`, а также \`Notification\` и \`Complaint\`. Точные FK и действия при удалении сверить по миграциям в 01.2.
2. \`Category\` / \`Subcategory\` + \`City\` — общие справочники для заказов, профилей, поиска и будущего SEO. Source of truth в новой архитектуре — Django/PostgreSQL, PSEO/Telegram только доноры данных после проверки.
3. Старый \`db.py\` и Flask SQLite имеют **иные схемы** и идентификаторы. Нельзя читать их как миграции Django, напрямую присваивать FK или объединять таблицы без явной карты соответствий, dry-run и backup.
4. Существующий \`TECHNICAL_REPORT.md\` — исторический архитектурный отчёт, не доказательство текущего успешного выполнения. Статусы подтверждаются тестами и отдельными проверками.
5. \`stage-01-stabilization\` — отдельная рабочая ветка для этапа 01 (01.1); её не редактировать в ходе этапа 00. После объединения документационного PR #5 синхронизировать активные ветки с обновлённым \`main\` без force-push.

## 4. Неподтверждённые данные и блокирующие зависимости

- **00.2 — секреты:** в дереве приватного PSEO находятся \`.env\`, \`index_site/service_account.json\`; также SQLite \`.db\`. Проверены только **имена файлов**, не значения и не содержимое. Владельцу нужны проверка действительности, разрешённая ротация/удаление из будущего дерева, закрытый план обработки истории. Не раскрывать секреты в PR.
- **00.3 — backup/restore:** реальное расположение/состав/объём production PostgreSQL, SQLite и медиа не подтверждены; нет доказанного теста восстановления. Никакой backup не выполнен в 00.1.
- **00.4 — SEO URL:** требуется \`docs/SEO_URL_INVENTORY.csv\` из генератора, sitemap, фактических HTTP-ответов и (при наличии) GSC. Существующие Flask-маршруты не равны опубликованному списку.
- **00.5 — перенос:** требуется ADR и map полей/ID/состояний Django vs Telegram vs PSEO, dry-run и защита от дубликатов; прежняя аналитическая записка не заменяет новую схему миграции.
- **00.6 — диагностика:** нужен воспроизводимый baseline проверок \`manage.py check\`, isolated migrate, smoke, Docker/ограничения; полученные от Codex результаты 17/20 тестов не повторялись.
- **Риски:** отсутствие работающего чата, REST API и полноценного SEO в Django — предмет следующих этапов, а не ошибки, устраняемые в 00.1. Не запускать production/deploy/изменения DNS до соответствующего gate.

## 5. Критерии приёмки 00.1 и передача на проверку

- [x] Перечислены существующие приложения, старые модули и PSEO активы.
- [x] Для функций указан источник, степень подтверждения и решение \`REUSE/ADAPT/REWRITE/REJECT\`.
- [x] Связи и риски помечены, неизвестное явно \`UNVERIFIED\`.
- [x] Секреты и базы не открывались и не включались в документацию.
- [ ] Независимая выборочная сверка матрицы с текущим кодом/Codex и приёмка владельца; затем можно проставить \`DONE\` в \`ROADMAP.md\` без повторного большого аудита.

**Проверки 00.1:** \`STATIC_INSPECTION: PASS\` (структуры и выбранные исходники GitHub), \`Django tests: NOT_RUN\`, \`migrations: NOT_RUN\`, \`production: NOT_TOUCHED\`. Матрица не подтверждает наличие реальных данных или рабочий запуск сервисов.
