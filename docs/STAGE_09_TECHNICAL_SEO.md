# Stage 09.4 — техническое SEO

Статус: `CODE_VERIFIED / INDEXING_DISABLED_BY_DEFAULT`.

## Контракты

- `/sitemap.xml` публикует только страницы, у которых одновременно есть три
  редакционно проверенные RU/EN/HE версии и фактический privacy-safe supply.
  Локализованные профили попадают туда только с непустым безопасным snapshot.
- `/robots.txt` при выключенном `ZEMIPRO_CATALOG_INDEXING_ENABLED` возвращает
  `Disallow: /`. После отдельного owner-gate разрешает публичный crawl и
  закрывает служебные/auth/order/chat/moderation/Stage14-private пути.
- Canonical не включает query string. Hreflang содержит `ru`, `en`, `he` и
  `x-default` на русский стабильный маршрут.
- Open Graph содержит только title/description/canonical/type текущей страницы.
- JSON-LD ограничен `WebPage`, `BreadcrumbList`, `Service`, `City` и
  `ProfilePage` по реально видимому содержимому. Нет `AggregateRating`,
  `Review`, цены, контактов, лицензий или гарантий.
- JSON сериализуется с экранированием `<`, `>`, `&`, а обычный контент остаётся
  под Django autoescape.

## Проверки

- Technical SEO + i18n: 23/23 PASS.
- Sitemap eligible-only, три языка, x-default, отсутствие другой географии/PII:
  PASS.
- Robots fail-closed/default и public allowlist: PASS.
- Canonical/hreflang/OG/JSON-LD, schema XSS и отсутствие ложных полей: PASS.
- Django check, Ruff, `git diff --check`: PASS.

Флаг индексации не включался в production. Закрытые функции Stage 14 не
добавлялись в sitemap и не активировались.
