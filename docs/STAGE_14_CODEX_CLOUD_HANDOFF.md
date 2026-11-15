# ZemiPro — Stage 14: Codex Cloud handoff / единая точка входа

> **Дата:** 2026-11-15. **Репозиторий:** `maxim9362/zemiPro_site_django`.
> **Текущая рабочая ветка:** `stage-14-knowledge`; проверенная документационная HEAD до этого handoff: `62ce5343d69645971a4c13713ba75d7f75f489b1`.
> **Текущий `main`:** `3d640f66a3acc61bec623bd9e31786ae63b7196b` на момент передачи.
> **Основание:** новая прямая команда владельца: **передать остаток Stage14 целиком в Codex Cloud**. Это узкое исключение из разделения ChatGPT→Codex в `AGENTS.md`: Codex **пишет и проверяет код** всех 14.5–14.11, не только делает итоговое review. Другие этапы, правила безопасности и гейты запуска не изменяются.
> **PR для Stage14 на момент передачи:** отсутствует. **Одна ветка `stage-14-knowledge`, один итоговый PR в `main` после всех подэтапов, никаких промежуточных PR/merge.**

## 0. Инструкция чтения (по порядку)

1. `AGENTS.md` — обязательные правила, особенно Stage14 exception, безопасность, scope, Git/CI и правила release.
2. **Этот документ** — актуальная последовательность, уже реализованное и запреты.
3. `docs/ROADMAP.md` **только блок Stage14**, `docs/DEVELOPMENT_PLAN.md` **только 14.5–14.11**, `docs/TECHNICAL_SPEC.md` **REQ-KNOW-001–023**, `REQ-SEC-003–006`, `REQ-I18N-001–006` и затрагиваемые `REQ-SEO`.
4. Специализированные проверенные контракты: `docs/STAGE_14_DOMAIN_MODEL.md`, `docs/STAGE_14_ARTICLE_MODERATION.md`, `docs/STAGE_14_PUBLIC_ARTICLES.md`, `docs/STAGE_14_PILOT_PLAN.md`.
5. `docs/FRONTEND_DESIGN_BASELINE.md`, `docs/frontend/approved/` (4 **неизменяемых** HTML); затем только нужные `zemipro_web/apps/knowledge/`, `accounts/`, `marketplace/`, `moderation/`, `core/`, Django templates/CI. Сверяй live git вместо полагаться на устаревший текст.

Не трать контекст на полный перечитывание истории/Fonbet/старого PSEO. Не делай ложных утверждений о просмотренных/неоткрытых файлах.

## 1. Текущее состояние и точная доказательная база

| Подэтап | Фактический статус к моменту handoff | Проверенные доказательства |
|---|---|---|
| 14.1 — модели статей и границы домена | `CODE_CI_VERIFIED` | code `a5a9f711bfe17dc6c8f05de711fd411254f34cd3`; [CI #43686166201](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43686166201), 6/6 target, 637/637 Django |
| 14.2 — редактор и модерация | `CODE_CI_VERIFIED` | code `21daf56d83c34fe108b09de20cc6afac95473a6b`; [CI #43689847639](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43689847639), 27/27 target, 664/664 Django |
| 14.3 — публичные статьи и SEO metadata | `CODE_CI_VERIFIED`, публикация OFF | code `83bb874276ccbfb3d645163dd66693852b1e66d2`; [CI #43693188715](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43693188715), 22/22 target, 686/686 Django |
| 14.4 — технический контур пилота | **`CODE_CI_VERIFIED`**, **реальный пилот/решение Q&A = PENDING** | code `8d02ed58eed68cdce09b83c9648e36f9d398973b`; [CI #43702478915](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43702478915), **21/21** target, **707/707** Django, **40/40** steps. Markdown-only HEAD `62ce5343...` также [CI #43703408409](https://github.com/maxim9362/zemiPro_site_django/actions/runs/43703408409) success 40/40 |
| 14.5–14.11 | **`NOT_STARTED`** | После новой команды владельца разработать и проверить **все семь последовательно** |

- Репозиторий **Django 5.2 LTS, Python 3.12, PostgreSQL 17, Docker Compose, server-rendered Django/HTMX/templates**; RU/EN/HE, Hebrew RTL. Пилот и авторы **только Ашдод**. Технический справочник других городов не разрешает их публикацию.
- Stage07/Stage08 и 4 HTML-baseline уже MERGED в `main`. **Stage09 SEO/public migration НЕ НАЧИНАЛСЯ** и этой задачей не разрешён.
- Все `Stage14` flags в `zemipro_web/core/config/base.py` сейчас **False** и не переключаются через .env. `ZEMIPRO_KNOWLEDGE_ARTICLES_ENABLED`, `ZEMIPRO_KNOWLEDGE_AUTHORING_ENABLED`, `ZEMIPRO_KNOWLEDGE_PILOT_METRICS_ENABLED`, `ZEMIPRO_KNOWLEDGE_QA_ENABLED`, `ZEMIPRO_PERSONAL_RECOMMENDATIONS_ENABLED`, `ZEMIPRO_RECOMMENDATION_REQUESTS_ENABLED`. При реализации новых фич — отдельные **fail-closed**, owner-controlled feature flags; никакой активации только потому, что тесты зелёные.
- **Ни одного настоящего участника/согласия/жалобы/просмотра/заказа пилота 14.4 не подтверждено; Q&A owner `GO/NO-GO=PENDING`.** Не симулировать доказательства, не ставить 14.4 полное `DONE`, не приписывать синтетическим тестам реальные метрики.

## 2. Существующий код, который надо сохранять/переиспользовать

- `zemipro_web/apps/knowledge/models.py`: `ExpertArticle`, `ExpertArticleRevision`, `ExpertArticleImage`, `ExpertArticleDecision`, `ExpertArticleReport`, `ArticlePilotEnrollment`, `ArticlePilotSelection`, `ArticlePilotAudit`, `ArticlePilotDailyMetric`, `ArticlePilotOrderAttribution`. Миграции `0001_initial`, `0002_stage14_article_moderation`, `0003_pilot_observation`.
- `knowledge/services.py`, `access.py`, `forms.py`, `views.py` — черновики, optimistic locking, правомерное авторство, приватные media, отчёты/решения модератора. `accounts/public_text.py` + `accounts/public_snapshot_v1.py` — действующая нормализация/anti-PII. Не создавать параллельный PII/рейтинг-контур без причин.
- `knowledge/public_content.py` — единый **fail-closed** публичный queryset: версия снимка, решение модератора, Ashdod, живой публичный профиль, активная категория, **реальное согласие автора + whitelist пилота**. Из всех новых публичных endpoints использовать такой же gate.
- `knowledge/public_views.py`, `public_urls.py`, `public_search.py`, `public_seo.py` — маршруты `/{ru|en|he}/advice/`, article detail, одобренные JPEG, canonical/hreflang/Article JSON-LD с `noindex` до Stage09. Изолированно изменять для новых сценариев, не переписывать PSEO.
- `knowledge/pilot_services.py`, `pilot_metrics.py`, `pilot_views.py`, `pilot_forms.py` — согласия, whitelist, контроль нагрузки, server-side session переходов, агрегаты без PII, HMAC подтверждённых `Order.PUBLISHED` (не приравнивать просмотры/клики к реальным заявкам). Мастер вправе отозвать согласие после блокировки публикации, модератор — снять статью при выключенном редакторе. Не делать аналитические потери причиной сбоя заказа.
- `marketplace.Order`, `Response`, `Rating`, `ServiceQuestionnaire` **не являются** статьями/вопросами/рекомендациями; использовать только ссылку на штатный workflow `marketplace:order_wizard_start`. Не переписывать этапы 04–08 и не смешивать помощь/вопросы с коммерческими откликами.
- `apps.accounts.client_favorites.public_worker_queryset()`, `WorkerProfile`, `Category`, `Subcategory`, `moderation` — серверная фильтрация уже проверенных сущностей. `core.middleware` содержит PostgreSQL `SensitivePostCounter` для ограничений. Права и CSRF проверяются на сервере независимо от скрытых кнопок.
- Публичные производные Django templates в `zemipro_web/templates/pages/`, `templates/knowledge/`, статика `zemipro_web/static/css/`; четыре `docs/frontend/approved/*.html` **не менять**.

## 3. Что Codex должен сделать: 14.5 → 14.11, строго последовательно

**Одна команда владельца разрешает все перечисленные подэтапы до конца без ожидания семи отдельных «Дальше».** После каждого подэтапа — узкая реализация, адресные проверки, запись в ROADMAP/PROGRESS, коммит/пуш **в ту же** `stage-14-knowledge`. Полный независимый аудит и полная регрессия — в конце после 14.11, кроме критических рисков.

| Этап | Задача, минимальная приёмка, запрет |
|---|---|
| **14.5** | Спроектировать и реализовать независимые от `Order` `ExpertQuestion`, `ExpertAnswer`, ревизии/модерацию/жалобы, `HelpfulVote`. Вопрос задаёт активный зарегистрированный пользователь, отвечают активные опубликованные специалисты Ашдода, запись server-authorized, авторский ownership, статусы `draft/pending/published/rejected/archived` либо документированный безопасный эквивалент, immutable/moderated public snapshots, anti-PII/anti-spam/rate-limit/duplicate/idempotency, safe media. Голоса устойчивы к накрутке и повторам, автор вопроса может выбирать полезный ответ строго по полномочиям. **Никаких бюджета/платных откликов/контактов/автоматического заказа.** |
| **14.6** | Полноценный Django UI Q&A (спросить/найти/отвечать/полезный ответ/жалоба/модерация), публичный список/поиск/категории/деталь/ссылки на реально опубликованные профили и явное создание отдельной заявки; RU/EN/HE + RTL, responsive, keyboard/a11y, safety copy. Только проверенные snapshots, фильтры public availability и выключенный `ZEMIPRO_KNOWLEDGE_QA_ENABLED` по умолчанию. Никогда не повышать `Rating` по ответам; `noindex` до разрешённого SEO Stage09. |
| **14.7** | Сквозные security/concurrency/E2E на Stage14; synthetic PostgreSQL17 migrations apply/reverse where safe, browser mobile HE/RU/EN, object permissions, CSRF, IDOR, XSS, Unicode/URI PII, raw vs public snapshot, complaint/takedown, votes abuse, order-path and privacy. Подготовить контролируемый **owner-authorized** release/kill switch, smoke + rollback + retention/privacy/audit plan; агрегаты `article_view`, `question_view`, `profile_click`, `order_started` не должны хранить visitor PII или подменять реальные заказы. **НЕ включать** Q&A/статьи/analytics и не проводить реальный staging/production deploy без отдельного GO. |
| **14.8** | Личная рекомендация о **собственном опыте вне ZemiPro**, отдельная сущность и UI-блок от `Rating`. Автор — реальный пользователь; self-recommendation/conflict/дубли антифрод, права, согласие, report/takedown, anti-PII, moderation. Публичная метка «со слов пользователя / вне ZemiPro / не подтверждено платформой» на RU/EN/HE. Никаких изменений `Rating`, агрегированного проверенного рейтинга или статистики выполненных заказов. |
| **14.9** | Кнопки «Поделиться профилем в Facebook» + «Скопировать ссылку»: только **публичный безопасный URL** опубликованного WorkerProfile и безопасный preview/OG без PII. Реальное действие пользователя, без автопостинга, Meta API/Facebook Login/импорта друзей. Нормальный fallback без установленного приложения, безопасные открытия/clipboard, RU/EN/HE/RTL/mobile tests. |
| **14.10** | Изолированный «Посоветуйте мастера»: вопрос-рекомендация **не Q&A и не Order**; активный пользователь, категория, Ashdod-only, безопасное описание, ответы с личным опытом и только реально публичными специалистами, явные ссылки и обычная заявка. Anti-fraud/self-advertising/duplicates/rate-limits, moderation/report/history/PII safe, RU/EN/HE RTL, closed flag by default. **Public rollout только после доказанного спроса + отдельного owner GO**, в отсутствие — `PENDING`, но код реализовать. |
| **14.11** | «Пригласить мастера» означает **внешнего, ещё не зарегистрированного человека**: добровольно скопировать/поделиться ссылкой **самостоятельной** регистрации по выбранному каналу, включая Facebook/Messenger, без чтения адресной книги, автоматических сообщений, массового спама, создания профиля за третье лицо. Строго отделить от `marketplace` приглашения **уже зарегистрированного** мастера на заказ (Stage05). RU/EN/HE RTL/mobile; безопасный URL и атрибуция только ограниченными обезличенными агрегатами, без fake registrations/conversions. |

Для каждого подэтапа: **слои Django models/migrations → services/permissions → forms/views/URLs/templates → адресные тесты → документация**. Выбирай разумные узкие файлы, проверяй действующие conventions и не делай несвязанных архитектурных переработок. Промежуточные SHA и результаты указывай буквально, не выдумывай.

## 4. Обязательные инварианты безопасности и гейты

1. **Только Ашдод** (hardcoded pilot boundary, server-side) для специалистов/услуг/публичных запросов; `User.is_active`, `is_blocked`, `email_verification_required`, опубликованный `WorkerProfile`, текущая категория/навыки должны проверяться по БД на каждом публичном чтении и изменении.
2. **Безопасный snapshot + модераторское решение** для любого user-generated public text; draft/detail не раскрывать по угаданному ID. Проверять контакты, URL, Unicode-подмену, HTML/XSS, приватные имена, опасные советы и чужие медиа. Редакционная проверка реальных материалов/лицензий остаётся ручным гейтом.
3. **Ownership + блокировки + permission** на любом POST/GET private/moderation/media, CSRF, transaction.atomic/optimistic version/unique constraints/race, rate-limit PG. Нет свободного изменения чужих материалов или self-moderation.
4. **Флаги на старте False**: можно реализовать технические закрытые flows через `override_settings` и synthetic fixtures. Нельзя включать public Q&A или «Посоветуйте мастера» на сайте без доказанного `GO`, при `NO-GO` — OFF. Аналитический/Pilot owner GO не создаётся из кода и не имитируется.
5. **Никаких реальных действий** без отдельного согласия: merge, live deploy, staging с реальными данными, изменения DNS/Cloudflare, VPS, боевых secrets, платежи, Facebook posting, импорт настоящих контактов, изменение production БД, изменение старого публичного SEO/Stage09.
6. Сохранить внешний gating Stage14.4 `PILOT_PENDING`. Кодовая часть может стать `CODE_CI_VERIFIED`, но реальный пилот / owner Q&A decision / реальный спрос и рекомендационный GO — `PENDING` и **препятствуют безоговорочному Stage14 `DONE`**. Не пытаться «закрыть» это синтетическими данными.
7. 4 исходных approved HTML неизменяемые; Django derived templates можно корректировать минимально ради реальных URL/права/RTL/UX. Не использовать старый Telegram/Flask PSEO или фиктивные отзывы.

## 5. Верификация Codex Cloud и итоговый PR

Делать финальную **независимую** ревизию после всех 14.5–14.11: security, архитектура, данные/приватность, гонки, обратимость миграций, локали/RTL, broken links/SEO/OG, экраны и реальные тестовые браузеры. Исправлять найденные `CRITICAL/HIGH/MEDIUM` в **этой же ветке**, повторять адресные и полный suite на финальном SHA. Указывать `SKIP/NOT_RUN` для недоступных проверок; не писать PASS без логов.

Минимальные команды в изолированной среде Codex (настройки БД/секреты брать из штатных безопасных test CI, не из production):

```bash
cd zemipro_web
python -m compileall -q apps core manage.py
python -m ruff check apps core manage.py
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test apps.knowledge.tests
python manage.py test
```

Проверить `.github/workflows/django-ci.yml` на финальном SHA: isolated PostgreSQL17, migrations, full Django, browser smoke/RTL Stage02/06/07/08 + новые Stage14 targeted тесты. Проверить, что rollback миграций делается **только** в пустой CI-БД; никаких откатов реальной БД. Записать exact SHA, CI run URL, количество тестов, ошибки/фиксы и незакрытые ручные gates.

**PR:** если существующего Stage14 PR нет, открыть **один** итоговый **Draft PR из `stage-14-knowledge` в `main`**, только после завершения кодовых подэтапов и независимого Codex review. Если интерфейс Cloud запрещает создание/обновление PR — сохранить код/документы в той же ветке, дать точную ссылку/описание/ошибку, не создавать дубли. Не нажимать merge и не деплоить без отдельного прямого разрешения владельца. Ни один собственный тест не заменяет review.

## 6. Отчёт и правила продолжения

- **Не спрашивать после каждого 14.5–14.11 «Дальше»**: новая команда разрешает всю перечисленную реализацию последовательно. Не перескакивать через подэтап без документации/адресных проверок.
- После каждого коммита кратко вести `docs/PROGRESS.md` и Stage14-строки `docs/ROADMAP.md`; статус `CODE_IMPLEMENTED` и `CI_VERIFIED` присваивать только по факту. Прогресс хранить в Git, чтобы другой сеанс Codex возобновился без переписывания контекста.
- В конце выдать: последовательность 14.5–14.11 и статусы, SHA, PR, changed files/migrations, тесты на финальном SHA, security findings, реальные блокеры и открытые owner GO. **Остановиться перед merge/deploy/activation.**
- Владелец просит **технически закончить остаток Stage14**. Если недоступен live pilot 14.4, работа не блокируется: пометить внешний гейт `PENDING` и закончить весь новый код в выключенном состоянии.

**Источник истины — live Git branch и подтверждённые тесты; этот handoff — навигация, а не замена просмотра исходников.**
