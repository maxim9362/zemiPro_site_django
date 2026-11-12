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
- **Проверка новых исправлений:** GitHub [Django CI #43058354569](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43058354569) **PASS: 81/81 Django tests, Ruff, PostgreSQL migrations и coverage 89,5% только для `apps.marketplace.services`**. GitHub [isolated staging smoke #43058354612](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43058354612) **PASS: localhost TLS, backup SHA-256, DB restart/persistence**; CI baseline empty catalog p50 12.0 ms / p95 13.1 ms (не результат реальной нагрузки). **PENDING на Windows-ноутбуке:** повторное получение LF после существующего checkout, пересборка Docker/Gunicorn HOME и замер кабинета на 1000 заявках. Результат 75/75 был на предыдущем SHA.
- **Внешние гейты:** `OFF_HOST_BACKUP_NOT_VERIFIED`, `ALERT_DELIVERY_NOT_VERIFIED`, `BRANCH_PROTECTION_BLOCKED`, publicly trusted staging TLS `NOT_RUN` — сознательно не названы выполненными. Действующий VPS, DNS, Cloudflare, production, чужие ноутбучные контейнеры не трогались. PR #7 остаётся **Draft / NOT_MERGED**.

## 2026-11-11 — Windows Codex repeat review: six PASS, one Docker-only false negative

- **Reviewed SHA:** `71094208a68350d4c10d63f7a2a0601e106ebb9d` on `stage-01-development`; source checkout and PR #7 were not changed by Codex. Summary supplied by owner, not an independently collected full report file.
- **Confirmed PASS:** clean fast-forward from `8365d7c`; all four tracked shell scripts `i/lf w/lf attr/text eol=lf`; local Development and Staging rebuild/health on isolated Docker with retained PostgreSQL volumes; Gunicorn `/home/django` writable for UID 10001 and zero permission errors; 1000 synthetic orders survive restart; paginated client dashboard limits each of four statuses to 10 orders/page and excludes another client's private address, HTML **39,661 bytes** (previously ~1.02 MiB); 50-request local direct p95 **28.92 ms**, HTTPS p50 **70.58 ms** / p95 **101.79 ms**, zero HTTP errors; dynamic RU/EN/HE `lang/dir` PASS; Windows venv **81/81 Django PASS**, Ruff/migrations/backup/health PASS.
- **One reproducible false negative (Docker 80/81):** `core.tests.test_container_config.ContainerConfigurationTests.test_shell_scripts_use_lf_and_django_has_writable_home` reads `self.root.parent / '.gitattributes'`, which exists in repository checkout but is intentionally outside Docker image context `/app`; Docker image must **not** copy `.git` or parent workspace. Fix: check root `.gitattributes` **only when it exists**. Mandatory checks of actual LF in scripts and Dockerfile Gunicorn HOME remain unconditional.
- **After fix:** new tests and staging smoke `NOT_YET_VERIFIED` until latest GitHub run and new Windows container test. No code/DB production modifications, no branch merge.
- **External gates still OPEN:** `OFF_HOST_BACKUP_NOT_VERIFIED`, `ALERT_DELIVERY_NOT_VERIFIED`, `BRANCH_PROTECTION_BLOCKED`, publicly trusted staging TLS `NOT_RUN`. Stage 02 covers full translations and Hebrew RTL UX.

## 2026-11-11 — Stage 01 локально принят; разрешён merge PR #7 и переход к Stage 02

- **Решение владельца:** после проверки положительных результатов разрешены завершение этапного PR #7 в `main` и переход к разработке Stage 02 в этом чате. Владелец не приобретает VPS сейчас; отдельный публичный staging/production host не настроен.
- **Состояние на момент решения:** `stage-01-development` at `455236a5f782ef6c491f746d20a4cebd90c9c1e8`; GitHub Django CI [#43079414032](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43079414032) **SUCCESS**; isolated staging Docker smoke [#43079414024](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43079414024) **SUCCESS**, включая специфический тест `test_shell_scripts_use_lf_and_django_has_writable_home` `Ran 1 test / OK` внутри образа.
- **Локальная база по отчёту Codex:** Windows с чистым git, LF и Docker dev/staging, Gunicorn HOME, PostgreSQL 17.11 / 30 migrations, synthetic backup/checksum/restore, 1000 заявок с HTML 39,661 B, p95 HTTPS 101.79 ms на 50 запросах, privacy, 81/81 Django suite. Повтор полного Windows suite после *самой последней* CI-only правки не предоставлен; не приписывать ему PASS.
- **Приёмочный статус:** `LOCAL_VERIFIED / ACCEPTED_FOR_STAGE_02`. Это подтверждение пригодности для продолжения локальной разработки, **не** `DONE` всей внешней/production инфраструктуры.
- **Обязательства при будущей подготовке к релизу:** off-host зашифрованный backup и восстановление, реальная доставка alert, branch protection для `main`, публичный staging HTTPS/TLS, реальные p50/p95/RSS на сервере и визуальный HE RTL. Всё `DEFERRED / NOT_VERIFIED`, а не `PASS`.
- **Ограничения:** Merge только кода, никакого автоматического deploy, миграций на VPS, DNS/Cloudflare, изменения prod БД или создания настоящего staging без отдельного разрешения.

## 2026-11-11 — Stage 01 merged; Stage 02 branch kickoff

- **Stage 01:** PR [#7](https://github.com/maxim9362/zemiPro_site_django/pull/7) **MERGED** into `main`, merge SHA `7202ce1f8f1a6697d9bc6db878666ee719de7017`. Before merge, GitHub Django CI #43080172545 and staging smoke #43080172542 **PASS** on `e5cfbf2`. Stage 01 remains `LOCAL_VERIFIED / ACCEPTED_FOR_STAGE_02`, with external production gates not yet verified and deliberately deferred.
- **Stage 02:** created branch `stage-02-catalog-localization` **directly from merged main** at `7202ce1`. One branch for all stage 02 substages, one final PR at stage completion; do not open a PR for every substage. Work continues in this ChatGPT development chat; isolated Windows Codex runs tests/reviews.
- **Sequence:** 02.1 catalog `Category/Subcategory`, verified RU/EN/HE fields and idempotent synthetic seed; 02.2 city/service geography; 02.3 translations & Hebrew RTL; 02.4 localized public catalogue URLs; 02.5 editable service questions; 02.6 import/i18n regression tests and integration review.
- **Constraints:** no import from Telegram, PSEO or legacy DB; no lost IDs, slugs or existing orders; no arbitrary modifications to the four approved frontend HTML designs; keep public SEO pages accessible; register to create orders; preserve privacy; no production/DNS/VPS/Cloudflare or real-data migrations. Changes are incremental within the single stage branch, with targeted tests and docs per substage.
- **02.1 state:** `NOT_IMPLEMENTED` (branch and plan prepared only). Need inspect normative catalog TЗ and existing seed/model before proposing code changes; do not assume a category list from incomplete context.

## 2026-11-11 — Stage 02.1: Django catalog baseline implemented, independent QA pending

- **Branch:** `stage-02-catalog-localization`, stage rule one branch / one final PR.
- **Schema:** additive `marketplace.0005_catalog_hierarchy`; 12-section `ServiceSection`; `Category.section` nullable for legacy preservation; localized names/descriptions/SEO and work modes at all three levels. Existing FK relations and IDs untouched.
- **Seed:** explicit `seed_service_catalog`, pure manifest, 12 sections, 19 categories (including unchanged 8 pre-existing repair slugs), 88 services (including unchanged 56); --plan/--check, atomic get_or_create, fill-only blanks, fail-closed reparent and duplicate detection. Existing repair-only command stops mutating global seed data.
- **UI/Admin:** section-grouped catalog with existing unassigned categories as fallback, localized label properties, inactive sections excluded from public catalog/order form, Django Admin editing. The four approved frontend HTML mockups are not changed.
- **Coverage added:** idempotency, no changes to existing order/category PKs, Admin edit preservation, duplicate and section-conflict guards, three-language fallback, public visibility, legacy repair command repeatability.
- **Status:** `IMPLEMENTED / CI_PENDING / LOCAL_CODEX_NOT_RUN`. No local Docker/PG tests run by ChatGPT; GitHub Actions to validate after push. New service taxonomy and Hebrew/English editorial quality require owner review before production; full RTL Stage 02.3.
- **No actions:** no production/DNS/VPS/Cloudflare/real data migration, no PR, no merge.

## 2026-11-11 — Stage 02.1 independent GitHub QA verified, code accepted

- **One shared Draft PR:** [#8](https://github.com/maxim9362/zemiPro_site_django/pull/8), same `stage-02-catalog-localization` branch for all 02.1–02.6; no merge.
- **Verified code SHA:** `91e665791ea832c64a1dd239865c7f3091eb1800`.
- **GitHub Django CI:** [#43086273717](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43086273717) **SUCCESS**; Ruff/compileall, Django checks and `makemigrations --check --dry-run` PASS, isolated PostgreSQL `marketplace.0005_catalog_hierarchy` migration PASS; Django **92/92 tests PASS** including 11 new catalog tests. Service-only coverage `apps.marketplace.services` **89.5%**, not project-wide.
- **Independent live seed execution on *ephemeral CI PostgreSQL*, never production:** `seed_service_catalog --plan` → 12/19/88; first seed created (12 sections, 19 categories, 88 services), second seed created (0,0,0); `--check` PASS twice; explicit SQL/model count assertion `STAGE_02_1_CATALOG_SEED_PASS (12,19,88)`.
- **Docker staging smoke:** [#43086273848](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43086273848) **SUCCESS**, isolated localhost Caddy/PostgreSQL/backup checks.
- **Acceptance:** `02.1 CODE_DONE / CI_VERIFIED`. Technical scope complete on synthetic CI database. `EDITORIAL_REVIEW_PENDING` for the 11 newly proposed categories and translated catalog wording (native Hebrew proofread before public release). No real-user database import, no deployment, no PR merge.
- **Next:** 02.2 city/geographic coverage and service zones; reuse stage branch and Draft PR #8. Test suite may expand; full stage 02 acceptance only after 02.6.

## 2026-11-11 — Stage 02.2 geography and service zones implemented (CI pending)

- **Branch/PR:** `stage-02-catalog-localization` / single [Draft #8](https://github.com/maxim9362/zemiPro_site_django/pull/8). No merge or production changes.
- **Additive schema:** `locations.0002_district_city_alias` creates 6 canonical statistical District keys + CityAlias, adds nullable City.district. `accounts.0004_worker_service_zones` creates `WorkerProfile.service_cities` M2M and `offers_remote=False`. No data migration or rewrite of City PK/slugs, user profiles, orders or worker skills.
- **Curated seed:** existing Django 25 cities preserved as original stable slugs; English/Hebrew names added, 6 districts and 4 non-shadowing alternate slug aliases. `seed_israel_cities --plan/--check` read-only, default atomic fill-missing-only, preservers admin edits/is_active; fails closed on re-parenting or alias collisions. **This is a curated 25-city pilot subset, NOT Israel's complete locality register.**
- **Matching:** service zones are explicit selectable City PKs; if an existing profile has no explicit zones, the existing home City acts as sole fallback. Remote opt-in matches only categories that explicitly support `online`/`both`. Public city/category searches and new-order feed use those zones; unrelated cities and onsite-only remote jobs are excluded. Private order access rules are unchanged.
- **Forms/Admin:** worker form controls cities + remote flag with validation; public profile shows service locations (not contacts); City/District/Alias editing in admin, localized names with RU fallback.
- **Coverage written:** 13 targeted tests for seed idempotency, existing IDs/admin edits, atomic conflict, alias collision, translations, legacy fallback, multi-city search, remote compatibility, form tampering and geo-specific job feed. **Not yet independently executed**, no claim of PASS.
- **Source reference:** Israel CBS [2022 census](https://census.cbs.gov.il/en) and [2023 localities dataset](https://data.gov.il/he/datasets/lamas/localities-in-israel/d47a54ff-87f0-44b3-b33a-f284c0c38e5a). Native Hebrew name review and nationally complete locality import remain open before public full coverage.
- **Next gate:** GitHub Django CI migrations/Ruff/13 tests and repeated seeded isolated PG counts `6/25/4`; isolated Docker smoke; document results before `CODE_VERIFIED`.

## 2026-11-11 — Stage 02.2 GitHub QA PASS; technical geography accepted

- **Verified code SHA:** `51bc4525fcfbf3dfec9f1edd8c3e12cb0022f58a`, shared [Draft PR #8](https://github.com/maxim9362/zemiPro_site_django/pull/8).
- **Django CI:** [#43090165800](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43090165800) **SUCCESS**: Ruff, Django checks, `makemigrations --check --dry-run`, PostgreSQL `locations.0002_district_city_alias` + `accounts.0004_worker_service_zones` applied cleanly, **106/106 tests PASS**; target-only `apps.marketplace.services` coverage **94.0%** (not entire project).
- **Isolated PostgreSQL geo seed:** plan 6 districts / 25 cities / 4 aliases, first seed created `6/25/4`, second created `0/0/0`, two `--check` runs PASS, model counts assertion `STAGE_02_2_GEO_SEED_PASS (6, 25, 4)`. Preserves city FK identity and prior admin edits in tests. Catalog seed 02.1 round-trip also PASS.
- **Staging smoke:** [#43090165776](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43090165776) **SUCCESS** (disposable runner, not public HTTPS).
- **Alias collision hardening:** canonical City.slug and CityAlias.slug cross-table conflicts rejected by admin form validation and seed guards; test added. No production input or site changes.
- **Status:** `02.2 CODE_DONE / CI_VERIFIED / NATIONAL_COVERAGE_PENDING`. Technical service-zone and remote search functionality verified. 25 cities are an explicit pilot subset, **not** a claim of complete Israeli locality coverage; need official complete registry and editorial RU/EN/HE translations, plus full UI localization in 02.3.
- **Next:** 02.3 three-language interface and mobile Hebrew RTL, within same stage branch / one Draft PR. No merge or deploy.

## 2026-11-11 — Stage 02.3 Django i18n/RTL implementation, CI pending

- **Draft PR #8**, `stage-02-catalog-localization`; single stage branch unchanged. `main`, VPS, production, DNS, existing orders and original 4 approved frontend mockups untouched.
- **Language layer:** existing `LocaleMiddleware` + `LOCALE_PATHS`, Django `set_language` via CSRF-protected POST/cookie and current path/query `next`; do not introduce `/ru/` prefixes until 02.4. Page language/dir is set server-side.
- **Translation catalogs:** Django RU source strings in main templates, compiled `locale/en,he/LC_MESSAGES/django.mo` and corresponding editable `.po`; form labels/choices/validation and notification templates use active language at render time. User-supplied text remains in original language, with `dir=auto`; no automatic translation of personal chat/requests.
- **RTL CSS:** logical margins/padding, neutral phone/email/budget bidi, responsive 390/768 width baseline; **static CSS checks only**, not actual screenshots or device/browser measurements. Approved 4 front-end mockups remain untouched.
- **Safety:** category dependent select uses localized public JSON endpoint and DOM `new Option` rather than untrusted HTML; order prices stored with canonical legacy fallback unchanged; notification event translations do not rewrite stored notification rows.
- **Tests:** 10 targeted trilingual regression tests added (home/catalog/cities/registration, safe switch redirect, forms validation and localized choices, API JSON, user data invariance, system notification, static RTL selectors).
- **Status:** `IMPLEMENTED / CI_PENDING / MOBILE_VISUAL_PENDING / HEBREW_EDITORIAL_PENDING`. Do not call 02.3 DONE until GitHub Actions PASS and mobile screenshot/content gates resolved or accepted for later 02.6.


- **Post-implementation static review 2026-11-11:** 20 main Django templates audited for unlocalized Russian UI literals: only the language selector's proper name `Русский` remains. Editable EN/HE `.po` and compiled binary `.mo` catalog contents are aligned (249 messages in each language). New automated regression checks PO/MO binary parity with `gettext.GNUTranslations` (10 targeted i18n tests in total). **GitHub Actions still QUEUED; tests have not executed on the current SHA**. Last checked head `9e35c3c2d5bca09071f67adc3bf6412740580ea0`. CI and Android/mobile visual RTL remain non-verified.

## 2026-11-12 — Stage 02.4 add-only localized public catalog routes (QA pending)

- **Same Draft PR #8**, branch `stage-02-catalog-localization`; no merge/deploy.
- Added `catalog_i18n` routes under Django `i18n_patterns` for sections, categories, subcategories, cities, lists (`ru/en/he`); existing unprefixed routes and privileged endpoints untouched.
- One stable model PK + slug across all languages. For service detail, category slug is included because subcategory slug is category-scoped.
- Additive templates and catalog links keep their language; language switch uses Django `set_language` to translate the current prefixed path and retain query string.
- New prefixed routes only: absolute `canonical`, reciprocal `hreflang`, `noindex,follow` by default. Explicit config flag remains off and thin pages remain noindex; production SEO/PSEO URL mappings are not changed.
- Prefixed known CityAlias → exact canonical city 301, unknown/inactive returns 404. Unprefixed legacy aliases keep their old 404 behavior; no guessed redirects.
- Tests written: 9 targeted test methods, covering 6 × 3 route matrix, same object identity, SEO/canonical, 404/301, query preservation, default index guard and private data exclusion. **Not executed** until GitHub Actions complete.
- **02.3 QA still pending:** GitHub runners for that commit did not execute (last seen `queued`); 02.4 does not inherit its PASS.
- **Status**: `02.4 IMPLEMENTED / CI_PENDING / MOBILE_VISUAL_PENDING`. Real domain/Cloudflare unchanged. Next stage after QA: 02.5.
- **Legacy 404 safeguard:** `LegacySafeLocaleMiddleware` prevents Django's automatic unprefixed-404 to prefixed-path redirect, preserving unknown legacy/PSEO paths. Regression checks verify old unknown category/city URLs still return 404 even for Hebrew Accept-Language.
- **CI findings (initial SHA 3d96a536):** Stage 02.3 localized tests **10/10 PASS**; Stage 02.4 targeted set **FAILED** (12 errors from test-only `resolve()` active-language mismatch, 1 redirect failure from `set_language` source locale, 1 legacy-404 failure from stock locale middleware); initial Docker staging smoke **SUCCESS**. Fixed within same branch: source-language-aware wrapper around Django `set_language`, 404-safe locale subclass, and route test using `translation.override(language)`. Await corrected HEAD CI; do not claim 02.4 PASS from failed earlier run.

## 2026-11-12 — Stage 02.4 fully verified in isolated GitHub CI

- **Verified code SHA:** `8d7427d4641c82283861ad5ea9fdc0fc1952e3b5`, Draft PR #8.
- [Django CI #43155367524](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43155367524) **SUCCESS**: 02.3 `10/10 PASS`, 02.4 `9/9 PASS`, full Django `125/125 PASS`, Ruff PASS, `makemigrations --check` PASS, PostgreSQL migrations PASS, catalog/geography seed round-trips PASS, targeted service coverage `94.0%`.
- [Ephemeral Docker staging smoke #43155367578](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43155367578) **SUCCESS**, synthetic infrastructure only.
- 02.4 fixes: restore original unprefixed 404, ensure `resolve()` tests run under selected language, wrap Django's `set_language` with validated source-language activation for no-cookie visits to `/he/...`.
- **02.4:** `CODE_DONE / CI_VERIFIED / INDEXING_DISABLED_BY_DEFAULT`. **02.3:** code CI-verified, still `MOBILE_VISUAL_PENDING / HEBREW_EDITORIAL_PENDING`. No PSEO redirects, sitemap/robots, production-domain changes, deployment, merge or user data migration.
- **Next:** 02.5 configurable service questions in same branch/PR, after recording this verification. Full 02 gate remains pending 02.5/02.6 and outstanding reviews.

## 2026-11-12 — Stage 02.5 configurable questionnaires implemented, independent QA pending

- Shared `stage-02-catalog-localization` / Draft PR #8, no merge/deploy.
- Additive migration `marketplace.0006_versioned_questionnaires`: ServiceQuestionnaire editable JSON draft per Subcategory, QuestionnaireVersion published immutable snapshot, OrderQuestionnaireAnswer private per-order versioned answer snapshot. Existing Order rows/PK/FKs remain untouched.
- Django Admin explicitly publishes new versions through `publish_questionnaire` under `select_for_update` and atomic transaction. Re-publishing unchanged draft is idempotent; direct admin modification/deletion of published versions and order snapshots disabled.
- Validation: up to 20 questions, six types (text/single/multiple/number/date/boolean), RU/EN/HE labels, stable value IDs and bounded options, one-level earlier single/boolean dependency, client cannot select unpublished/unknown choices or save a stale version.
- Authenticated order creation stores Order+answers in same DB transaction; existing orders with no questionnaire remain valid. Only owner/authorized designated worker sees answers via existing `can_view_private_order_details`. Public API returns only published questions and allowed option identifiers; dynamic client widgets do not use `innerHTML`.
- Optional operator-invoked `seed_demo_questionnaires` for plumbing, math tutoring, landing pages, event photography; `--plan`, `--check`, `--publish`, no production auto-seed or overwriting administrator drafts. Four drafted demonstrations are provisional content.
- Added 15 targeted tests: invalid schemas, idempotent revisions, immutable old versions/answers, tamper resistance, conditional questions, multi-language API, privacy, legacy order behavior and demo seed re-run. EN/HE gettext catalogs updated to 257 entries.
- `02.5 IMPLEMENTED / QA_PENDING` until GitHub CI Django/migrations/seed/full suite and Docker smoke succeed. Native Hebrew editorial review and mobile RTL visual checks remain for Stage 02.6. No Docker/production credentials changed.

## 2026-11-12 — Stage 02.5 technical acceptance on GitHub Actions

- **Code SHA:** `22297226d781a43f3279386f9bdec2ed0aaf374d`, same Draft PR #8.
- [Django CI #43156737078](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43156737078) **SUCCESS**: migration `marketplace.0006_versioned_questionnaires`, Ruff, `makemigrations --check`, 15/15 targeted questionnaire tests, 10/10 i18n, 9/9 localized URLs, **140/140 complete Django suite**, target service-layer coverage 94.0%.
- Isolated CI PG seed: `seed_demo_questionnaires --plan`, first `--publish` = 4 drafts + 4 versions, `--check` PASS, second `--publish` = 0 new drafts and 0 new versions, model counts `(4,4)` asserted. The regular catalog 12/19/88 and geography 6/25/4 repeated checks also PASS.
- [Docker staging smoke #43156737097](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43156737097) **SUCCESS** on disposable GitHub runner; not public staging deployment.
- **02.5 `CODE_DONE / CI_VERIFIED`.** Technical versioned questionnaires accepted. Sample wording/HE translations remain editorial-pending and real mobile browser/RTL screenshots remain Stage 02.6 gates. No real contacts/order data read or altered; no production/domain/VPS changes; PR stays Draft.
- **Next:** 02.6 integrated Stage 02 verification, including official national locality and Hebrew editorial completeness decisions, with separate Codex Cloud final review.

## 2026-11-12 — Stage 02.6 integration QA implementation

- **Branch/PR:** stage-02-catalog-localization, existing Draft PR #8. No new branch/PR and no merge.
- **Implemented:** Django integration coverage for all three seed manifests, stable catalog and city IDs/foreign keys, synthetic historic order/answer snapshot, editor overrides, collision rejection, privacy, route/menu/form and language-switch behavior in RU/EN/HE.
- **Browser smoke:** separate headless Chrome emulator on GitHub-hosted runner checks 320/360/375/390/768 pixel viewports for catalog/cities/authenticated order form, rtl/ltr HTML and CSS, horizontal overflow, phone field direction; screenshots retained for manual review. This is not a real Android or iPhone test.
- **Historical status at the initial implementation commit (before CI):** tests were pending; superseded by 2026-11-12 results below. Independent Code Review of the original SHA produced `CHANGES_REQUIRED` (ZP-02-001), now addressed in a later code commit.
- **Remaining gates:** independent visual review of screenshots and native Hebrew editorial validation of new 11 categories, 25 pilot cities and 4 demo forms. Full official national localities, external staging HTTPS, off-host backup, alerts, credential rotation and branch protection are not implied complete by Stage 02 CI.
- **Next (historical):** initial CI and independent review were required; see current verified status below. No live DB/VPS/DNS/production changes.

## 2026-11-12 — Stage 02.6 final integration CI and Codex finding ZP-02-001

- **Independent Codex Cloud assessment of SHA `127a9d7e3ea8039f093d85e34bd184c365486587`:** `CHANGES_REQUIRED`. Reproduced `ZP-02-001` (MEDIUM/BLOCKER): with indexing flag enabled, incomplete translated category/city lists could be indexed; translated description fallback likewise failed to prevent thin indexed details. Documentation status `ZP-02-002` (LOW/NON-BLOCKER) needed refresh.
- **Correction SHA:** `067da9da669a9c66645404b1ec293cada1144f74`, existing `stage-02-catalog-localization` and Draft PR #8. Added lazy indexability predicate (only evaluates under opt-in), RU/EN/HE names and required description coverage for *every displayed catalog/location entry*, without modifying display fallback, PK/FK, URLs, seed or production. Seven SEO regression tests reproduce missing EN/HE labels/descriptions, including section/category/city/district/service cross-links, and prove fully translated supplied pages can index only when explicitly enabled.
- **GitHub [Django CI #43162334570](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43162334570) SUCCESS on correction SHA:** 16/16 targeted 02.4 SEO tests, 4/4 Stage 02.6 integration, 10/10 i18n, 15/15 questionnaires, 45/45 Playwright Chrome viewport scenarios, **151/151 complete Django suite**, Ruff, migrations and seed repetitions PASS; coverage 94,0% of *targeted `apps.marketplace.services` only*, not whole repo.
- **[Isolated Docker smoke #43162342520](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43162342520) SUCCESS** on correction SHA; disposable CI environment only, not a publicly trusted staging host.
- **Now:** `02.4 CODE_VERIFIED / ZP-02-001_FIXED / TARGETED_CODEX_RECHECK_PENDING`; `02.6 CI_VERIFIED / FINAL_ACCEPTANCE_OPEN`. Prior `QA_PENDING` and automated-test `NOT_RUN` entries are historical, not the current state.
- **Remaining:** repeat *focused* Codex review of the new SEO guard and documentation; native Hebrew content/editorial approval (including 11 suggested categories, 25-city pilot and 4 demo forms) not obtained; physical Android/iPhone `NOT_RUN`; national city registry incomplete; off-host backup, delivered alert, credential rotation, branch protection, public staging HTTPS and PSEO release plan pending. PR #8 **Draft / NOT_MERGED**; no VPS, production, DNS, Cloudflare or live user DB operations.

## 2026-11-12 — Stage 02 focused Codex re-review: CODE_REVIEW_PASS

- **Independently reviewed SHA:** `cad90a071a169a9d70d99629422ff852db610e7c` in the existing `stage-02-catalog-localization` branch / Draft PR #8. Final report: **`CODE_REVIEW_PASS`**, no new code blockers.
- **`ZP-02-001 FIXED`:** lazy SEO indexability, all visible entities' RU/EN/HE names and required descriptions, whitespace/missing translations, default noindex, filtered/no-supply routes and legacy URL safety confirmed. Targeted independent run: Ruff, Django system check, migrations consistency, 16/16 SEO tests, canonical/hreflang and private contact marker PASS.
- **`ZP-02-002 FIXED`:** ROADMAP, PROGRESS, STAGE_02_INTEGRATION and STAGE_02_LOCALIZED_URLS correctly distinguished historical outcomes from verified CI and open manual gates.
- **Exact-SHA GitHub Actions:** [Django CI #43162656220](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43162656220) **SUCCESS** (151/151 full tests, 16/16 SEO, 45/45 Chrome, targeted service coverage 94.0%); [isolated Docker smoke #43162656363](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43162656363) **SUCCESS**. Codex deliberately did **not** repeat unchanged full suite / Chrome locally.
- **Decision:** `STAGE_02_CODE_REVIEW_PASS / CI_VERIFIED / MANUAL_AND_INFRASTRUCTURE_GATES_OPEN`, **not** `STAGE_02_DONE` or permission to deploy/merge. This note updates documentation only after the reviewed SHA; source code remains unchanged.
- **Manual gates:** native Hebrew proofreading; review of 11 new categories, 25 pilot cities and four sample questionnaires; physical Android/iPhone NOT_RUN; complete national CBS city dataset; original CI screenshot artifact/UX final approval; verified legacy SEO URL inventory before Stage 08.
- **External infrastructure gates:** off-host backups, delivered alerts, credential rotation, branch protection, publicly trusted staging HTTPS and production/DNS/Cloudflare/VPS rollout are unverified or require owner authorization. PR #8 remains **Draft / NOT_MERGED**.
