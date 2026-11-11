# ZemiPro — журнал подтверждённого прогресса

> Начальная редакция: 2026-11-05
> Источник статусов: docs/ROADMAP.md и docs/DEVELOPMENT_PLAN.md

## Историческое исходное состояние 2026-11-05

- Этапы: 0 из 13 подтверждены в новой программе.
- Подэтапы: 0 из 85 подтверждены.
- Этап 00 / подэтап 00.1: NOT_STARTED / UNVERIFIED.
- Существующий Django и Telegram-бот не считаются готовыми без аудита, тестов и приёмки.
- Этот файл создан вместе с базовым пакетом документации. Разработка этапов не запускалась.
- Для каждого подэтапа фиксировать: ID, статус, переиспользование, изменённые файлы, тесты (PASS/FAIL/SKIP/NOT_RUN), миграции, блокеры, commit/PR, дату и следующий разрешённый шаг.

Актуальный нормативный объём после решения владельца: **14 обязательных этапов 00–13 и 96 обязательных подэтапов**. Исторические числа выше сохранены только как исходная точка.

## Безопасность репозитория

- В начальном дереве main отслеживались корневой .env и настройки IDE .idea/.
- Предложено удалить их из текущего дерева через отдельный PR и добавить .gitignore; старая история Git этим не очищается.
- Любые реальные ключи из истории требуют проверки и ротации владельцем.
- Production, DNS, базы и внешние аккаунты этим документационным PR не затрагиваются.

## 2026-11-06 — этап 01, критические исправления Django backend

### 01.1 — конфигурация и production-безопасность

- **Статус:** `IN_PROGRESS / LOCALLY_VERIFIED`.
- **Сделано/переиспользовано:** сохранена единая Django-конфигурация; при `DEBUG=False` обязательны сильный `DJANGO_SECRET_KEY` и `DJANGO_ALLOWED_HOSTS`, автоматически включены HTTPS redirect, secure cookies и HSTS. Локальный `DEBUG=True` не изменён.
- **Файлы:** `zemipro_web/core/settings.py`, `zemipro_web/.env.example`.
- **Тесты:** PASS `manage.py check`; PASS `manage.py check --deploy` с синтетическими production-переменными.
- **Блокеры/риски:** полное разделение settings и lock/constraints остаётся в объёме этапа 01; реальные секреты и production не затронуты.

### 01.2 — обязательный владелец заявки и миграция

- **Статус:** `IN_PROGRESS / LOCALLY_VERIFIED`.
- **Сделано/переиспользовано:** анонимное создание закрыто; `Order.client` стал обязательным `PROTECT` FK. Миграция останавливается с явной ошибкой при наличии legacy-заявок без владельца, не удаляет и не переназначает данные автоматически.
- **Файлы/миграции:** `marketplace/models.py`, `marketplace/views.py`, `marketplace/services.py`, `marketplace/migrations/0003_require_order_owner.py`.
- **Тесты:** PASS миграции текущей изолированной dev-БД; PASS миграции чистой тестовой БД; PASS `makemigrations --check`; PASS `migrate --check`.
- **Блокеры/риски:** перед будущим production-выкатом необходимо отдельно сопоставить возможные legacy-заявки с владельцами; production-БД не затронута.

### 01.3 — права доступа и адресные тесты

- **Статус:** `IN_PROGRESS / LOCALLY_VERIFIED`.
- **Сделано/переиспользовано:** приватный адрес и контакт доступны только владельцу, назначенному исполнителю и staff; потенциальные исполнители видят безопасную карточку. Проверены owner checks операций accept/cancel/complete/review. Django API endpoints в текущем дереве отсутствуют; legacy Telegram handlers не изменялись.
- **Файлы:** `marketplace/tests/`, связанные views/templates.
- **Тесты:** PASS 11 Django tests — обязательная авторизация, DB constraint владельца, защита от IDOR, сокрытие адреса, права управления, рейтинги, страницы категории/города, RU/EN/HE и fallback.
- **Блокеры/риски:** CI остаётся отдельной незавершённой частью 01.3.

### 01.6 — каталог и blocker-ошибки

- **Статус:** `IN_PROGRESS / LOCALLY_VERIFIED`.
- **Сделано/переиспользовано:** рейтинг агрегируется через `WorkerProfile.user`; страницы категорий и городов больше не возвращают 500. Названия городов выбираются по текущему языку `ru/en/he` с fallback на русский. Сортировка заказов мастера стала детерминированной без `UNION`.
- **Файлы:** `locations/models.py`, `marketplace/views.py`, `marketplace/services.py`, шаблоны каталога и кабинетов.
- **Тесты:** PASS целевые страницы и локализация в общем наборе из 11 тестов.

**Ветка, commit, PR, merge:** `stage-01-backend-security`; базовый commit `e80ea6e`; PR [#2](https://github.com/maxim9362/zemiPro_site_django/pull/2); merge не выполнялся.

**Реальная БД/VPS/DNS/секреты:** не затронуты.

**Следующий разрешённый шаг:** устранение четырёх blocker-замечаний финального security-review в существующем PR #2.

## 2026-11-06 — исправления финального security-review PR #2

### Регистрация и авторизация

- **Статус:** `LOCALLY_VERIFIED`.
- **Сделано:** `RegistrationForm` явно привязана к кастомной `accounts.User`; проверены успешная регистрация с автоматическим входом, последующий login и отклонение невалидной регистрации.
- **Файлы:** `accounts/forms.py`, `accounts/views.py`, `accounts/tests/test_auth.py`.

### Приватность заявок и self-response

- **Статус:** `LOCALLY_VERIFIED`.
- **Сделано:** detail заказа требует входа. Свободное описание, адрес, имя и телефон не выводятся неназначенным исполнителям; безопасная карточка сохраняет категорию, город, бюджет и статус. Сырые подробности доступны владельцу, назначенному исполнителю и staff. Собственные заявки исключены из выдачи мастера; view и service запрещают отклик владельца.
- **Файлы:** `marketplace/views.py`, `marketplace/services.py`, связанные шаблоны и `test_order_security.py`.

### Конкурентный выбор исполнителя

- **Статус:** `LOCALLY_VERIFIED`.
- **Сделано:** `accept_response` блокирует строку `Order` через `select_for_update`, внутри транзакции повторно проверяет `NEW`, блокирует выбранный отклик и допускает только `PENDING`. Повторный конкурентный запрос не назначает второго исполнителя и не создаёт уведомления об успехе.
- **Файлы:** `marketplace/services.py`, `marketplace/views.py`, `test_order_concurrency.py`.

### Проверки и границы

- **Тесты:** PASS 17 адресных Django-тестов на PostgreSQL, включая два параллельных соединения; общие проверки выполняются перед отправкой ветки.
- **Оставлено по roadmap:** замечание review о политике `User.is_blocked` не входит в четыре blocker-исправления этой задачи и не изменялось.
- **Production/VPS/DNS/реальные базы/секреты:** не затронуты.
- **Ветка/PR:** существующие `stage-01-backend-security` и PR #2; новый PR и merge не создаются.

## 2026-11-07 — синхронизация требований о разделе знаний, PR #3

- **Область:** только документация; `REQ-KNOW-001–015` из `TECHNICAL_SPEC.md` v1.1.0 и согласование зависимых документов.
- **План:** добавлен необязательный этап 13 (`13.1–13.7`), всего 14 этапов / 92 подэтапа; этап начинается только после закрытого 09 и команды владельца, Q&A — после `GO` по пилоту статей.
- **Статус реализации:** `NOT_STARTED / DEFERRED`; никаких статусов `DONE` у этапа 13 и его подэтапов. Фактический прогресс этапов 00–12 не менялся.
- **Проверка:** документационная сверка требований, зависимостей, счётчиков и нумерации; Django-тесты/миграции — `NOT_RUN` (приложение не менялось).
- **Production/VPS/DNS/реальная БД/внешние публикации:** не затронуты.
- **Следующий шаг:** по согласованной дорожной карте; реализация знаний требует отдельного разрешения и отдельного итогового PR.

## 2026-11-10 — плановые функции рекомендаций и приглашений, v1.2.0

- **Область:** документация этапа 13, `REQ-KNOW-016–023`, подэтапы 13.8–13.11. Программа: 14 этапов / 96 подэтапов; исторические статусы 1.0–1.1 сохранены.
- **Функции:** личные рекомендации мастеров (вне заказов), добровольный Facebook-шеринг профиля, «Посоветуйте мастера» после проверки спроса, кнопка приглашения ещё не зарегистрированного мастера в ZemiPro.
- **Статус:** этап 13 — `NOT_STARTED / DEFERRED`; новые подэтапы не начаты. Facebook Login и расширенные Meta-интеграции в текущие требования не входят.
- **Проверки:** синхронизация документов и нумерации; Django-тесты/миграции `NOT_RUN`, поскольку приложение не менялось.
- **Production, рабочие БД, DNS, Facebook и платежи:** не затрагивались.

## 2026-11-10 — этап 00, подэтап 00.1: реестр реализаций

- **Статус:** `IN_PROGRESS / STATICALLY_INVENTORIED`. Этап 00 не завершён; 00.2–00.6 не запускались.
- **Сделано:** создан `docs/STAGE_00_IMPLEMENTATION_INVENTORY.md` с матрицей Django/Telegram/PSEO, решениями REUSE/ADAPT/REWRITE/REJECT, картой связей, источниками проверки, рисками и явными UNVERIFIED.
- **Проверки:** `STATIC_INSPECTION: PASS` (GitHub деревья/выбранные исходники и тесты); `Django tests: NOT_RUN`, `migrations: NOT_RUN`; прежние 17/20 тестов — только по отчётам Codex, не новая проверка.
- **Границы:** найденные по именам потенциально чувствительные PSEO-файлы не открывались; реальные базы, секреты, производственные службы, DNS не затрагивались. Ротация/backup/URL inventory/ADR/diagnostics остаются 00.2–00.6.
- **Ветка:** `stage-00-audit` от `main`; по одному коммиту на подэтап, один итоговый PR этапа после завершения. Изменения документов PR #5 пока не объединены в `main`.
- **Следующий шаг:** независимая выборочная сверка матрицы; после приёмки 00.1 — переход к 00.2 только по команде владельца.

## 2026-11-10 — решение владельца: Telegram больше не нужен

- **Решение:** Django + PostgreSQL — единственный целевой backend; Telegram/FSM/aiogram и связанная интеграция исключены из будущей платформы. Telegram-код временно оставлен как исторический/безопасностный объект, без запуска или удаления.
- **Документ:** `docs/DECISIONS/ADR-0001-DJANGO-ONLY-NO-TELEGRAM.md`, обновление матрицы 00.1. Соответствующие требования в основных документах синхронизировать отдельно, после урегулирования PR #5; до этого приоритет — новое прямое решение владельца.
- **Production, Telegram, БД, секреты:** не затронуты.

## 2026-11-10 — подэтап 00.2: метаданные секретов и план защиты

- **Статус:** `BLOCKED / OWNER_ACTION_REQUIRED`; `DONE` не подтверждён. Создан `docs/STAGE_00_SECRET_RISK_REGISTER.md`.
- **Проверено:** имена и размеры отслеживаемых файлов в Git деревьях Django/Telegram и приватного PSEO; `.gitignore` основного репозитория. PSEO содержит `.env`, JSON сервисной учётной записи и два SQLite файла; наличие/действительность ключей и чувствительного содержимого `UNVERIFIED`.
- **Защита:** расширен `.gitignore` текущей ветки против случайного попадания новых .db, ключей и env; это не исключает уже отслеживаемые файлы из PSEO и не очищает историю.
- **Не выполнялось:** чтение секретов/БД, secret scanning содержимого/истории, ротация или отзыв ключей, действия во внешних сервисах, backup, production, миграции, Docker и Django-тесты. Статусы `NOT_RUN` / `NOT_TOUCHED`.
- **Для приёмки:** после разрешённой проверки владельцем — ротация действующих секретов, безопасный вывод PSEO файлов из Git с подтверждённым сохранением данных, локальная санитизированная проверка. Промежуточный Codex Cloud не используем; итоговая проверка по окончании этапа 00.
- **Следующий плановый подэтап:** 00.3 (резервные копии/восстановление). К реальной БД не обращаться без разрешения; до устранения риска 00.2 production запрещён.

## 2026-11-10 — отказ от старого PSEO и решение по URL

- **Решение владельца:** развиваем новый Django-сайт на существующей кодовой базе, старые Flask/PSEO код, тексты, шаблоны, генераторы и SQLite не переносим. Telegram также исключён ранее.
- **Единственный условно сохраняемый актив:** реестр старых публичных URL/slug для проверки видимости и точечных 301 после готовности Django, без массовых редиректов на главную.
- **Документ:** `docs/DECISIONS/ADR-0002-REBUILD-WITH-URL-ONLY.md`; обновлена интерпретация инвентаризации 00.1 и границы 00.4 в дорожной карте.
- **Проверка:** живой сайт и примеры опубликованных URL найдены; количество проиндексированных URL, трафик и GSC-метрики `UNVERIFIED`. `sitemap.xml` и `robots.txt` не удалось подтвердить через веб-инструмент.
- **Реальные действия:** Django tests `NOT_RUN`, миграции `NOT_RUN`, production/DNS/PSEO репозиторий `NOT_TOUCHED`, PR/merge `NOT_CREATED`.

## 2026-11-10 — подэтап 00.3: план резервирования и восстановления

- **Статус:** `IN_PROGRESS / RESTORE_NOT_VERIFIED` — критерий подтверждённого backup/restore пока не выполнен.
- **Сделано:** подготовлены `docs/STAGE_00_BACKUP_INVENTORY.md` (Django PostgreSQL, Django media, миграции, отдельный архив Telegram и PSEO), `docs/STAGE_00_BACKUP_RESTORE.md` (безопасный порядок и критерии проверки), `scripts/stage00_pg_snapshot.py` (synthetic-only local pg_dump/pg_restore с контролем пустой базы и SHA-256).
- **Разграничение:** активным источником для будущего ZemiPro остаётся Django/PostgreSQL; старый Telegram/PSEO не мигрируется. Их Git-объекты не подменяют проверенные резервные копии.
- **Проверки:** статическая подготовка документов/исходников `PREPARED`; выполнение PostgreSQL CLI, Django tests, SQL backup/restore, проверка медиа `NOT_RUN`. Промежуточный Codex Cloud не используем; итоговое тестирование по завершении этапа 00.
- **Безопасность:** скрипт запрещает удалённый хост, реальные имена БД, очистку существующей схемы и сохранение дампа в репозитории. Любой реальный backup/restore только с отдельным разрешением и изолированной средой.
- **Production/VPS/DNS/реальные базы/секреты/PSEO:** `NOT_TOUCHED`. 00.2 всё ещё блокирован.
- **Следующий:** 00.4 — только сохранение и инвентаризация ранее опубликованных URL, без переноса PSEO-кода или контента.

## 2026-11-10 — 00.4: первичная инвентаризация публичных URL

- **Статус:** `IN_PROGRESS / GSC_AND_SITEMAP_UNVERIFIED`, не `DONE`.
- **Сделано:** в `docs/SEO_URL_INVENTORY.csv` сохранён выборочный набор из 21 уникального URL (11 — содержимое открыто в публичном веб-инструменте, 10 — обнаружены в публичной поисковой выдаче); описаны источники и ограничения в `docs/STAGE_00_URL_AUDIT.md`.
- **Не проверено:** полный sitemap/robots (веб-инструмент вернул ошибку), GSC клики/показы/индекс, фактические HTTP-коды, canonical и целевые Django-URL. Не утверждать исчерпывающую индексацию/публикацию.
- **Решение:** только REVIEW адресов; никакого переноса Flask/PSEO, автоматических редиректов или массовой генерации URL. Новые страницы и маршруты будут утверждены отдельно.
- **Проверки:** уникальность/домен/статусы CSV — `PASS`; Django tests, миграции, production, DNS/Cloudflare, GSC и редиректы — `NOT_RUN / NOT_TOUCHED`.
- **Следующий подэтап:** 00.5 — архитектурная карта Django-only и стратегия URL-перехода без миграции Telegram/PSEO. Codex Cloud использовать только после завершения этапа 00.

## 2026-11-10 — подэтап 00.5: архитектурная карта и план перехода

- **Статус:** `IN_PROGRESS / PLAN_PREPARED`, не `DONE`.
- **Решение:** один Django backend `zemipro_web/`, один PostgreSQL на окружение, один `accounts.User`, текущие ORM/миграции переиспользуются. Legacy Telegram и Flask/PSEO не импортировать; единственный переносимый ориентир — публичные URL после GSC/HTTP и точной карты переходов.
- **Артефакты:** `docs/DECISIONS/ADR-0003-DJANGO-ONLY-SINGLE-DATABASE.md`, `docs/STAGE_00_ARCHITECTURE_MIGRATION_PLAN.md`, `docs/STAGE_00_SOURCE_TARGET_MATRIX.csv`.
- **Выявлено:** `User.role` пока одно значение (мультирольность отдельный 03.1), `Order.client` обязательный и `0003_require_order_owner` блокирует legacy `client=NULL`, `apps.seo` ещё заглушка. Старые региональные slugs нельзя бездумно трактовать как новые города.
- **План dry-run:** только изолированная Django PostgreSQL с проверенным backup; counts/migrations/constraints и проверка URL-списка на GSC/HTTP/redirect loops. **Ни одна работающая БД не импортировалась, никаких 301 не создавалось.**
- **Проверки:** `STATIC_CODE_REVIEW: PASS` (модели/URLs/migration/settings), `DOC_MATRIX: PREPARED`; `SQL/DRY_RUN/DJANGO_TESTS: NOT_RUN`; независимая итоговая проверка после 00.6, Codex Cloud пока не используется.
- **Production/VPS/DNS/реальные базы/секреты:** `NOT_TOUCHED`. Сохранены нерешённые гейты 00.2–00.4.
- **Следующий подэтап:** 00.6 — диагностический baseline; 00.1–00.5 закрывать только по критериям, не по числу коммитов.

## 2026-11-10 — подэтап 00.6: диагностический baseline

- **Статус:** `IN_PROGRESS / STATIC_BASELINE_PREPARED`, **не DONE**. Все подэтапы 00.1–00.6 имеют артефакты, но остаются незакрытые приёмочные критерии; 00.2 заблокирован действиями по секретам, 00.3 — отсутствием доказанного restore, 00.4 — полнотой URL/GSC.
- **Реализация:** `scripts/stage00_static_diagnostics.py` (read-only Python AST, проверка метаданных, CSV/миграции, JSON-статусы без доступа к данным), `scripts/tests/test_stage00_static_diagnostics.py` (синтетические fixtures), `docs/STAGE_00_DIAGNOSTIC_BASELINE.md` (подтверждённые и отсутствующие проверки, риски, порядок полной приёмки).
- **Выполненные локальные проверки:** синтетический unittest 6/6 `PASS`, `py_compile` утилиты `PASS`; проверены нужные файлы через GitHub. **Полный static baseline по checkout самого GitHub не выполнялся** в локальном runner.
- **Среда:** runner Python 3.13.5; Django, Docker и инструменты PostgreSQL отсутствуют. Это **не** статус окружения Codex/пользователя/VPS.
- **Не запускалось:** `manage.py check`, `check --deploy`, `makemigrations --check`, миграции и Django-тесты, восстановление PostgreSQL, Docker/HTTP smoke, скан секретов/истории и GSC. Нельзя называть результаты `PASS` без выполнения.
- **Риски и рамки этапа 01:** сохранены `0003_require_order_owner` с возможными анонимными старыми строками, разделённые settings 01.1 в другой ветке, отсутствие CI/staging readiness, модели ролей и пустой Django SEO. Полный список: `docs/STAGE_00_DIAGNOSTIC_BASELINE.md`.
- **Безопасность:** secrets, production, DNS, Cloudflare, реальные DB, Telegram/PSEO и PR `NOT_TOUCHED`.
- **Следующий шаг:** подтвердить блокеры 00.2–00.4, затем провести **одну итоговую** проверку этапа 00 в изолированном окружении, как поручил владелец. Финальный PR/merge не выполнять до достижения гейта и разрешения.

## 2026-11-10 — 00.2: углублённая проверка и кодовая защита

- **Новый риск:** в публичном `admin_bot/admin_main.py` обнаружен жёсткий SOCKS5 proxy URI с учётными данными. Значения не выводились и не проверялись на действительность.
- **Изменение кода:** литерал заменён чтением `ADMIN_BOT_PROXY_URL` из окружения; если прокси не задан, используется обычная сессия. Не производится запуск Telegram и не изменяется production. Старые секреты сохраняются в истории Git до отдельного согласованного решения.
- **PSEO-история:** проверены метаданные шести предыдущих деревьев; `.env`, service_account JSON и старые SQLite встречаются в нескольких ревизиях. Не открывались значения секретов и содержимое баз.
- **Безопасный инструмент:** `scripts/stage00_secret_audit.py` + `scripts/tests/test_stage00_secret_audit.py`; 6/6 локальных синтетических тестов PASS, результат полноценного сканирования действующего клона и всех исторических blob — NOT_RUN.
- **Блокер:** `00.2 = BLOCKED / OWNER_ROTATION_REQUIRED`. Нужны отзыв/смена прокси-пароля, проверка PSEO-токенов/сервисной учётки и последующее закрытие исторического риска. Никаких значений ключей в документации.
- **GitHub:** работа только в `stage-00-audit`, никаких операций с PSEO/основным `main`, PR, DNS, базами и Cloudflare.

## 2026-11-10 — подготовка удаления чувствительных файлов PSEO

- В `maxim9362/zemipro_site_pseo` создана ветка `security/remove-tracked-credentials-and-dbs`, черновой PR #1: https://github.com/maxim9362/zemipro_site_pseo/pull/1.
- Четыре файла с потенциальными секретами/данными исключены из HEAD этой ветки; добавлены .gitignore и notice. PR не объединён, PSEO main и история не изменены.
- Действующие ключи не отозваны, история не очищена, старый сайт/базы не тронуты. `00.2` сохраняет `BLOCKED / OWNER_ROTATION_REQUIRED`; SOCKS5 исправлен только в `stage-00-audit`.
- PR основного этапа 00 не создавался, `main` не менялся; итоговая Codex-проверка отложена по решению владельца.

## 2026-11-10 — удаление устаревшего Telegram runtime из Git-ветки

- По прямому решению владельца удалены 28 файлов Telegram-бота, админ-бота, старого Docker/Compose, зависимостей и конфигурации из `stage-00-audit`. Действующий Django в `zemipro_web/` сохранён без изменений.
- Создан `docs/STAGE_00_LEGACY_REMOVAL.md`, обновлены ADR-0001 и реестр рисков. Поле `accounts.User.telegram_id` пока оставлено для безопасной будущей миграции схемы.
- Удаление из HEAD ветки не удаляет историю публичного Git и не отзывает пароли у сервисов. `main`/production/DNS/реальные базы/секреты не изменялись; диагностика Django `NOT_RUN`.
- В приватном PSEO отдельный draft PR #1 на удаление файлов с ключами и SQLite. Не объединять без оценки влияния на текущий сайт.

## 2026-11-10 — окончательная GitHub-подготовка этапа 00 (без запуска Django)

- Подтверждено: бывший приватный PSEO-репозиторий удалён владельцем (GitHub API 404), основной Django-репозиторий существует. Прежний PR #1 PSEO — историческая запись.
- В `stage-00-audit` сохраняются Django-модули и миграции; удалено 28 файлов legacy Telegram runtime. `main`/история Git не изменялись.
- Устранены противоречия о гостевых заказах в `docs/ROADMAP.md`, `docs/DEVELOPMENT_PLAN.md`, `AGENTS.md`: для создания/управления заказом нужна авторизация, `Order.client` обязателен. Гостям разрешён только публичный просмотр.
- Актуализированы риск-реестр 00.2, инвентарь источников 00.3, документ вывода Telegram. Создан `docs/STAGE_00_FINAL_ACCEPTANCE.md` для итоговой проверки.
- Кодовые зависимости Django (`core/urls.py`, `core/settings.py`, `apps/accounts`, `apps/marketplace`, `apps/notifications`, seed-команды) просмотрены через GitHub; статически новые прямые ссылки на удалённые root Telegram модули в проверенных файлах не выявлены. Полный suite и runtime ещё не пройдены.
- **Не проверено**: отзыв внешних ключей, полная история секретов Git, backup/restore, GSC, Django tests/migrations и Docker. Предварительные синтетические тесты вспомогательных скриптов — не доказательство работоспособности Django.
- Открытый PR #5 содержит v1.3/обязательность этапа 13; его нужно согласовать с v1.2 до финального merge. PR этапа 00 не создан, production/DNS/БД не затронуты. **Этап 00: IN_PROGRESS.**

## 2026-11-11 — независимый аудит и доступное завершение этапа 00

- **Ветка/base:** `stage-00-audit`, независимая проверка начата с `94526454ff0b1102e038f5a74ab5aeb3d3be67f9`.
- **00.1:** `DONE / INDEPENDENTLY_VERIFIED`. Подтверждён единственный Django runtime; Telegram/PSEO отсутствуют как runtime и источники импорта.
- **00.2:** `BLOCKED / OWNER_ROTATION_REQUIRED`. Текущее дерево безопасным сканером не выявило отслеживаемых secret-файлов; historical credential и старые Google/Gemini/Telegram credentials требуют подтверждённого отзыва владельцем. Значения не читались и не публиковались.
- **00.3:** `READY_FOR_OWNER_ACTION / SYNTHETIC_RESTORE_PASS`. На PostgreSQL 17.11 совпали 27 миграций, 8 категорий, 56 подкатегорий и 25 городов до/после restore. Доступная конфигурация не доказывает наличие рабочей Django DB/media с ценными данными; владелец должен подтвердить их наличие. Legacy базы восстанавливать не требуется.
- **00.4:** `READY_FOR_OWNER_ACTION / HTTP_GSC_UNVERIFIED`. CSV: 21 строка, 21 уникальный URL, корректная структура, без придуманных target URL. Публичный GET заблокирован Cloud CONNECT proxy `403`; HTTP/canonical/sitemap/GSC не проверены и остаются задачей этапа 08.
- **00.5:** `DONE / DOCUMENTED`. Нормативные документы синхронизированы: auth-only orders, Django/PostgreSQL, запрет Telegram/PSEO/SQLite import, 14/96 обязательны, этап 13 обязателен с отдельным `GO` на публикацию Q&A.
- **00.6:** `READY_FOR_OWNER_ACTION / CORE_CHECKS_PASS`. PASS: 17/17 Django tests, 12/12 tests инструментов, system/deploy checks, миграции, `pip check`, Git checks и synthetic restore. Docker image `NOT_RUN`: TLS CA Cloud proxy прервал `pip`; это не подтверждённый дефект проекта.
- **Дефекты:** HIGH/production риски персональных данных, `is_staff`, публичного blocked profile, рейтингов, зависимостей и deployment перечислены в `docs/STAGE_00_FINAL_ACCEPTANCE.md` и назначены этапам 01–07. Функциональный код в этой итерации не изменялся.
- **PR #5:** его требования v1.3 сохранены вручную вместе с результатами этапа 00. PR #5 не объединялся и не изменялся; безопасный порядок согласования записан в final acceptance.
- **Production/внешние системы:** `NOT_TOUCHED`. Этап 00 остаётся `BLOCKED / OWNER_ACTION_REQUIRED`; итоговый PR автоматически не создаётся.

## 2026-11-11 — фиксация этапа 00 и переход к процессу GPT → Codex Cloud

- **Итоговый статус этапа 00:** `IMPLEMENTED / CORE_VERIFIED / FOLLOW_UP_REQUIRED`. Основная разработка и независимая проверка завершены; это не означает `DONE` всех 00.1–00.6.
- **Подтверждено:** 00.1 завершён; 00.3 synthetic PostgreSQL backup/restore `PASS`; 00.5 согласован; 00.6 core checks выполнены; Django tests 17/17 и tools tests 12/12 `PASS`. Новая PostgreSQL создаётся с нуля; Telegram/PSEO базы и данные не импортируются.
- **00.2:** `LEGACY_REMOVED / PROVIDER_REVOCATION_DEFERRED_BY_OWNER`. Старые credentials не используются; владелец отзовёт их позднее. Факт отзыва не подтверждён; обязательный security gate до production сохранён. History rewrite и force-push не выполняются.
- **00.4:** `DEFERRED / RETURN_BEFORE_STAGE_08`. Перед этапом 08 обязательно проверить все 21 URL, HTTP, sitemap, canonical, GSC, индексацию/трафик и зафиксировать KEEP/301/404/410 в CSV. Сейчас редиректы, сайт, DNS и Cloudflare не изменяются.
- **Новый процесс:** GPT в ChatGPT реализует все подэтапы в одной ветке этапа, выполняет адресные проверки и обновляет документацию. После завершения всего этапа Codex Cloud проводит независимый review и этапные проверки; ошибки исправляются в той же ветке и проверяются повторно.
- **Переход к 01:** следующий этап — стабилизация Django и инфраструктуры через GPT. Проверено наличие `stage-01-backend-security` и `stage-01-stabilization`; PR #2 уже входит в `main`, `stage-01-stabilization` не объединена. До выбора ветки сохранить существующую реализацию. Новая ветка и код 01 в этой задаче не создавались.
- **GitHub:** один этап = одна ветка = один итоговый PR; PR этапа 00 и merge автоматически не выполнялись; PR #5 не изменялся.

## 2026-11-11 — решение владельца о новой PostgreSQL и старых ключах

- Владелец подтвердил: Django/PostgreSQL запускаем **с новой чистой базой**, старые Telegram/PSEO SQLite/PostgreSQL данные и media не импортируем. Тестовая PostgreSQL backup/restore ранее прошла (27 миграций, 8 категорий, 56 подкатегорий, 25 городов). Не удалять автоматически существующие серверные тома/БД; production backup и rollback готовить перед запуском.
- Старые ключи Gemini, Google Service Account, Telegram и SOCKS5 в новой архитектуре **не используются** и не будут переноситься. Новые необходимые ключи создадим по необходимости, только в environment/secret storage, не в Git.
- Отзыв старых ключей у провайдеров владелец планирует выполнить позднее самостоятельно. Он **не выполнен и не подтверждён**; 00.2 остаётся `BLOCKED / PROVIDER_REVOCATION_DEFERRED_BY_OWNER`. Публичная Git history с прежним SOCKS5 credential — отдельный риск до отзыва; force-push/history rewrite не выполнялись.
- Решение о позднем отзыве **не является** доказательством безопасности и не разрешает production. Разрешены только дальнейшие независимые проверки, разработка и подготовка изменений без использования старых секретов.
- Изменена только документация `stage-00-audit`; реальных ключей, секретов, Django-кода, production и серверных данных не трогали. Один этап/ветка/итоговый PR сохраняется.

## 2026-11-11 — 01.1: разделение Django-конфигурации (GPT, рабочая ветка)

- **Статус:** `IN_PROGRESS / IMPLEMENTED / RUNTIME_NOT_RUN`; до подтверждения тестов и воспроизводимого чистого запуска не `DONE`.
- **Ветка и основание:** `stage-01-development`, исходный `main` `6b119043e330`; код адаптирован выборочно из `stage-01-stabilization`, старые ветки не изменены. Коммит: запись в этом же коммите 01.1. Один этап — одна ветка — один итоговый PR.
- **Реализовано:** `core.config` с профилями `development/test/staging/production`; строгая проверка продакшен-секретов, хостов и DB, обязательный HTTPS, secure cookies, консервативная HSTS без preload; отдельная тестовая PostgreSQL с локальным host-guard; `manage.py test` выбирает профиль test. Сохранены единая Django ORM и существующая бизнес-логика.
- **Зависимости:** Python 3.12.14 (reference), Django 5.2.19 LTS; runtime requirements с exact pins и Windows markers, Gunicorn для Linux.
- **Документы/безопасность:** новые `README.md`, `DJANGO_SETUP.md`, `.env.example`, `.dockerignore`; Git-исключения секретов сохранены. Compose/staging остаются 01.4 и не заявляются проверенными.
- **Тесты:** `PASS` — статическое сравнение веток, код/requirements/документация проверены на уровне GitHub; `NOT_RUN` — новый Django suite и `manage.py check --deploy`, PostgreSQL migrate, `pip check`, Windows/Linux clean install и Docker build (в рабочем контейнере отсутствуют Django и сетевой доступ к пакетам). 7 конфигурационных тестов добавлены, выполнение ожидается в изолированной среде.
- **Миграции:** нет; схемы и реальные данные не изменялись.
- **Риски:** поддерживаемый Django 5.2 ещё требует полноценного regression run; проверка Python package pins/совместимости и реальный clean start не завершены; до production старые credentials должны быть отозваны отдельно владельцем.
- **Далее:** после подтверждения доступных тестов и решения по DoD 01.1 переход к 01.2 только по команде владельца. Production, VPS, Cloudflare, DNS и действующие БД `NOT_TOUCHED`.

## 2026-11-11 — 01.2: PostgreSQL constraints and migration rehearsal (GPT)

- **Статус:** `IN_PROGRESS / IMPLEMENTED / RUNTIME_NOT_RUN`, не `DONE`: миграции и тесты написаны, но полноценный PostgreSQL/Django runtime недоступен в этой среде.
- **Ветка:** `stage-01-development`; исходный предыдущий этапный коммит `9c34753e058d9953d65478138678e18c7a4f1977`. Один этап — одна ветка — один итоговый PR; этот подэтап не создаёт PR.
- **Проверено:** `accounts`, `marketplace`, `locations`, `moderation`, `notifications`, `analytics`: сохранены исходные миграции, модель пользователя, связи `PROTECT/SET_NULL/CASCADE`, уникальность категорий/городов/откликов/подкатегорий, существующие индексы. Правила каскада и политики удаления личных данных не менялись без продуктового решения.
- **Реализовано:** модельные и миграционные PostgreSQL CHECK constraints для `Order.status`, `Response.status`, `Complaint.status`, с предварительной блокировкой несовместимых legacy значений и без записи/удаления данных; добавлены адресные тесты графа миграций, статусных ограничений, уникальности и защиты владельца. Файлы: `marketplace/models.py`, `marketplace/migrations/0004_status_constraints.py`, `moderation/models.py`, `moderation/migrations/0002_status_constraint.py`, `marketplace/tests/test_schema_constraints.py`, `docs/STAGE_01_MIGRATION_REHEARSAL.md`.
- **Решение по legacy:** новые тестовые PostgreSQL создаются с нуля. Старые Telegram/PSEO/SQLite базы/данные не импортируются; для текущего Django — только сохранение существующей истории миграций и synthetic backup/restore.
- **Проверки:** `PASS` — GitHub-статическая проверка моделей, имён/зависимостей миграций и сохранения исходных файлов; `NOT_RUN` — Django migration loader, `makemigrations --check`, `migrate`, PostgreSQL CHECK enforcement, synthetic restore + row counts, Django tests (зависимости и изолированный PostgreSQL не доступны).
- **Миграции:** 2 новых, без удаления старых и без правок production. Вставка данных/вызовы внешних сервисов отсутствуют.
- **Риски:** 01.1 Django 5.2 dependencies ещё требуют регрессионных тестов; статусные ограничения не применены в БД; настройка тестовой БД и миграционная репетиция должны быть выполнены в изолированной среде. Действующие базы, DNS, Cloudflare, VPS, секреты: `NOT_TOUCHED`.
- **Следующий шаг:** после команды владельца — 01.3, сохраняя оба предыдущих подэтапа `IN_PROGRESS` до выполненных критериев и независимого этапного Codex review.

## 2026-11-11 — 01.3: базовые Django тесты, фабрики и CI через GPT

- **Статус:** `IN_PROGRESS / IMPLEMENTED / CI_VERIFICATION_PENDING`. Это не `DONE` без реального успешного CI и проверки blocking required status.
- **Рабочая ветка:** `stage-01-development` на базе предыдущего 01.2 коммита `6ce67ca0b62013f0d56a4864fa2cfb307e9d1179`; один этап, одна ветка и один итоговый PR. `main` не изменяется.
- **Реализовано:** `.github/workflows/django-ci.yml` запускает Ubuntu/Python 3.12, отдельную PostgreSQL 17, pinned dependencies, `pip check`, Ruff и `compileall`, Django check, `makemigrations --check`, clean migrate, `migrate --check`, полный набор Django TestCase и coverage критичного сервисного слоя, а также синтетический `check --deploy` без сетевого production доступа.
- **Переиспользовано:** исходные 17 Django тестов этапа 00, 7 конфигурационных тестов из 01.1, 8 тестов схемы PostgreSQL из 01.2. Добавлены 6 тестов сервисного happy path/отрицательных сценариев и фабрики синтетических users/categories/cities/orders; новые тесты используют данные только своего тестового PostgreSQL.
- **Файлы:** `.github/workflows/django-ci.yml`, `zemipro_web/requirements-ci.txt`, `zemipro_web/pyproject.toml`, `zemipro_web/.coveragerc`, `zemipro_web/apps/marketplace/tests/factories.py`, `zemipro_web/apps/marketplace/tests/test_service_workflow.py`, `docs/STAGE_01_CI_ACCEPTANCE.md` и записи ROADMAP/PROGRESS.
- **Порог покрытия:** 60% только для `apps.marketplace.services`; не заявлено глобальное покрытие Django.
- **Тесты:** `PASS` — подготовительный просмотр текущих файлов GitHub и синтаксиса конфигураций статически; GitHub Actions, Django tests, покрытие и настоящий PostgreSQL `NOT_RUN` до появления результата запусков после push. Контейнер ChatGPT без Django/PostgreSQL и без сетевого доступа к PyPI.
- **Приёмка/блокер:** branch ruleset для main должен требовать GitHub Actions check `django-postgresql`; наличие YAML в Git не гарантирует запрет merge. Проверить перед PR и записать доказательство.
- **Миграции/production:** миграции в 01.3 не добавлены; staging/VPS/DNS/prod/секреты/реальные БД не затронуты.
- **Следующий подэтап:** 01.4 только по команде владельца, не объявляя 01.1–01.3 `DONE` до соответствующих проверок.

## 2026-11-11 — 01.4: Docker Compose и staging (GPT)

- **Статус:** `IN_PROGRESS / IMPLEMENTED / DEPLOYMENT_NOT_RUN` — требования описаны и код добавлен, но Docker build и реальное staging HTTPS ещё не подтверждены.
- **Ветка:** `stage-01-development`, исходный commit `1f2b6313467fe9c375bd797dc23ce98f0a833319`. Один этап/одна ветка/один итоговый PR, без merge.
- **Что сделано:** обновлён non-root Python 3.12 Dockerfile; безопасный `entrypoint.sh` запускает Django migrations только для явных `development/staging`, `collectstatic` на persistent static volume, Gunicorn. Development Compose: PostgreSQL 17, healthcheck DB/web, volumes для PostgreSQL/static/media, порты только loopback. Отдельный staging Compose: физически независимые БД/тома/сеть, нет опубликованного DB/web порта, ограничение памяти и 1 worker, Caddy TLS proxy для заранее согласованного домена, запрет прямого доступа `/media/*`; `.env.staging.example` без реальных секретов.
- **Проверки:** добавлены 5 статических Django-тестов безопасности конфигурации и CI `docker compose config --quiet` с синтетическими переменными. Фактические Docker build/run, PostgreSQL persistence, HTTPS smoke и тесты Django пока `NOT_RUN` / staging `BLOCKED` до изолированного окружения и согласования.
- **Файлы:** `zemipro_web/Dockerfile.django`, `docker-compose.django.yml`, `docker-compose.staging.yml`, `Caddyfile.staging`, `docker/entrypoint.sh`, `.env.staging.example`, `core/tests/test_container_config.py`, CI workflow, README, `docs/STAGE_01_DOCKER_STAGING.md`, ROADMAP, PROGRESS.
- **Риски и rollback:** старые volumes не удаляются/не подключаются, новые секреты не использованы; полноценный rollback зависит от 01.5 backup/restore. Окружение с Gunicorn TCP health проверяет лишь процесс, а не функциональную готовность Django/DB. До пробного HTTPS нужен отдельный staging host, DNS и разрешение владельца.
- **Production, VPS, DNS/Cloudflare, реальные БД и медиа:** `NOT_TOUCHED`. Дальше 01.5 только после команды владельца.

## 2026-11-11 — 01.5: safe logs, health, staging backup/restore runbook

- **Статус:** `IN_PROGRESS / IMPLEMENTED / RUNTIME_AND_RESTORE_NOT_RUN`. Нет подтверждённого расписания/бэкапа/restore/доставленного мониторингового алерта; `DONE` не заявляется.
- **Ветка:** `stage-01-development`, исходный HEAD после 01.4 `80b29bd7903e9ca7ad2d574aa318df23c1ed5889`. Один этап — одна ветка, один итоговый PR после 01.6, `main` не изменяется.
- **Реализация:** `core.observability.SafeJsonFormatter` пишет только UTC timestamp/level/component/allowlisted event/status_code и отбрасывает сообщения, аргументы, request, exceptions, tracebacks; базовые Django логгеры направлены в безопасный console JSON handler. `GET /health/live/` — HTTP liveness без БД, `GET /health/ready/` — `SELECT 1` и 503 при `DatabaseError`, без деталей DB, с no-store. PostgreSQL connect_timeout=3.
- **Staging backup:** отдельный opt-in maintenance контейнер PostgreSQL 17 с жёстко проверенными PGHOST/PGDATABASE/PGUSER, приватным `staging_backups` volume, atomic pg_dump custom archive + pg_restore list + SHA-256. Архив не включает медиа; для медиа нужен отдельный защищённый backup. Без автоматического удаления имеющихся архивов и без воздействия на production.
- **Расписание и ошибки:** подготовлены неактивный шаблон cron 03:15 UTC, проверка readiness каждые 5 минут (скрипт exit=1 + syslog ALERТ), runbook внешней зашифрованной копии, synthetic restore через защищённый stage00 tool, сравнений counts и ручного rollback. Ни хост, ни cron, ни канал алертов не настроены.
- **Тесты/CI:** добавлены конфигурационные тесты formatter, health HTTP/DB mock, backup/monitor guard; CI проверяет shell syntax и `docker compose --profile maintenance config --quiet`. Runtime Django/PostgreSQL/Docker/curl monitoring/restore **NOT_RUN** в доступном окружении; только статический review и сопоставление конфигураций `PASS`. Версии и уязвимости внешних сервисов повторно не аудировались.
- **Риски:** следует отдельно подтвердить отсутствие PII в Gunicorn/Caddy/host логах, проверку реального 503 и доставку алерта; backup на volume того же хоста не disaster recovery. Staging/production, домен, secrets, старая Django/Telegram/PSEO DB, платежи и медиа `NOT_TOUCHED`.
- **Далее:** 01.6 — только по команде; финальные независимые проверки и один итоговый PR после всех шести подэтапов.

## 2026-11-11 — 01.6: SQL performance, safe errors, mobile fallback and throttling

- **Status:** `IN_PROGRESS / IMPLEMENTED / BENCHMARK_NOT_RUN`, not `DONE`. Code now exists for 01.1–01.6, but none of the runtime acceptance gates can be asserted solely from these commits.
- **Branch:** `stage-01-development`, parent commit `84ce08e1dd62227210fe31478d3e620f106051e1`. One stage branch, one final PR after independent verification; main not touched.
- **SQL:** city worker skills prefetched, category ordering stabilized by PK, worker public profile skills prefetched, worker dashboard orders joined to city/category, client dashboard response counts aggregated instead of N per-order DB queries.
- **Cache/error:** dynamic HTML no-store middleware and independent generic 404/500 templates that do not echo request data/tracebacks.
- **Basic throttle:** 12 login POST / 5 min, 6 registration POST / 15 min per client IP, HMAC cache keys, generic 429/503; staging Caddy overwrites X-Real-IP and a dedicated env flag enables trust. Default LocMemCache is per process, **not** an adequate distributed production safeguard.
- **CSS:** minimal responsive fallback for existing Django pages at 320–480px; the approved four separate frontend HTML source files are not changed.
- **Tests:** synthetic SQL scaling, 404/500, cache headers, POST limit and source-IP trust behavior added to existing CI test suite. Current environment lacks Django/PostgreSQL, so test execution and real device/latency/memory figures remain `NOT_RUN`.
- **Data/infra:** no schema migrations, no external services or libraries, no Docker starts, no VPS/DNS/Cloudflare/production or real data changes. See `docs/STAGE_01_PERFORMANCE_BASELINE.md`.
- **Stage 01 acceptance:** requires independent Codex Cloud review, full verified GitHub CI with PostgreSQL/migrations/tests, branch protection, isolated Docker HTTPS staging, backup/restore + alert drill, performance/mobile checks and production-grade abuse-control decision. Do not claim Stage 01 DONE or merge until verified and authorized.

## 2026-11-11 — Stage 01 independent Codex review: ZP-01-001–006 remediation

- **Reviewed SHA:** `3b06a647bca3cdba1c70aca6c2e02a23d89f552b`; Codex verdict `CHANGES REQUIRED`. Independent synthetic PostgreSQL: Django `69/69 PASS` twice, `pip check` PASS, `manage.py check` PASS, `makemigrations --check` PASS, `29` migrations PASS, schema restore and backup/verification PASS, coverage `89.5%` of `apps.marketplace.services`. GitHub CI `FAIL` from 16 F401 + 2 F405; these are **pre-remediation** results, not post-change passes.
- **ZP-01-001 HIGH:** remove 16 confirmed unused imports across Django source and historic no-op stubs; make `DATABASES` explicit in test settings so Ruff F405 does not trigger. Do not turn lint rules off.
- **ZP-01-002 MEDIUM:** staging/production reject `DJANGO_SECURE_HSTS_SECONDS <= 0`, add invalid-value test.
- **ZP-01-003 HIGH:** replace per-process LocMemCache throttle with atomic PostgreSQL `INSERT ... ON CONFLICT ... RETURNING` HMAC window counters, new `accounts.0003_sensitive_post_counter` schema, expiring records and operator-scheduled pruning, concurrency test across independent DB connections. No Redis, queue or paid service.
- **ZP-01-004 HIGH:** public catalogue and direct worker URL require both `user.is_active=True` and `is_blocked=False`, new tests assert 404 and no public profile listing.
- **ZP-01-005 MEDIUM:** `NULLS LAST` descending rating with stable PK tie-break and rating test.
- **ZP-01-006 LOW:** rewrite obsolete Compose description in `DJANGO_SETUP.md`.
- **Verification status:** remediation prepared in the same existing stage branch, but new Django/PostgreSQL suite, migrations, Ruff and GitHub Actions require **fresh** execution. Do not infer PASS from Codex's pre-fix 69/69. No PR, merge, production DB, VPS, DNS, Cloudflare or secret changes.
- **Remaining gates:** real staging HTTPS, off-host backup+monitor alert, branch protection, representative p95/RSS, mobile HE/RTL and authorized deployment decisions. All 01 substages remain `IN_PROGRESS` until acceptance.

## 2026-11-11 — Stage 01: повторная проверка Codex после исправлений / подготовка итогового PR

- **Проверенный Codex коммит:** `c8591a553b59412c56c85ab2b2b584b4f5718719` в `stage-01-development`. Результаты приведены по итоговому отчёту Codex, переданному владельцем; это **не новый локальный прогон GPT**.
- **Итог ZP-01-001–006:** все 6 замечаний закрыты; новых ошибок по ним Codex не обнаружил. Ruff **PASS**, GitHub Actions **PASS**, миграция `accounts.0003_sensitive_post_counter` **PASS**, атомарность общего PostgreSQL rate limiter при параллельных запросах **PASS**.
- **Тесты:** полный Django набор **75/75 PASS**, два независимых прогона по отчёту Codex (обычный и coverage); покрытие `apps.marketplace.services` **89,5%**. Это **не** покрытие всего проекта. До исправлений были `69/69` и красный CI; эти записи исторические и не отражают текущий код.
- **Объём:** код 01.1–01.6 реализован и успешно прошёл повторную проверку исправлений. Этап **не объявляется `DONE`**, поскольку инфраструктурные и продуктовые гейты ниже ещё не выполнены.
- **Подтверждено ранее по первому отчёту Codex на синтетической среде:** dev Docker/Compose runtime, новая PostgreSQL и миграции, базовые DB health, staging backup container и synthetic restore; реальные production/staging настройки и пользовательские данные не использовались.
- **Осталось не подтверждено / `BLOCKED`:** отдельный staging host/domain/DNS с действительным HTTPS; off-host зашифрованное хранение backup и доставка мониторингового alert; административная проверка required GitHub branch protection для `main`; реальные p50/p95/RSS и мобильная визуальная проверка 320px, RU/EN/HE RTL; native Docker build без особенностей облачного CA окружения (Codex проверял сборку с audit CA mount, не production build).
- **Политика PR:** допускается **один итоговый Draft PR** из `stage-01-development` в `main` для review; незакрытые гейты перечисляются в описании. **Не объединять PR, не активировать staging/prod и не менять DNS/Cloudflare/VPS** без отдельного решения владельца. После изменения документации новый commit требует собственного GitHub CI run; PASS за `c8591a553b59412c56c85ab2b2b584b4f5718719` не автоматически распространяется на новый SHA.

## 2026-11-11 — изолированная staging smoke-проверка CI, без изменения реальной инфраструктуры

- **Основание:** владелец запросил довести инфраструктурные гейты Stage 01 до приёмки, сохраняя действующий сайт/VPS/DNS/Cloudflare.
- **Новая проверка:** `.github/workflows/stage01-staging-smoke.yml` запускает на disposable GitHub runner `zemipro_web/docker/ci-staging-smoke.sh` с синтетическими секретами, `localhost` и локальными портами. Docker staging build, loopback HTTPS с внутренним Caddy CA (не доверенный реальный TLS), HSTS, Django readiness, CSS/media, PostgreSQL persistence после restart, backup checksum и 100 HTTP timing samples.
- **При добавлении:** `WORKFLOW_NOT_YET_VERIFIED`. Статус обновить только после реального GitHub Actions run. Результаты p50/p95 локального CI не приравнивать к реальному staging benchmark.
- **В уже проверенном GitHub run** `43026841102` / Django CI / SHA `8ed9c3797fd5a9016bfece64b1333a3f4d81b76f` статус `success` (отдельно подтверждён инструментом GitHub).
- **Не затронуты:** существующие VPS, DNS, Cloudflare, production и настоящие данные/секреты. В PR #7 нет разрешения на merge.
- **Остаётся зависимость от владельца:** назвать и разрешить отдельный staging host/domain, параметры DNS и защищённое off-host место хранения; провести внешний alert и real TLS, browser/mobile RTL, performance с реалистичными данными, проверить GitHub branch protection (админ-интерфейс).

## 2026-11-11 — GitHub Actions synthetic staging smoke verified (PR #7)

- **Tested SHA:** `c2e159f96254ffd0005b790050a273da7f11bfdf`.
- **Django CI run #9:** [43028406270](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43028406270) — **SUCCESS**.
- **Isolated staging smoke run #1:** [43028406371](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43028406371) — **SUCCESS** (GitHub hosted runner, `localhost` with Caddy *internal* CA, synthetic credentials). Actual output confirms HTTPS readiness, static 200/media 404, HTTP redirect/HSTS, migration persistence across DB restart, `pg_dump` + checksum and `pg_restore --list`.
- **Timing baseline:** 100 sequential requests to empty `/categories/`: p50 **15.5 ms**, p95 **16.6 ms**, loopback-only. This **does not meet** representative 100/1000-workers or real staging p95/RSS/mobile gates.
- **Main blocker:** no owner-designated separate staging host/domain and no authority to change real Cloudflare/DNS/VPS; off-host backup + delivered alert, branch protection administration and 320px/HE/RTL visual checks remain `BLOCKED/NOT_RUN`.
- **PR:** [Draft #7](https://github.com/maxim9362/zemiPro_site_django/pull/7) remains **OPEN / NOT MERGED**. Stage 01 remains `IN_PROGRESS`; passing disposable CI does not satisfy the publicly trusted HTTPS or off-host disaster recovery conditions.

## 2026-11-11 — локальный Codex на Windows: найденные дефекты и исправления в PR #7

- **Основание:** пользователь предоставил резюме локального `STAGE_01_LOCAL_VERIFICATION_REPORT_RU.md`; полный файл остаётся локально на ноутбуке и не предоставлен в GitHub/чат. Итог Codex: `CHANGES_REQUIRED`; рабочие локальные Development (`127.0.0.1:8000`) и Staging (`localhost:18443`), PostgreSQL 17.11/30 миграций, 75/75 Django tests, Ruff PASS, 89.5% coverage `apps.marketplace.services`, synthetic backup/checksum/restore PASS, health failures, 2 Gunicorn workers + shared rate limiter, 10/100/1000 entities и 320–1280px проверены на старом HEAD `8365d7c`.
- **LOCAL-01-HIGH:** `CRLF` Windows checkout портит shell scripts (`entrypoint`/backup). Добавлен корневой `.gitattributes` с `*.sh text eol=lf` и static regression. Уже существующий Windows checkout может требовать безопасного переполучения tracked scripts после `git pull --ff-only`; не очищать чужие изменения.
- **LOCAL-02-MEDIUM:** Gunicorn пытается использовать отсутствующий домашний каталог `/home/django`. Docker образ создаёт `/home/django` с владельцем `django`, `HOME` и правами `0700`.
- **LOCAL-03-MEDIUM:** dashboard заказчика рендерил 1000 заказов (~1.02 MiB). Введены **четыре независимые ограниченные страницы** по статусам (по 10 записей каждая), с сохранением позиции других секций и агрегированными счётчиками откликов. Добавлены тесты объёма, приватности, пагинации и счётчиков.
- **LOCAL-04 / Stage 02:** базовый `<html lang="ru">` заменён динамическими `lang/dir` (he→rtl; ru/en→ltr) и тестом. Это только корректная разметка активного locale; **полная локализация RU/EN/HE и пригодный RTL-дизайн остаются в 02.3**, не помечать `DONE`.
- **Проверка новых исправлений:** `NOT_RUN / CI_PENDING` на момент публикации изменений. Результат 75/75 относится к предыдущему SHA. После push проверить Ruff, PostgreSQL migrations, новые и полные Django tests, Docker Windows CRLF, Gunicorn HOME и HTML size на 1000 записей через локальный Codex.
- **Внешние гейты:** `OFF_HOST_BACKUP_NOT_VERIFIED`, `ALERT_DELIVERY_NOT_VERIFIED`, `BRANCH_PROTECTION_BLOCKED`, publicly trusted staging TLS `NOT_RUN` — сознательно не названы выполненными. Действующий VPS, DNS, Cloudflare, production, чужие ноутбучные контейнеры не трогались. PR #7 остаётся **Draft / NOT_MERGED**.
