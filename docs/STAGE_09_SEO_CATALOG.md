# Stage 09.2 — Django SEO-каталог

Статус: `CODE_VERIFIED` в изолированной PostgreSQL 17.

## Реализация

- Источник истины сохранён: `ServiceSection`, `Category`, `Subcategory`, `City`
  и privacy-safe `WorkerProfile` из действующей Django БД.
- `apps.seo.catalog.service_workers()` возвращает только опубликованные,
  незаблокированные, прошедшие публичный snapshot профили, которые явно указали
  конкретную услугу и действительно обслуживают разрешённый город.
- География закрывается серверным `ZEMIPRO_PILOT_CITY_SLUG='ashdod'`.
- Добавлены модели точного legacy-реестра и редакционного контента посадочных
  страниц. Никакие URL-решения не активны по умолчанию.
- Контент посадочных страниц отделён от статей/Q&A Stage 14: он может быть
  связан только с реальной сущностью каталога, имеет язык, источники фактов,
  CAS-версию, reviewer, статус и append-only историю.
- PostgreSQL constraints защищают уникальность/состояния, а trigger запрещает
  `UPDATE`/`DELETE` истории даже прямым SQL.

## Проверки

- `apps.seo.tests`: 8/8 PASS.
- Чистое применение `seo.0001`/`seo.0002` в PostgreSQL 17: PASS.
- `makemigrations --check --dry-run`: PASS.
- Django system check: PASS.
- Ruff `apps/seo`: PASS.
- Прямые SQL `UPDATE` и `DELETE` истории: BLOCKED/PASS.

Не создавались мастера, цены, отзывы или production-данные. Старый PSEO,
Flask, SQLite и его тексты не импортировались.
