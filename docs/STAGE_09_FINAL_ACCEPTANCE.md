# Stage 09 — финальная техническая приёмка

Дата: 2026-11-15

Статус: **`LOCAL_CODE_VERIFIED / CUTOVER_PENDING / PR_API_BLOCKED / NOT_MERGED`**.

## Проверенный состав

- base: `origin/main` `3d640f66a3acc61bec623bd9e31786ae63b7196b`;
- code-review SHA: `d706ba9a0cab6688ea7408f84442d0161cb0d219`;
- ветка: `stage-09-django-seo`;
- Stage14 compatibility source: `origin/stage-14-knowledge`
  `620242aa3605a78aacf1c608c8fa8a4f99d2edea`, без merge;
- Python 3.12.14, Django 5.2.19, PostgreSQL 17.12, Ruff 0.17.4,
  Chromium 155, Docker 29.9.2, Compose 2.40.3.

## Результаты 09.1–09.7

| Подэтап | Результат | Оставшийся внешний гейт |
|---|---|---|
| 09.1 | `SAFE_PREPARATION_COMPLETE` — 21 уникальный URL сохранён, предположения отделены от фактов | `EXTERNAL_HTTP_GSC_PENDING`: CONNECT proxy вернул 403 до сайта, GSC недоступна |
| 09.2 | `CODE_VERIFIED` — каталог строится только из реальных Django entities и privacy-safe Ashdod supply | Реальное наполнение выполняется только утверждёнными данными |
| 09.3 | `CODE_VERIFIED` — локализованные landing pages, breadcrumbs, CTA и профили | Физические устройства и редакторская приёмка до public launch |
| 09.4 | `CODE_VERIFIED / DEFAULT_OFF` — sitemap, robots, canonical, hreflang, OG и правдивый JSON-LD | Включение индексации только отдельным owner GO |
| 09.5 | `MECHANISM_VERIFIED` — exact 301/308/404/410, approval, chain/open-redirect protection и rollback | `REAL_DECISIONS_PENDING_09.1`; все 21 seed rows остаются inactive review |
| 09.6 | `PREPARED` — staging, backup/restore, migrations, proxy, monitoring и rollback runbook | `PRODUCTION_CUTOVER_PENDING_OWNER_APPROVAL` |
| 09.7 | `CODE_VERIFIED / NO_REAL_CONTENT_PUBLISHED` — versioned editorial workflow и immutable history | Реальные материалы требуют отдельного human review/publish |

## Инвентаризация URL

- Всего строк: **21**, дубликатов: **0**.
- Кандидат `KEEP`: **1** (`/`), но HTTP/canonical/GSC не подтверждены.
- `REVIEW`: **20**.
- Финально утверждённые реальные `301/308/404/410`: **0**.
- Проверенные текущим сеансом origin HTTP-коды: **0** — запросы остановлены
  CONNECT proxy `403`, `http_status=000` не является ответом сайта.
- GSC clicks/impressions/index status: **UNKNOWN**. Требуемый экспорт описан в
  `docs/STAGE_09_URL_AUDIT.md`.

## Проверки

| Проверка | Результат |
|---|---|
| Полный Django suite | **660/660 PASS**, PostgreSQL 17, 70.391 s |
| Stage09 Django tests | **29/29 PASS** |
| Independent adversarial re-review | **PASS** на `d706ba9`; открытых CRITICAL/HIGH/MEDIUM/LOW нет |
| Clean migrations | **PASS**, все миграции применены с нуля |
| Stage08→Stage09 upgrade rehearsal | **PASS**; синтетические City/Category/User сохранены 1/1/1, seed legacy rows 21 |
| SEO rollback/reapply | **PASS**, `seo zero → latest`, затем `migrate --check` |
| Django check / migration drift | **PASS / no changes detected** |
| Ruff / compileall / pip check | **PASS / PASS / no broken requirements** |
| Production settings check | **PASS** без запуска production; W005/W021 оставлены owner-gated до проверки всех поддоменов |
| Docker Compose dev/staging/maintenance | **PASS**, контейнеры cutover не запускались |
| Chromium | **17/17 PASS**, RU/EN/HE, RTL, 320×568/390×844/768×900/1440×1000 |
| Chromium no-JS | **3/3 PASS** |
| Скриншоты | **6** синтетических responsive captures, просмотрены; физические устройства не запускались |
| Approved HTML SHA-256 | **4/4 MATCH**, эталоны не менялись |
| `git diff --check` | **PASS** |

## Дефекты независимого review

На исходном review SHA `6b8885a` подтверждены и затем исправлены:

1. `ZP-09-001` MEDIUM — изменённый текст наследовал старое approval и мог
   остаться опубликованным. Теперь substantive edit атомарно возвращает draft,
   снимает публикацию и очищает reviewer/quality metadata.
2. `ZP-09-002` MEDIUM — Django Admin обходил revision/CAS/review. Content admin
   сделан read-only, запись разрешена только через versioned workflow.
3. `ZP-09-003` MEDIUM — staff без SEO permissions мог открыть и изменить чужой
   draft. Добавлены явные view/change permissions в HTTP и service layers.
4. `ZP-09-004` MEDIUM — active legacy decision можно было изменить со старым
   approval. Активная конфигурация заблокирована до отдельной деактивации.
5. `ZP-09-005` MEDIUM — sitemap мог включить страницу, которую renderer пометил
   `noindex`. Supply/translation gates синхронизированы для service/city cases.
6. `ZP-09-006` LOW — новые public/editorial labels и statuses не были полностью
   локализованы. Добавлены и скомпилированы EN/HE catalogs и регрессии.

## Stage14 compatibility

Stage09 и Stage14 используют отдельные приложения, namespaces и цепочки
миграций. Будущий rebase PR Stage14 затронет общие `core/urls.py`, settings,
`base.html`, workflow и нормативные документы; это ожидаемая ручная интеграция,
а не разрешение копировать или активировать Stage14. Combined test остаётся
`PENDING_AFTER_REBASE`. Оба Stage09 runtime flags и все закрытые Stage14 flags
должны оставаться выключенными до своих owner GO.

## GitHub и ограничения среды

Все code commits отправлены в существующую ветку. `gh auth status` без token
environment сообщил отсутствие авторизации; GitHub API и публичный REST request
вернули 403 через network proxy. Поэтому этот сеанс не может достоверно создать
Draft PR, обновить его описание или прочитать результат Actions. Push workflow
настроен на `stage-*`, но его SUCCESS нельзя заявлять без доступного GitHub API.

Подготовленная ссылка для единственного Draft PR:
`https://github.com/maxim9362/zemiPro_site_django/compare/main...stage-09-django-seo?expand=1`.

## Не выполнялось

- merge, deployment и production cutover;
- DNS, Cloudflare, VPS, Nginx, SSL/TLS или production PostgreSQL изменения;
- отключение старого сайта;
- активация индексации, legacy redirects или Stage14 features;
- реальные статьи, мастера, отзывы, цены, метрики или пользовательские данные;
- GSC, физические Android/iPhone и screen-reader acceptance.

До отдельного owner GO итоговый release-гейт остаётся:
**`PRODUCTION_CUTOVER_PENDING_OWNER_APPROVAL`**.
