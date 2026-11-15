# Stage 09.6 — план перехода на Django

Статус: **`09.6_PREPARED / PRODUCTION_CUTOVER_PENDING`**.  
Этот документ не является разрешением выполнить команды. В Codex Cloud не
изменялись production, VPS, reverse proxy, DNS, Cloudflare, TLS, рабочая
PostgreSQL, media или действующий сайт.

## 1. Обязательные условия до окна переключения

- отдельное письменное owner GO на cutover, согласованное окно и оператор;
- Stage 09 PR принят/merged обычным процессом, final SHA и обязательный CI green;
- Stage 09.1 закрыт HTTP/GSC: каждый значимый URL имеет утверждённый
  KEEP/301/404/410, активируемые строки прошли staging matrix;
- publicly trusted staging HTTPS, RU/EN/HE/RTL и критические browser paths PASS;
- qualified Hebrew/editorial sign-off, physical-device smoke и accessibility;
- проверенный encrypted off-host PostgreSQL **и media** backup, checksum,
  retrieval и restore rehearsal в новую БД;
- известны текущие production topology, image/SHA, proxy config, volumes,
  database version/size, RPO/RTO, контакты on-call;
- устранены/приняты release gates Stage 01/02: secrets rotation, alerts,
  branch protection и безопасный SMTP/OAuth режим.

Если любой пункт неизвестен, оператор останавливается до переключения.

## 2. Подготовка проверенного артефакта

На авторизованном build/staging host, не на production:

```bash
export RELEASE_SHA='<final-merged-sha>'
git fetch --no-tags origin main
test "$(git rev-parse origin/main)" = "$RELEASE_SHA"
git archive --format=tar "$RELEASE_SHA" | sha256sum
docker compose --env-file .env.staging -f docker-compose.staging.yml config --quiet
docker compose --env-file .env.staging -f docker-compose.staging.yml build --pull web
```

Зафиксировать digest образа в release ticket; не использовать плавающий образ
без digest. `.env.staging`/production secrets не печатать и не коммитить.

## 3. Staging rehearsal

```bash
docker compose --env-file .env.staging -f docker-compose.staging.yml up -d db
docker compose --env-file .env.staging -f docker-compose.staging.yml run --rm web python manage.py migrate --plan
docker compose --env-file .env.staging -f docker-compose.staging.yml up -d web proxy
docker compose --env-file .env.staging -f docker-compose.staging.yml exec web python manage.py check --deploy
docker compose --env-file .env.staging -f docker-compose.staging.yml exec web python manage.py migrate --check
docker compose --env-file .env.staging -f docker-compose.staging.yml --profile maintenance run --rm backup
```

Проверить через staging hostname: `/health/live/`, `/health/ready/`, `/ru/`,
`/en/`, `/he/`, Ashdod catalog/service/profile, auth, создание заявки, static,
`/robots.txt`, `/sitemap.xml`, 21 legacy URL, 404/410, canonical/hreflang и
отсутствие Stage 14 публичных страниц/flags. Сначала оба Stage09 flag `false`,
затем — только в согласованном SEO acceptance окне — проверить утверждённую
матрицу с `true` и вернуть `false`.

## 4. Backup и восстановление

Перед cutover production-оператор использует существующую утверждённую систему
backup, а не staging volume. Минимальный проверяемый набор:

```bash
pg_dump --format=custom --no-owner --no-acl --file='<off-host-staging-path>/pre-cutover.dump' '<production-connection-from-secret-store>'
sha256sum '<off-host-staging-path>/pre-cutover.dump'
pg_restore --list '<off-host-staging-path>/pre-cutover.dump'
createdb '<new-isolated-restore-db>'
pg_restore --no-owner --no-acl --dbname='<new-isolated-restore-db>' '<off-host-staging-path>/pre-cutover.dump'
```

Команду нельзя копировать буквально: connection и пути берутся из одобренного
secret/backup runbook. Restore выполняется только в **новую** изолированную БД,
никогда поверх production. Отдельно копируются media/private media с шифрованием
и проверкой количества/checksum.

## 5. Будущее переключение (только после owner GO)

Параметризованный порядок для подтверждённой topology:

1. Включить maintenance/change window; сохранить текущие proxy config, image
   digest и release SHA в off-host ticket.
2. Остановить только запись приложения согласованным способом; сделать final
   backup и повторно проверить restore manifest.
3. На новом release-контейнере выполнить `python manage.py migrate --plan`,
   затем `python manage.py migrate --noinput`, `python manage.py migrate --check`,
   `python manage.py collectstatic --noinput`, `python manage.py check --deploy`.
4. Запустить Django на внутреннем loopback/upstream и проверить health/smoke,
   пока публичный proxy всё ещё направлен на старый сайт.
5. Атомарно заменить только upstream в утверждённом Caddy/Nginx config,
   выполнить `caddy validate --config <candidate>` или `nginx -t`, затем штатный
   reload. Не менять DNS/Cloudflare, если сохранён тот же ingress.
6. Сначала оставить оба SEO flag false; проверить auth/заказы/чат и статусы.
7. Только по отдельному SEO GO включить `ZEMIPRO_CATALOG_INDEXING_ENABLED=true`
   и `ZEMIPRO_LEGACY_REDIRECTS_ENABLED=true`, перезапустить application workers,
   повторить URL matrix без изменения proxy/DNS.

Фактическая команда reload зависит от подтверждённого production proxy/service
manager; до инвентаризации topology её нельзя безопасно выдумать.

## 6. Smoke и наблюдение

В первые 15/60 минут и 24/72 часа контролировать:

- health/latency и 5xx, PostgreSQL connections/locks, CPU/RAM/disk;
- 404/410/301/308 по **нормализованному path без query/PII**;
- redirect loops/chains, destination 200, canonical/hreflang reciprocity;
- sitemap fetch/errors и robots; после owner GO — GSC submitted/indexed changes;
- регистрации, вход, заявки, предложения, чат и уведомления без текста/контактов
  в telemetry;
- резкий рост 404/500 или падение конверсии относительно зафиксированного
  baseline. Alert destinations должны быть реально доставлены до cutover.

Stop conditions: health failure, migration mismatch, auth/order regression,
PII exposure, redirect loop, массовый нерелевантный redirect, рост 5xx или
необъяснимый скачок существенных 404.

## 7. Rollback

1. Немедленно вернуть оба Stage09 flag в `false` (SEO rollback без code/DB).
2. Если приложение неисправно — атомарно вернуть сохранённый proxy upstream и
   предыдущий image digest, validate и штатно reload.
3. Не выполнять обратные schema migrations вслепую. Совместимые additive
   миграции оставить и применить forward fix. Restore production БД — только
   отдельное owner-approved disaster-recovery решение после анализа записей,
   сделанных после cutover.
4. Сохранить логи/метрики без PII, timestamp, final SHA, симптомы и решение.
5. Старый сайт не удалять до завершения согласованного периода наблюдения.

## 8. Совместимость с Draft PR #18 (Stage 14)

Проверен remote head `620242aa3605a78aacf1c608c8fa8a4f99d2edea` без merge.

- URL Stage14 (`advice`, `questions`, `recommendations`, `share`,
  `recommend-master`) не пересекаются с Stage09 catalog/master routes.
- Stage14 намеренно оставляет sitemap/robots под контролем Stage09 и предоставляет
  `sitemap_candidates()` только как будущий hook.
- Ожидаемые ручные rebase-конфликты: `core/urls.py`, `core/config/base.py`,
  `templates/base.html`, `docs/ROADMAP.md`, `docs/DEVELOPMENT_PLAN.md`,
  `docs/TECHNICAL_SPEC.md`, `docs/PROGRESS.md`.
- При будущем rebase сохранить Stage14 owner-gated flags `False`, его безопасный
  Article JSON-LD block и Stage09 OG/JSON-LD. Статьи добавлять в sitemap только
  после отдельного публичного GO и проверки human translations; Q&A и
  рекомендации автоматически не индексировать.
- Миграции не конфликтуют: Stage09 использует `apps.seo.0001–0003`, Stage14 —
  отдельное `apps.knowledge.0001–0008`.

Полная интеграционная проверка Stage09+Stage14 без merge невозможна и остаётся
`PENDING` после будущего rebase PR #18. Код Stage14 не копировался.

