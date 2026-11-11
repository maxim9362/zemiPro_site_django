# ZemiPro — 01.5: безопасные логи, health и backup/restore

**Статус:** `SYNTHETIC_BACKUP_AND_RESTORE_PASS / OFF_HOST_AND_ALERT_PENDING`. Этот документ
описывает код и проверяемую процедуру; он не утверждает, что расписание
уже установлено, резервная копия создана, восстановление проверено или
оповещения настроены на действующем сервере.

## 1. Границы безопасности

- **Никаких production действий.** Текущие VPS, DNS, Cloudflare,
  real PostgreSQL, существующие тома и пользовательские медиа не трогать.
- Сохраняется одна кодовая база Django и одна PostgreSQL на каждую среду.
- Legacy Telegram/PSEO/SQLite и старые учётные данные **не переносить**.
- Новые staging secrets использовать только после явного разрешения владельца,
  в untracked `.env.staging` (0600 или эквивалент ACL); не выводить
  полный `docker compose config`, environment или переменные с секретами.
- Приватные дампы и медиа содержат потенциальные PII. Не прикладывать
  к GitHub/PR/чату/общим логам и не делать публичными через HTTP.

## 2. Логи и диагностические URL

`core.observability.SafeJsonFormatter` выдаёт JSON с ограниченными
полями `timestamp` (UTC), `level`, `component`, `event`, по возможности
`status_code`. Фильтр **вообще не использует** `record.getMessage()`,
`record.args`, `record.request`, пути и query strings, exception details
или traceback. Поддерживаются только постоянные allowlisted события
например `database_unavailable`. Отсутствие exception text намеренное:
это минимальный безопасный baseline, а не полнофункциональный error tracker.
Проверить реальное логирование Gunicorn, Caddy, контейнеров и внешнего proxy
отдельно: форматтер Django не гарантирует redaction сторонних компонентов.

| Endpoint | Значение | Ошибка | Публичный ответ |
| --- | --- | --- | --- |
| `GET /health/live/` | Django обрабатывает HTTP | 5xx вне view | `{"status":"ok"}` / 200 |
| `GET /health/ready/` | `SELECT 1` на Django PostgreSQL | DB error → 503 | `{"status":"ok"}` или `{"status":"unavailable"}` |

Оба ответа имеют `Cache-Control: no-store`; POST → 405.
Нет адресов сервера, имён БД, SQL text, стека исключения, IP клиента,
телефонов, user IDs и деталей заказов. Названия health endpoint могут
быть публичны, но сам сервер обязан использовать trusted reverse proxy.
DB `connect_timeout=3` ограничивает время установления соединения,
**не** длительность SQL-запроса; медленные запросы отдельно измерить.
Ограничение частоты public probes и нагрузочное тестирование — 01.6.

Проверять логи:
```bash
python manage.py test core.tests.test_health core.tests.test_observability
```
Тесты этих модулей используют mocks, не реальные PostgreSQL connections.

## 3. Staging: отдельные резервные копии без автозапуска

`docker-compose.staging.yml` объявляет opt-in `backup` service
(`--profile maintenance`) в закрытой сети, с отдельным named volume
`staging_backups` и утилитами PostgreSQL 17. Скрипт
`docker/staging-backup.sh` разрешает только `PGHOST=db`,
`PGDATABASE=zemipro_staging` и `PGUSER=zemipro_staging`.
Он создаёт частный временный архив custom `pg_dump`, проверяет
`pg_restore --list`, публикует целый архив атомарным rename и
пишет SHA-256 рядом. Промежуточный файл удаляется при неудаче.
Ни автоматического удаления старых backup, ни restore поверх DB нет.

**До согласования host/secret/DNS ничего не запускать.**
После разрешения оператора и проверки, что это отдельная staging-БД
с **синтетическими данными**:

```bash
cd /absolute/authorized/staging/zemipro_web
docker compose --env-file .env.staging -f docker-compose.staging.yml \
  --profile maintenance run --rm backup
```

Проверить, что archive и `.sha256` присутствуют внутри staging
backup volume и checksum совпадает. Затем перевезти копию по защищённому
каналу в *отдельное* зашифрованное хранилище с ограничением доступа;
один Docker volume на том же хосте **не** является disaster recovery.

## 4. Расписание, сохранность и мониторинг

Планируемое staging расписание: ежедневно в **03:15 UTC**. Template
`docker/staging-backup.cron.example` содержит абсолютные пути-заглушки:
оператор обязан заменить их и **вручную** установить задачу на
одобренном staging-host; из GitHub cron не активируется. На хосте
обеспечить owner-only доступ к `.env.staging` и журналу backup.
При каждом запуске проверять: exit code, timestamp последней
успешной копии, контрольную сумму и свободное место на backup volume.
Уведомления при пропуске/сбое и хранение off-site требуется настроить
отдельно, до принятия 01.5.

Сохранение staging: минимум 7 успешных ежедневных архивов +
еженедельная **отдельная encrypted off-host** копия (целевая политика).
Автоматической ротации/удаления файлов пока нет, чтобы не потерять
ценные данные из-за непроверенной команды. Назначить ответственного
владельца/оператора за ежедневную сверку и безопасную ручную очистку
после проверки off-host копий.

Проверка доступности staging каждые **5 минут** после одобрения host:
задать `STAGING_HEALTH_URL=https://.../health/ready/` в защищённом
окружении мониторинга, запускать `docker/check-staging-health.sh`
по планировщику. Скрипт не пишет URL, ответ или секрет в логи, при
неуспехе возвращает exit=1 и оставляет неизменный сигнал
`ALERT: ZemiPro staging readiness failed` (stderr/syslog).
Нужны доступные `curl`, `logger`, syslog и отдельный проверенный
канал доставки алерта ответственному; **его ещё нет**. Не заявлять
`MONITORING_ACTIVE` до воспроизведения 503 + видимого алерта.

При инциденте оператор фиксирует только UTC время, SHA запущенного
кода, тип события, HTTP статус, статус контейнеров и факт наличия
внешней копии. Не сохранять в общий отчёт stdout `pg_dump`,
параметры подключения, полные логи с PII или приватные данные.

## 5. План репетиции восстановления (только синтетические данные)

В этой среде нельзя делать восстановление production. Сначала
проверить паспорт backup: SHA-256, `pg_restore --list` и версию
PostgreSQL. Для test restore создать **другую** пустую PostgreSQL
с именем `zemipro_restore_*` на local loopback (не общий том).
Использовать проверенный `scripts/stage00_pg_snapshot.py restore`
с набором `ZEMIPRO_RESTORE_DB_*` и архивом *вне репозитория* —
скрипт запрещает удаление таблиц, удалённые хосты и непустые цели.
Защитные правила см. `docs/STAGE_00_BACKUP_RESTORE.md`.

На восстановленном клоне сверить `django_migrations`, таблицы, row
counts и синтетические ID, категории/города/заказы/отклики/жалобы;
сравнить со снимком из исходной staging DB. При несовпадении:
`FAIL / STOP`, никаких фиктивных исправлений. Приватные media:
отдельная защищённая копия, manifest с именами/хешами и тест возврата
в *изолированный* каталог; **текущий PG backup media не содержит**.
Никакой автоматической перезаписи томов или schema rollback.

## 6. Ручной rollback и обязанности

1. **Владелец:** разрешает подходящий staging/production host, DNS,
   реальные секреты, отдельный backup location и условия теста.
2. **Staging-оператор:** фиксирует working app SHA, schema version,
   container images, успешную внешнюю копию и доступную процедуру
   возврата без `down -v`/автоматического reverse migration.
3. При отказе: прекратить выпуск изменений, проверить DB health и
   backup; при несовместимых migrations — **forward fix** по отдельному
   решению или восстановление в новый независимый экземпляр.
4. Только после dry-run и отдельного разрешения может планироваться
   production rollback/cutover; **здесь ничего не применялось**.

## 7. Требуемые доказательства для `DONE`

| Условие | Статус 2026-11-11 |
| --- | --- |
| Django redacted JSON logger + health endpoints в коде | PASS (Codex, synthetic PostgreSQL) |
| Backup service и скрипт с guard | PASS (Codex + GitHub runner) |
| Cron template и 5-минутный monitor script | PREPARED / NOT_INSTALLED |
| Synthetic staging dump and checksum | PASS (GitHub CI #43028406371); external staging backup NOT_RUN |
| Synthetic restore + schema/count parity | PASS (Codex isolated test) |
| Off-host encrypted backup storage | NOT_CONFIGURED |
| Ошибка health 503 вызывает доставленный мониторинг-alert | NOT_RUN |
| Production/VPS/DNS/реальные PostgreSQL | NOT_TOUCHED |

Stage 01.5 остаётся `IN_PROGRESS`, пока тест восстановленной базы
и сигнал отказа не будут подтверждены фактически. Полный этап 01
дополнительно требует всего 01.1–01.6 и итоговый Codex review.

### Добавленная независимая CI-проверка
На GitHub Actions [run #1](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43028406371)
создание *synthetic* staging backup, `pg_restore --list` и SHA256
**PASS**. Ранее Codex отдельно выполнил восстановление на новой синтетической
БД и сверил строки/миграции — **PASS**. **НЕ выполнены** off-host
зашифрованный backup и фактически доставленный alarm: эти операции требуют
отдельного согласованного staging окружения и канала уведомлений.
