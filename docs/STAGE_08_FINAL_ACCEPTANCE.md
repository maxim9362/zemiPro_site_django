# Stage 08 — финальная техническая приёмка Codex (2026-11-14)

Статус: `LOCALLY_VERIFIED / INDEPENDENT_REVIEW_PASS / PR_DRAFT / NOT_MERGED / NOT_DEPLOYED`.
Ветка: `stage-08-frontend`, единственный PR #17; временная база —
`stage-07-chat-notifications-moderation`, PR #16 Draft, NOT_MERGED.
Исходный SHA аудита: `ca965b3dfe8eb2e36e455b152192454b1084af5e`.
Base Stage07: `8ab5839f4c633dd58f13bb84e6417b8ef11abc72`.
Main: `576ef639e1b5944e333ac2829d47e16f51aa82a0`, не изменялся.

## Повторная проверка прошлых замечаний

- ZP-08-001 MEDIUM: canonical `Order.price` сохраняется как `Договорная`,
  preview локализуется отдельно. Проверено unit/integration и реальным
  Stage08.7 wizard→publish с проверкой PostgreSQL для RU/EN/HE.
- ZP-08-002 MEDIUM: no-JS header имеет static positioning на 320×568;
  прокрутка и доступность submit проверены Chromium, старый порог сохранён.

## Новые находки и исправления

| ID | Severity | Воспроизведение / причина | Исправление |
|---|---|---|---|
| ZP-08-003 | MEDIUM | Без JS initial required subcategory пуст; браузер блокирует POST выбранной category, список услуг не загружается | Отдельная noscript кнопка Load services с formnovalidate. Серверные required, token, CSRF и owner guards сохранены. Browser реально выполняет category POST → service POST → draft; Django regression проверяет отсутствие Order при невалидном POST |
| ZP-08-004 | MEDIUM | После 15 сообщений quota rejection возвращает пустой textarea, теряется текст 16-го сообщения | Только шаблон: escaped request.POST.body сохраняется в textarea. Regression подтверждает сохранение XSS-shaped ввода и отсутствие 16-й записи |
| ZP-08-005 | LOW | ROADMAP считает реализованный 08.7 не начатым | Актуализированы ROADMAP/PROGRESS и этот документ; исторические записи сохранены |

Новые backend операции, изменения сервисов/квот Stage07, миграции и зависимости
не добавлялись. Runtime fixes ограничены двумя шаблонами Stage08.

## Проверенные подэтапы

| Подэтап | Результат / доказательства |
|---|---|
| 08.1 | UX-карта и роли сверены с фактическими Django URLs/templates |
| 08.2 | Общая дизайн-система, компоненты, keyboard focus и семантика; source/HTTP/browser tests |
| 08.3 | Каталог, поиск, профили, privacy, Ashdod-only, пустые состояния и фильтры |
| 08.4 | Auth UI, кабинеты, восемь wizard шагов, back/save, canonical budget, offers/assignment |
| 08.5 | Chat/read/poll/upload, opt-in translation UI, notices, review/reply, reports/moderation; server permissions неизменны |
| 08.6 | 213 Chromium checks: RU/EN/HE/RTL, 320/390/768/1440, short no-JS 568, text 200%, keyboard |
| 08.7 | 47 browser milestones по ролям; фактические HTTP/CSRF и PostgreSQL состояния |

## Проверки и доказательства

- Исходный полный suite: 629/629 PASS; окончательный после исправлений:
  **631/631 PASS, failures/skips 0/0**, адресные 13/13 PASS.
  Финальные remote Actions проверяются по точному SHA и приводятся в handoff.
- Две новые Django-регрессии и расширение существующего browser no-JS сценария;
  прежние тесты и thresholds не удалены и не снижены.
- Chromium: Stage02 90/90, Stage06 18/18, Stage07 39/39,
  Stage08.6 213/213, Stage08.7 47/47. Артефакты сохранены вне репозитория.
- Изолированная PostgreSQL 17: clean migrations, check,
  makemigrations --check --dry-run, migrate --check; Ruff/compileall/Compose.
- Production settings проверены без deployment и production connection:
  нет ошибок; W005/W021 остаются существующими предупреждениями HSTS
  subdomains/preload. Эти политики не включались вслепую.
- Coverage gate marketplace/services.py: 89.6%, не покрытие всего проекта.

Отдельный reviewer не менял код и независимо воспроизвёл оба новых MEDIUM.
Независимое повторное review завершено: **PASS**, открытых blockers нет.
Reviewer независимо подтвердил оба fixes через Chromium и PostgreSQL;
исходные canonical price и header fixes перепроверены. Отчёт и SHA256
проверенных файлов сохранены в audit evidence. Общий финальный verdict
дополнительно требует remote Actions SUCCESS на последнем SHA.

## Ограничения и приёмка владельцем

Chromium emulation не является физическим Android/iPhone, iOS Safari,
VoiceOver/TalkBack или формальной WCAG certification. Эти ручные pre-release
гейты остаются открыты. Live OAuth, SMTP, SMS и Gemini не вызывались.

GitHub GraphQL в текущей среде отвечает `Forbidden`; публичные PR discussions
прочитаны, включая прошлые замечания и ca965b3, но полнота скрытых review threads
не подтверждена. Описание PR обновляется только при доступном штатном API.

PR #17 зависит от не объединённого PR #16; смена базы и новая проверка интеграции
после отдельно разрешённого merge Stage07 остаются будущим гейтом.
PR #16/#17, main и production не изменялись этой задачей вне push в Stage08.
Merge/deployment не разрешены. Финальные Actions должны быть SUCCESS именно
на последнем SHA, включая документацию; ссылки — в финальном отчёте.
