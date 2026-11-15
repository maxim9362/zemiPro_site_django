# Stage 09.5 — безопасная миграция legacy URL

Статус: `MECHANISM_VERIFIED / REAL_DECISIONS_PENDING_09.1`.

## Реестр

Миграция `seo.0003` добавляет все 21 строки `SEO_URL_INVENTORY.csv` как
`review`, `is_active=false`. Это журнал известных адресов, а не импорт старого
PSEO и не утверждение об их индексации.

Runtime обрабатывает только `/master/<path>` и выполняет **точный** поиск полной
строки. Неизвестный адрес, `review`, `keep` без существующего Django route,
неактивная запись или выключенный feature flag возвращают 404 без редиректа.

## Активация

Решение можно активировать только транзакционным `activate_legacy_url`:

1. actor — staff с отдельным permission `approve_legacy_url`;
2. есть источник HTTP/GSC/редакторских доказательств;
3. target — локальный query-free path, не self/open redirect;
4. target разрешается в allowlist публичных Django views;
5. соответствующая ORM-сущность активна, город — Ashdod, есть реальный supply;
6. для услуги опубликован редакционно проверенный контент нужного языка;
7. target не является другой активной legacy-записью (нет цепочки/цикла).

Поддерживаются индивидуальные `301`, `308`, `404`, `410`. Query string старого
адреса намеренно не переносится, чтобы не протащить непроверенные параметры.

## Rollback

1. Немедленно установить `ZEMIPRO_LEGACY_REDIRECTS_ENABLED=false` и перезапустить
   только Django application processes штатным будущим release-процессом.
2. Проверить, что legacy fallback снова отвечает 404, а новые canonical URLs
   доступны напрямую.
3. Деактивировать ошибочные строки через `deactivate_legacy_url` с audit actor.
4. После исправления доказательств/цели повторить staging URL matrix.

Эти шаги подготовлены, но не выполнялись на production. DNS/reverse proxy не
менялись.

## Тесты

- все 21 seeded URL при даже включённом runtime flag остаются 404, пока review;
- точный synthetic 301/308, 404/410, unknown URL, POST 405 и feature-off;
- query dropping, permission denial, unsafe target и active-chain rejection;
- activation/deactivation rollback;
- model/DB constraints и open/self redirect validation.

Фактические решения 20 `REVIEW` и проверка кандидата `KEEP` для `/` остаются до
HTTP/GSC из Stage 09.1. Массовый redirect на главную отсутствует.
