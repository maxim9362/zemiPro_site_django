# Stage 14 — техническая финальная приёмка

Дата локальной приёмки: 2026-11-15. Ветка: `stage-14-knowledge`.

## Вердикт по коду

Подэтапы 14.1–14.11 технически реализованы. Независимый локальный review
изменений после 14.11 завершён без открытых CRITICAL, HIGH или блокирующих
MEDIUM. Это не разрешение на merge, deployment или публичную активацию.

Все deployable-конфигурации сохраняют Stage 14 flags жёстко выключенными.
Только `core.config.stage14_browser`, недоступный через `DJANGO_ENV`, включает
их для изолированной синтетической browser-проверки.

## Закрытые замечания независимого review

| ID | Severity | Исправление |
|---|---|---|
| S14-R1 | MEDIUM | Голос и принятие ответа привязаны к публичному родительскому вопросу и live-публичному профилю автора; cross-question и archived/hidden IDOR закрыты. |
| S14-R2 | MEDIUM | Блокировка WorkerProfile ограничена `FOR UPDATE OF self`; взаимные рекомендации больше не создают deadlock на присоединённых User-строках. |
| S14-R3 | MEDIUM | Доменные CAS/PII-конфликты write views преобразуются в контролируемый HTTP 400 без частичных записей. |
| S14-R4 | MEDIUM | Ошибка необязательной invite attribution не откатывает уже созданный аккаунт и не препятствует входу. |
| S14-R5 | MEDIUM | Жалобы на личные рекомендации, recommendation requests и responses получили полную очередь и атомарное решение модератора. |
| S14-R6 | MEDIUM | Личные рекомендации выводятся отдельной маркированной секцией публичного профиля и не смешиваются с Rating. |
| S14-R7 | MEDIUM | `RecommendationResponseForm` больше не обращается к БД при импорте URL/form modules; production/staging deploy checks остаются DB-independent. |
| S14-R8 | LOW | Подписи форм и публичные действия request detail локализованы для RU/EN/HE. |

Независимая повторная проверка: 5/5 adversarial и 3/3 targeted PASS;
fingerprint проверенного diff сохранён вне репозитория в рабочем артефакте
Codex Cloud. После R7 отдельно прошли environment-settings и Stage14.10 tests.

## Локальные технические доказательства

- PostgreSQL 17: чистое применение `knowledge.0001–0008`, откат 0008→0003,
  сохранение синтетической legacy-статьи и повторное применение 0004–0008 —
  PASS; `migrate --check` и `makemigrations --check --dry-run` — PASS.
- Stage 14 knowledge tests: 130/130 PASS после review-fixes.
- Environment settings + Stage14.10 regression: 19/19 PASS.
- PostgreSQL concurrency: 20 параллельных aggregate increments дают одну
  строку и точный итог; взаимные рекомендации A↔B завершаются без deadlock.
- Chromium: 90/90 синтетических проверок RU/EN/HE, Hebrew RTL, ширины
  320/390/768/1440, 320×568 без JavaScript, отдельные screenshots при 390 px,
  safe profile/share и отсутствие private-email leakage — PASS. Это desktop
  Chromium emulation, не физические Android/iPhone.
- Ruff, compileall и `git diff --check` — PASS на локальном финальном diff.
- Полный Django suite: **761/761 PASS** на финальном локальном diff после R7.
  GitHub Actions фиксируется отдельно на итоговом commit/PR; промежуточный
  запуск обнаружил и привёл к исправлению R7, поэтому его FAIL не считается
  приёмкой финального diff.

## Неизменяемые границы

- Реальный пилот 14.4, реальные согласия, материалы, метрики и решение
  GO/NO-GO не проводились и остаются `PENDING`.
- Q&A, статьи, личные рекомендации, «Посоветуйте мастера» и приглашения не
  включены публично. Для каждого выпуска требуется отдельное решение владельца.
- Статьи, вопросы, рекомендации и invitation analytics не создают Order,
  Offer, Rating, оплату или подтверждённую репутацию.
- Production/VPS/DNS/Cloudflare/рабочая PostgreSQL не изменялись; deployment и
  merge не выполнялись; этап 09 не начинался.
- До публичного запуска остаются ручная редактура Hebrew и регулируемого
  контента, физические Android/iPhone, screen reader, реальные процедуры
  модерации/retention и эксплуатационный backup/restore rehearsal.
