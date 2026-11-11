# ZemiPro — этап 01.4: Docker Compose и отдельный staging

**Статус:** IMPLEMENTED / DEPLOYMENT_NOT_RUN. Код и конфигурации не являются
подтверждением рабочего HTTPS или сохранности PostgreSQL после рестарта.
**Без разрешения владельца нельзя запускать это на VPS, менять домен,
Cloudflare, DNS, production, существующие тома и реальные базы.**

## Архитектура и границы

- Один Django в `zemipro_web/` и отдельная PostgreSQL 17 на окружение.
- Образ `Dockerfile.django`: Python 3.12, pinned runtime requirements,
  непривилегированный UID 10001, Gunicorn, `collectstatic`, без реальных
  секретов в build context (`.dockerignore`).
- `docker/entrypoint.sh`: только при `RUN_MIGRATIONS=1` и
  `DJANGO_ENV=development|staging` выполняет `migrate --noinput`;
  ошибка останавливает запуск веб-сервера. Миграции **не** разрешены этим
  скриптом для `DJANGO_ENV=production`.
- `docker-compose.django.yml`: локальная dev-среда, web и БД опубликованы
  только на `127.0.0.1`, тома `dev_postgres`, `dev_static`, `dev_media`.
- `docker-compose.staging.yml`: отдельный Compose project
  `zemipro-staging`, postgres `zemipro_staging` без опубликованного порта,
  отдельная внутренняя сеть, тома `staging_*`, веб **не** публикует порт,
  reverse proxy Caddy публикует только HTTP/HTTPS.
- Caddy автоматически запрашивает TLS-сертификат для `STAGING_DOMAIN`,
  обслуживает `/static/` из read-only тома; запросы `/media/*` получают
  HTTP 404 и не раскрывают приватные файлы. Публичные загрузки не включены.
- PostgreSQL `pg_isready` и Gunicorn TCP liveness управляют порядком
  запуска; TCP **не** доказывает доступность Django URL или БД после
  старта. Глубокий health endpoint/мониторинг входит в **01.5**.
- Лимиты памяти (staging DB 320 MiB, web 384 MiB, proxy 96 MiB) и один
  Gunicorn worker — стартовые конфигурации, не результат stress-тестов.
  Версию Docker host, свободную RAM и допустимость этих лимитов проверить
  до deployment. Staging предполагает собственный изолированный сервер.

## Проверка без запуска и без production

Наличие Docker Compose обязательно для следующих команд. Проверять на
личной тестовой машине, где **нет production Docker volume и данных**.
Нельзя считать знакомый порт/имя доказательством изоляции.

Из каталога `zemipro_web/`:

```bash
docker compose -f docker-compose.django.yml config --quiet
```

Для staging создать локальный **неотслеживаемый** `.env.staging` на основе
`.env.staging.example`; заменить `staging.example.invalid` реальным
согласованным staging-доменом. Сгенерировать *новые независимые* секреты;
ни старые Telegram/PSEO, ни production keys не использовать. Не коммитить
файл и не выводить развёрнутый `docker compose config` в логи: он содержит
значения секретов. Затем выполнить **только синтаксическую проверку**:

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml config --quiet
```

В CI запускается аналогичная `config --quiet` с **синтетическими**
значениями; создание staging infrastructure в GitHub Actions запрещено.

## Локальная репетиция development (только новая чистая БД)

Перед запуском установить, что Compose project/volumes новые и не принадлежат
действующим сервисам. Проверить `docker compose ... ps`, каталог данных и
наличие свободных портов. Запрещено `docker compose down -v` на неизвестных
томах, а также копирование production БД или медиа.

```bash
docker compose -f docker-compose.django.yml up --build -d
docker compose -f docker-compose.django.yml ps
docker compose -f docker-compose.django.yml logs --tail=50 web
docker compose -f docker-compose.django.yml exec -T web python manage.py migrate --check
```

Убедиться, что `web` healthy, миграции применены, главная страница
открывается через localhost, статические файлы доступны и private data не
появляются в публичных ответах. Создать только синтетические test-записи и
проверить сохранность DB/медиа после `restart` и `up --force-recreate`.
Сравнить counts, IDs, хеши фиктивного медиа и `showmigrations` до/после.
Остановка **без удаления volumes**:

```bash
docker compose -f docker-compose.django.yml down
```

## Разрешённое впоследствии staging HTTPS испытание

Отдельно согласовать hostname, DNS, выделенную машину/IP, порты TCP 80/443,
TLS/ACME доступность, непересекающиеся volumes и credentials. ВНИМАНИЕ:
Caddy автоматический HTTPS требует публичную доступность 80/443 либо
специально настроенный одобренный ingress; изменение локального порта на
8443 само по себе не обеспечивает выпуск сертификата.

**Только после явного разрешения владельца:**

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml up --build -d
docker compose --env-file .env.staging -f docker-compose.staging.yml ps
```

Сверить: `https://STAGING_DOMAIN/` валидный TLS и HTTP без утечек,
`/static/` отвечает 200, `/media/private-example` отвечает 404, DB
не доступна с публичного интерфейса, Gunicorn недоступен напрямую, данные
сохраняются после рестарта, `migrate --check` проходит. Проверить, что
redirect и trusted `X-Forwarded-Proto` корректны **только через Caddy**.

### Откат и безопасность

- Сохранить исходный SHA приложения и названия staging Compose volumes до
  обновления. Первым шагом отката является возврат предыдущего tested image
  после выяснения совместимости схемы; `migrate` назад не запускать вслепую.
- PostgreSQL backup/restore и процедура проверки восстановления относятся
  к 01.5. До подтверждения **не объявлять staging пригодным для production**.
- Никаких подключений к существующей боевой PostgreSQL, удаления старых
  volumes, публикации медиа и запуска платных сервисов.
- Новый staging не должен использовать текущий публичный домен
  `zemipro.co.il` до этапа 08 и специального разрешения.

## Приёмочные тесты и статусы

| Контроль | Сейчас |
| --- | --- |
| Review Dockerfile / Compose / Caddy / entrypoint | STATIC_REVIEW |
| Docker Compose dev/staging `config --quiet` | NOT_RUN пока не запущен |
| Build non-root image / `.dockerignore` exclusion | NOT_RUN |
| PostgreSQL readiness / web health | NOT_RUN |
| Migrated clean synthetic DB, restart + data persistence | NOT_RUN |
| Staging HTTPS with approved domain/TLS | BLOCKED (нет разрешения на staging deployment) |
| Production/DNS/VPS/реальные секреты | NOT_TOUCHED |

Приёмка 01.4: только после реального build/config, restart/persistence
прогона в изолированном окружении и подтверждённого HTTPS staging.
