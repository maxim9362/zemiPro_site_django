# Stage 09.7 — редакционный процесс SEO-контента

Статус: `CODE_VERIFIED / NO_REAL_CONTENT_PUBLISHED`.

## Workflow

`brief → draft/review → approved → published → approved (unpublish)`

- Создание привязывает материал к существующей сущности Django-каталога и
  фиксирует автора, язык, тему, источники и тип landing page.
- Изменения используют optimistic CAS `expected_version` и PostgreSQL row lock.
  Каждая успешная операция сначала создаёт append-only revision snapshot.
- Автор видит/редактирует только свои материалы; staff видит очередь. Review и
  publish требуют отдельных Django permissions. Автор не может одобрить
  собственный материал.
- Публикация требует источников, отдельного staff reviewer, quality approval,
  минимально содержательных summary/meta/body и отсутствия текстового дубля.
- История защищена ORM и PostgreSQL trigger от `UPDATE`/`DELETE`; публичного
  delete endpoint нет. Unpublish сохраняет историю.
- Все editorial routes требуют login/permission/CSRF, закрыты `noindex` и не
  поддерживают небезопасные HTTP methods.

## Границы

Модель хранит только дополнительный текст посадочных страниц каталога. Она не
дублирует статьи/Q&A Stage 14 и не смешивает SEO-контент с заказами, отзывами или
рейтингом. Gemini/API не вызывается. AI может в будущем подготовить только
черновик вне publication path; факты и одобрение остаются человеческими.

Ни одного production-материала, автора, мастера, согласия или метрики не
создано. Synthetic fixtures существуют только в изолированной test DB.

## Проверки

- `apps.seo.tests`: 21/21 PASS на PostgreSQL 17.
- Полный UI workflow create/submit/review/publish/unpublish и 4 immutable
  revisions: PASS.
- Object permissions, separate reviewer, CSRF, unsupported methods, CAS stale
  write, thin-content/duplicate gates: PASS.
- Прямые SQL update/delete history: BLOCKED/PASS.
- Ruff, Django checks, migration drift: PASS.
