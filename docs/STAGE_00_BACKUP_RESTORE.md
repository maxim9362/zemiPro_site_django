# ZemiPro — 00.3: резервирование и восстановление (только изолированный тест)

**Дата:** 2026-11-10  
**Статус:** PREPARED / RESTORE_NOT_VERIFIED  
**Норматив:** `docs/DEVELOPMENT_PLAN.md`, 00.3; `docs/DECISIONS/ADR-0001-DJANGO-ONLY-NO-TELEGRAM.md` и `ADR-0002-REBUILD-WITH-URL-ONLY.md`.

## Правила безопасности

- Здесь **нет доступа к production**, реальным PostgreSQL, VPS и архивам персональных данных. Ни одного реального backup/restore не выполнялось.
- `scripts/stage00_pg_snapshot.py` **жёстко допускает** только источники с именем `zemipro_fixture_*`, цели `zemipro_restore_*`, хост `localhost/127.0.0.1/::1`. Он не создаёт, не удаляет, не очищает базы. Для реального бэкапа нужен **отдельно согласованный production runbook** и разрешение.
- В архиве могут быть контакты и личные данные. Не загружать его в Git, PR, чат, общие облачные папки. Хранить отдельно, с ограниченными правами и шифрованием; не печатать пароли и дампы.
- `PGPASSWORD` и другие секреты передавать через локальные переменные окружения/секрет-хранилище. Не вставлять в команды shell, историю терминала или логи. Название переменной `ZEMIPRO_SOURCE_DB_PASSWORD` / `ZEMIPRO_RESTORE_DB_PASSWORD` допустимо; значения в документах отсутствуют.
- При restore база **должна быть создана заранее и пуста**. Целевую базу создавать только на изолированном локальном PostgreSQL, без общих volume с production.

## Источники и приоритеты

1. Django web: `zemipro_web/docker-compose.django.yml`, PostgreSQL 15 (образ `postgres:15-alpine`), объявленный volume `zemipro_django_data`, медиа `zemipro_web/media/` по настройкам; **существование живой БД, содержимого volume и файлов медиа не подтверждено**.
2. Отдельный старый Telegram compose: `docker-compose.yml`, `postgres_data`; Telegram отключён **в плане**, реальный runtime/данные не трогать. Не объединять со схемой Django.
3. Приватный PSEO: SQLite `masters_admin_write.db` и `zemi_master_seo_storage.db` отслеживаются в Git, но **не читались**; старый PSEO не переносится. Сохранность исторических файлов и секретов оценить перед удалением.
4. Конфигурации и миграции: код и Django migrations в Git по зафиксированному SHA; `.env`, действующие ключи, реальные БД и медиа не входят в репозиторный snapshot.

## Воспроизводимая тестовая репетиция (выполнить только после разрешения на тестовую БД)

Нужны установленные PostgreSQL CLI: `pg_dump`, `pg_restore`, `psql`; их major-версия должна быть совместима с версией источника. Целевая БД заранее создана отдельно (пример: `zemipro_restore_00`). Использовать **синтетические данные**, например Django test fixtures, а не реальные контакты.

1. В защищённом локальном окружении установить переменные `ZEMIPRO_SOURCE_DB_NAME=zemipro_fixture_00`, `ZEMIPRO_SOURCE_DB_HOST=127.0.0.1`, `ZEMIPRO_SOURCE_DB_PORT=5432`, `ZEMIPRO_SOURCE_DB_USER` и при необходимости `ZEMIPRO_SOURCE_DB_PASSWORD` через менеджер секретов. Для цели отдельно `ZEMIPRO_RESTORE_DB_NAME=zemipro_restore_00`, `ZEMIPRO_RESTORE_DB_HOST=127.0.0.1`, `ZEMIPRO_RESTORE_DB_PORT=5432`, `ZEMIPRO_RESTORE_DB_USER`, `ZEMIPRO_RESTORE_DB_PASSWORD`.
2. Создать каталог для архивов **вне репозитория** с правами, доступными только владельцу. На Windows проверить ACL каталога отдельно; `chmod` не гарантирует корректность NTFS ACL.
3. Снять архив: `python scripts/stage00_pg_snapshot.py backup /absolute/private/path/fixture-00.dump`.
4. Проверить структуру архива и SHA-256: `python scripts/stage00_pg_snapshot.py verify /absolute/private/path/fixture-00.dump`.
5. Создать **пустую** целевую базу на локальном тестовом PostgreSQL; её имя обязательно начинается `zemipro_restore_`.
6. Выполнить: `python scripts/stage00_pg_snapshot.py restore /absolute/private/path/fixture-00.dump`. Скрипт останавливается, если целевая БД содержит пользовательские таблицы. Команды `--clean`, `--create` или удаления БД не применяются.
7. Сверить отдельно в источнике и цели: версию PostgreSQL, перечень Django migrations, число схем/таблиц и контрольные `COUNT(*)` таблиц `accounts_user`, `marketplace_order`, `marketplace_response` и других релевантных таблиц. Не сохранять в документы записи пользователей, адреса, тексты заказов и контакты. Результаты counts, SHA-256, размеры и PASS/FAIL занести в локальный журнал проверки.
8. Проверить отдельную копию медиа (если реально существуют файлы): список, общий объём, ограничение доступа и выборочные хеши. Не загружать медиа в Git.

Для Docker Django, если порт `5433` локально проброшен в `docker-compose.django.yml`, тестовая база может использовать `127.0.0.1:5433`, **только если установлен факт, что это отдельный тестовый экземпляр**. Не считать это гарантией безопасности по одному номеру порта.

## Требования перед закрытием 00.3

| Критерий | Фактический статус на 2026-11-10 |
|---|---|
| Инвентарь объявленных БД, volume, миграций и медиа | STATICALLY_VERIFIED / существование runtime UNVERIFIED |
| Утилита создания/проверки тестового дампа | CODE_PREPARED / EXECUTION_NOT_RUN |
| Утилита восстановления с защитой пустой БД | CODE_PREPARED / EXECUTION_NOT_RUN |
| Реальный backup и проверка восстановления | **NOT_RUN** |
| Контрольные counts, hash, версия PostgreSQL, размеры | **NOT_RUN** |
| Подтверждённая безопасность архива и хранилища | **NOT_RUN** |
| Production и внешние службы | **NOT_TOUCHED** |

**Итог:** 00.3 оставлен `IN_PROGRESS / RESTORE_NOT_VERIFIED`. Продолжать другие безопасные подэтапы можно, но нельзя отключать/удалять старые ресурсы или запускать миграции реальных данных до завершения backup/restore и решения по секретам.
