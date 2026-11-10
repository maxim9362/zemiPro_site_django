# ZemiPro — 00.3: реестр источников и контрольной точки

**Дата:** 2026-11-10 · **Статус:** STATICALLY_INVENTORIED / RUNTIME_UNVERIFIED

## Контрольная точка исходного кода

| Актив | Ревизия/местоположение | Проверено |
| --- | --- | --- |
| Основной Django + архивный Telegram | `maxim9362/zemiPro_site_django`, `main` @ `ba337737c6912ebaa922ae9b5cafebc722cbd71b` | Git SHA известен; runtime DB не открывалась |
| Подэтап Django 01.1 (в отдельной ветке) | `stage-01-stabilization` — коммит `5cdb19c6a790031d32234dbaad21353bf489bafb` включён в историю | Код существует в Git, не развёрнут |
| PSEO (удалён владельцем; исторические метаданные) | Был `maxim9362/zemipro_site_pseo`, tree `def493642dbb86ffe7543efecb81f08fecf50e60` | GitHub API сейчас 404; запись историческая, не доступный репозиторий |
| Документация об обязательности этапа 13 | PR #5, v1.3.0, пока отдельная ветка | Не объединено в `main` на момент фиксации |

## Хранилища и данные (статус доступа)

| Источник | Указано в конфигурации или Git | Подтверждённое наличие/размер | Сохранение/восстановление |
| --- | --- | --- | --- |
| Django PostgreSQL | `zemipro_web/docker-compose.django.yml`: `postgres:15-alpine`, volume `zemipro_django_data`, локальный порт `5433` | Реальный контейнер, база, версии, строки — UNVERIFIED | NOT_RUN |
| Django media | `zemipro_web/core/settings.py`: `MEDIA_ROOT` в `zemipro_web/media/` | Фактические файлы/размер неизвестны; в Git не перечислены | NOT_RUN |
| Django migrations | `zemipro_web/apps/*/migrations/` (accounts, marketplace, locations, notifications, moderation, analytics) | Файлы есть, applied migrations в DB UNVERIFIED | Git-снимок; DB restore NOT_RUN |
| Архивный Telegram PostgreSQL | `docker-compose.yml`: `postgres:15-alpine`, volume `postgres_data` | Реальный runtime/содержимое UNVERIFIED | NOT_RUN; не переносить |
| Старый PSEO SQLite | `masters_admin_write.db` (Git-tree size 5 771 264 bytes), `zemi_master_seo_storage.db` (741 376 bytes) | Отслеживаемые файлы Git; не открывались, строки/PII UNVERIFIED | Нет отдельного проверенного backup; не переносить в Django |
| Реальные secrets/env | PSEO `.env`, `index_site/service_account.json` | По именам есть, значения/валидность не изучались | NOT_RUN; риск 00.2 |

**Не путать Git SHA и контрольные суммы реальной БД:** SHA коммита доказывает состояние репозитория, но не сохранность deployment, содержимого PostgreSQL или медиа.

## Шаблон журнала локальной репетиции (не заполнять догадками)

Заполнить после разрешённой проверки и хранить без конфиденциальных значений, снимков БД и контактных данных:

| Поле | Значение |
| --- | --- |
| Дата и изолированная среда | NOT_RUN |
| PostgreSQL и pg_dump/pg_restore версии | NOT_RUN |
| Источник и цель (только безопасные имена БД) | NOT_RUN |
| Размер архива / SHA-256 | NOT_RUN |
| Тест `pg_restore --list` | NOT_RUN |
| Проверка пустой целевой БД | NOT_RUN |
| Повторное восстановление / отказ при непустой цели | NOT_RUN |
| Сравнение схем, миграций и counts | NOT_RUN |
| Медиа и ACL | NOT_RUN |
| Итог PASS/FAIL, проблемы и ответственный | NOT_RUN |

Данные внешних сервисов, настоящая production-БД и приватные SQLite не были прочитаны. Отдельное подтверждение владельца требуется для любых операций с ними.
