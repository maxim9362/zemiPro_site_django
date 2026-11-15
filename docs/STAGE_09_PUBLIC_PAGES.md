# Stage 09.3 — публичные Django SEO-страницы

Статус: `CODE_VERIFIED`.

## Что добавлено

- Существующие локализованные страницы раздела, категории, услуги и города
  переиспользуют Stage 08 layout/components и получают редакционный блок только
  из опубликованной проверенной `SeoContentPage` текущего языка.
- Добавлен отдельный маршрут услуги в городе:
  `/<lang>/services/<category>/<service>/ashdod/`.
- Добавлен локализованный профиль:
  `/<lang>/professionals/<id>/`; старый `/worker/<id>/` сохранён без редиректа
  для обратной совместимости.
- Добавлены breadcrumbs, связанные услуги, безопасные CTA, реальные мастера
  конкретной услуги и честные пустые состояния.
- Страница города вне Ashdod возвращает 404. Страница без реального supply или
  опубликованного редакционного материала получает `noindex`.
- Пользовательский/редакторский текст выводится с автоэкранированием; контакты
  мастера берутся только из существующего privacy-safe snapshot.

## Проверки

- Stage 09 public pages + Stage 02 i18n + Stage 08 public UI: 28/28 PASS.
- RU/EN/HE URL, Hebrew `dir=rtl`, canonical/hreflang, breadcrumbs: PASS.
- Ashdod-only, thin-page noindex, PII suppression, XSS escaping: PASS.
- Legacy profile links и старые маршруты: regression PASS.

Четыре утверждённых HTML-эталона в `docs/frontend/approved/` не изменялись.

