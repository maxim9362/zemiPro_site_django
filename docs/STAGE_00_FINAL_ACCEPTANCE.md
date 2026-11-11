# ZemiPro — этап 00: итоговая приёмка после независимого аудита

**Дата:** 2026-11-11
**Ветка:** `stage-00-audit`
**Исходный проверенный commit:** `94526454ff0b1102e038f5a74ab5aeb3d3be67f9`
**Статус этапа:** `BLOCKED / OWNER_ACTION_REQUIRED`
**Production, VPS, DNS, Cloudflare, реальные базы и секреты:** `NOT_TOUCHED`

## Неизменные решения

- Единственная кодовая база — этот Django-репозиторий; единственная транзакционная БД каждого окружения — PostgreSQL.
- Telegram исключён. Удалённый PSEO, Flask, SQLite, генераторы, тексты и старые базы не импортируются и не восстанавливаются.
- Из прежнего сайта сохраняется только проверяемый список публичных URL для решений этапа 08.
- Заявку создаёт и изменяет только зарегистрированный и авторизованный пользователь; публичный каталог доступен гостю.
- Адреса, телефоны и приватные сообщения не публикуются.
- Все 14 этапов и 96 подэтапов обязательны. Этап 13 обязателен для общего `DONE`; публичная активация Q&A и отдельных рекомендаций требует отдельного `GO`.

## Состояние 00.1–00.6

| Подэтап | Статус | Доказательство | Осталось |
| --- | --- | --- | --- |
| 00.1 Инвентаризация | `DONE / INDEPENDENTLY_VERIFIED` | Проверено полное дерево и runtime; активных Telegram/PSEO-зависимостей нет; матрица обновлена | Исторические сведения хранить только как историю |
| 00.2 Секреты | `BLOCKED / OWNER_ROTATION_REQUIRED` | Текущее дерево не содержит отслеживаемых secret-файлов; historical scan требует review | Подтверждение отзывов у провайдеров |
| 00.3 PostgreSQL | `READY_FOR_OWNER_ACTION / SYNTHETIC_RESTORE_PASS` | PostgreSQL 17.11: 27 миграций, 8 категорий, 56 подкатегорий, 25 городов совпали до/после restore | Владелец подтверждает наличие ценной Django DB/media; при наличии разрешает backup изолированной копии |
| 00.4 Legacy URL | `READY_FOR_OWNER_ACTION / HTTP_GSC_UNVERIFIED` | 21 строка, 21 уникальный HTTPS URL, структура корректна, target URL пусты | HTTP/canonical/sitemap/GSC; все 21 решения выполняются в этапе 08 |
| 00.5 Архитектура | `DONE / DOCUMENTED` | ADR и нормативные документы согласованы с Django-only, PostgreSQL, auth-only orders и запретом legacy import | HIGH-дефекты закреплены за будущими этапами |
| 00.6 Диагностика | `READY_FOR_OWNER_ACTION / CORE_CHECKS_PASS` | 17/17 Django, 12/12 tools, checks, migrations, Git и synthetic restore PASS | Docker build не подтверждён из-за Cloud TLS proxy; итоговая приёмка после внешних блокеров |

Этап 00 нельзя объявлять `DONE`, пока обязательные действия 00.2–00.4 не приняты владельцем и итоговый этапный PR не прошёл review.

## Действия владельца по 00.2

Значения секретов не проверять через внешние API и не размещать в issue/PR:

1. Отозвать старый пароль SOCKS5 и подтвердить, что приложения от него не зависят.
2. Отозвать старые Gemini API keys.
3. Удалить/отозвать старый Google Service Account key и проверить audit log провайдера, если доступен.
4. Отозвать старые Telegram Bot API tokens при наличии.
5. Подтвердить отсутствие runtime-зависимости ZemiPro от всех перечисленных credentials.

Удаление файлов или репозитория не считается отзывом. Историю Git не переписывать и force-push не выполнять без отдельного плана владельца.

## Матрица согласования PR #5

PR #5 `docs/all-stages-required-v1.3-20261110` изменяет пять файлов и основан на общем предке текущей ветки. Его продуктовые решения сохранены в этой ветке вручную.

| Файл | Изменение PR #5 | Изменения этапа 00 | Безопасное разрешение |
| --- | --- | --- | --- |
| `AGENTS.md` | v1.3, обязательные 00–13/96 | Django-only, запрет анонимных заявок, правила legacy и security | Сохранить v1.3 и все уточнения этапа 00; не брать файл целиком из PR #5 |
| `docs/DEVELOPMENT_PLAN.md` | Этап 13 обязателен, rollout под GO | Удалены гостевые заказы и перенос PSEO/Telegram; обновлены источники | Объединить смысловые изменения; текущая ветка уже содержит оба набора |
| `docs/PROGRESS.md` | Запись о v1.3 | Полные доказательства независимого аудита и реальные статусы 00.1–00.6 | Сохранить подробную запись этапа 00, добавить историю v1.3 один раз |
| `docs/ROADMAP.md` | Этап 13 `NOT_STARTED`, все подэтапы обязательны | Фактические статусы этапа 00, 96 подэтапов, Django SEO вместо переноса PSEO | Использовать текущую редакцию; она включает v1.3 и новые доказательства |
| `docs/TECHNICAL_SPEC.md` | Обязательность этапа 13 | Auth-only orders, запрет legacy import, результаты решений владельца | Использовать текущую редакцию с v1.3 и исправленным QA-сценарием |

**Рекомендуемый порядок:** не объединять PR #5 в текущем виде поверх `stage-00-audit`. Сначала проверить, что итоговый PR этапа 00 полностью содержит продуктовые требования PR #5. После принятия этапа 00 PR #5 следует rebase на новый `main`: если semantic diff пуст, закрыть его как superseded; если процесс требует отдельного принятия PR #5, сначала объединить его, затем обновить `stage-00-audit` из `main` и вручную сохранить фактические статусы/доказательства этапа 00. Автоматическое разрешение конфликтов выбором одной стороны небезопасно.

## Реестр проблем независимого аудита

`Подтверждение`: `CONFIRMED` — воспроизведено или доказано кодом; `RISK` — требует внешнего подтверждения.

| ID | Приоритет | Подтверждение | Этап | Блокирует 00 | Блокирует production | Статус |
| --- | --- | --- | --- | --- | --- | --- |
| AUD-SEC-001 historical credential | CRITICAL | CONFIRMED path/marker; validity unknown | 00.2 | **Да** | **Да** | OWNER_ROTATION_REQUIRED |
| AUD-CFG-001 EOL/unpinned dependencies | HIGH | CONFIRMED | 01.1/01.3 | Нет | **Да** | OPEN |
| AUD-SEC-002 `is_staff` раскрывает PII | HIGH | CONFIRMED | 03.6/04.3/07.5 | Нет | **Да** | OPEN |
| AUD-SEC-003 blocked worker profile public | HIGH | CONFIRMED HTTP 200 | 03.6/05.5/07.5 | Нет | **Да** | OPEN |
| AUD-UI-001 blank category names | HIGH | CONFIRMED | 02.3/02.5 | Нет | Да, functional | OPEN |
| AUD-DATA-001 rating integrity | HIGH | CONFIRMED | 07.4/10.3 | Нет | **Да** | OPEN |
| AUD-INF-001 deployment Compose | HIGH | CONFIRMED | 01.4/01.5 | Нет | **Да** | OPEN |
| AUD-DOC-001 normative contradictions | HIGH | CONFIRMED | 00.5 | Нет | Нет | RESOLVED_IN_BRANCH |
| AUD-UI-002 missing subcategory endpoint | MEDIUM | CONFIRMED 404 | 02.5/04.2 | Нет | Да, functional | OPEN |
| AUD-AUTH-001 logout GET 405 | MEDIUM | CONFIRMED | 03.2 | Нет | Нет | OPEN |
| AUD-ORDER-001 response race handling | MEDIUM | CONFIRMED by code | 06.1/06.6 | Нет | Да | OPEN |
| AUD-ORDER-002 incomplete status guards | MEDIUM | CONFIRMED by code | 04.1/06.5 | Нет | Да | OPEN |
| AUD-EVENT-001 notification atomicity | MEDIUM | CONFIRMED by code | 04.7/07.3 | Нет | Да | OPEN |
| AUD-MOD-001 complaint target rules | MEDIUM | CONFIRMED by code | 07.5 | Нет | **Да** | OPEN |
| AUD-ABUSE-001 missing throttling | MEDIUM | CONFIRMED by code | 03/04/06/07 | Нет | **Да** | OPEN |
| AUD-PERF-001 N+1/null ordering | MEDIUM | CONFIRMED by code | 01.6/05 | Нет | Нет | OPEN |
| AUD-I18N-001 RU hardcode/no RTL | MEDIUM | CONFIRMED | 02.3–02.6 | Нет | Да, launch scope | OPEN |
| AUD-MIG-001 real DB owner state | MEDIUM | RISK | 00.3/01.2 | Условно | **Да** | OWNER_CONFIRMATION_REQUIRED |
| AUD-SEC-004 history scan coverage | MEDIUM | CONFIRMED limitation | 00.2 | Через SEC-001 | Да | OPEN |
| AUD-XSS-001 future `innerHTML` pattern | LOW | CONFIRMED, endpoint absent | 04.2 | Нет | Нет сейчас | OPEN |

## Production blockers

До production необходимо закрыть как минимум: `AUD-SEC-001`, `AUD-CFG-001`, `AUD-SEC-002`, `AUD-SEC-003`, `AUD-DATA-001`, `AUD-INF-001`, `AUD-MOD-001`, `AUD-ABUSE-001`; подтвердить `AUD-MIG-001`; завершить RU/EN/HE/RTL и backup/rollback. Наличие назначения на будущий этап не снимает риск.

## Решение о готовности PR

Документальная и диагностическая часть доступной работы этапа 00 готова к review. Итоговый PR **не следует открывать как завершённый этап**, пока владелец не зафиксирует действия по 00.2, решение по возможной Django DB/media и способ получения HTTP/GSC-данных либо явное принятие их статуса `UNVERIFIED`. Merge и deployment требуют отдельного разрешения.

## Решение владельца 2026-11-11: новые ключи только по необходимости

- Используем новую чистую PostgreSQL для Django; **не переносим** данные/секреты старого Telegram/PSEO. Существующие БД/тома на сервере **не удалять автоматически**. Synthetic backup/restore уже PASS; backup/restore новых рабочих данных требуется настроить до production.
- Старые Telegram, Gemini, Google Service Account и SOCKS5 credentials исключены из целевого Django; старый PSEO GitHub удалён. Новые секреты создаём позднее только под конкретные нужные интеграции и сохраняем вне Git. Собственные `DJANGO_SECRET_KEY` и `DB_PASSWORD` для нового Django остаются обязательными (с новыми значениями).
- Владелец **берёт на себя последующий отзыв** старых credentials у провайдеров. На дату записи их действительность неизвестна; удаление файлов из HEAD не аннулирует ключи и не стирает историю Git. Поэтому `00.2 = BLOCKED / OWNER_REVOCATION_DEFERRED`, а production с незакрытым риском **запрещён**.
- Этот статус **не блокирует** продолжение чисто локальной/облачной разработки, проверки кода и подготовку PR. Он **блокирует** заявление об устранении риска, итоговый `DONE` этапа 00 по действующему гейту и выпуск production до подтверждённого отзыва либо отдельного безопасного закрытия риска.
- После отзывов владелец сообщает только сервис и факт отзыва (без самих ключей). Историю Git переписывать лишь по отдельному решению и плану, без автоматического force-push.
