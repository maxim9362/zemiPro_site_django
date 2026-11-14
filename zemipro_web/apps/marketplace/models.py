import uuid

from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import get_language


WORK_MODE_CHOICES = [
    ('onsite', 'Выезд'),
    ('online', 'Онлайн'),
    ('both', 'Выезд и онлайн'),
]


def localized_catalog_value(instance, field, *, russian_field=None):
    """Use the active Django language; never expose a blank translation."""
    code = (get_language() or 'ru').split('-')[0].lower()
    ru = russian_field or f'{field}_ru'
    value = getattr(instance, f'{field}_{code}', '') if code in {'en', 'he'} else ''
    return value or getattr(instance, ru)


class ServiceSection(models.Model):
    """Stable top-level directory, independent of user-facing translations."""

    name_ru = models.CharField(max_length=100, verbose_name='Раздел (рус)')
    name_en = models.CharField(max_length=100, blank=True, default='', verbose_name='Раздел (англ)')
    name_he = models.CharField(max_length=100, blank=True, default='', verbose_name='Раздел (иврит)')
    slug = models.SlugField(unique=True, verbose_name='Slug')
    description_ru = models.TextField(blank=True, default='')
    description_en = models.TextField(blank=True, default='')
    description_he = models.TextField(blank=True, default='')
    seo_title_ru = models.CharField(max_length=180, blank=True, default='')
    seo_title_en = models.CharField(max_length=180, blank=True, default='')
    seo_title_he = models.CharField(max_length=180, blank=True, default='')
    seo_description_ru = models.CharField(max_length=320, blank=True, default='')
    seo_description_en = models.CharField(max_length=320, blank=True, default='')
    seo_description_he = models.CharField(max_length=320, blank=True, default='')
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        verbose_name = 'Раздел услуг'
        verbose_name_plural = 'Разделы услуг'
        db_table = 'marketplace_service_section'
        ordering = ['sort_order', 'pk']

    @property
    def localized_name(self):
        return localized_catalog_value(self, 'name')

    @property
    def localized_description(self):
        return localized_catalog_value(self, 'description')

    def __str__(self):
        return self.name_ru


class Category(models.Model):
    """Stable category; legacy IDs/slugs stay unchanged."""

    # Nullable for pre-existing categories until the operator runs the seed.
    section = models.ForeignKey(
        ServiceSection, on_delete=models.PROTECT, related_name='categories',
        null=True, blank=True, verbose_name='Раздел',
    )

    name_ru = models.CharField(max_length=100, verbose_name='Название (рус)')
    name_he = models.CharField(max_length=100, blank=True, default='', verbose_name='Название (иврит)')
    name_en = models.CharField(max_length=100, blank=True, default='', verbose_name='Название (англ)')
    slug = models.SlugField(unique=True, verbose_name='Slug')
    emoji = models.CharField(max_length=10, blank=True, default='', verbose_name='Эмодзи')
    description = models.TextField(blank=True, default='', verbose_name='Описание')
    description_en = models.TextField(blank=True, default='')
    description_he = models.TextField(blank=True, default='')
    seo_title_ru = models.CharField(max_length=180, blank=True, default='')
    seo_title_en = models.CharField(max_length=180, blank=True, default='')
    seo_title_he = models.CharField(max_length=180, blank=True, default='')
    seo_description_ru = models.CharField(max_length=320, blank=True, default='')
    seo_description_en = models.CharField(max_length=320, blank=True, default='')
    seo_description_he = models.CharField(max_length=320, blank=True, default='')
    work_mode = models.CharField(
        max_length=10, choices=WORK_MODE_CHOICES, default='onsite',
    )
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Порядок сортировки')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        db_table = 'marketplace_category'
        ordering = ['sort_order', 'name_ru']

    @property
    def localized_name(self):
        return localized_catalog_value(self, 'name')

    @property
    def localized_description(self):
        return localized_catalog_value(self, 'description', russian_field='description')

    def __str__(self):
        return f'{self.emoji} {self.name_ru}' if self.emoji else self.name_ru


class Subcategory(models.Model):
    """Подкатегория внутри категории."""

    category = models.ForeignKey(
        Category, on_delete=models.CASCADE,
        related_name='subcategories', verbose_name='Категория'
    )
    name_ru = models.CharField(max_length=100, verbose_name='Название (рус)')
    name_he = models.CharField(max_length=100, blank=True, default='', verbose_name='Название (иврит)')
    name_en = models.CharField(max_length=100, blank=True, default='', verbose_name='Название (англ)')
    slug = models.SlugField(verbose_name='Slug')
    description_ru = models.TextField(blank=True, default='')
    description_en = models.TextField(blank=True, default='')
    description_he = models.TextField(blank=True, default='')
    seo_title_ru = models.CharField(max_length=180, blank=True, default='')
    seo_title_en = models.CharField(max_length=180, blank=True, default='')
    seo_title_he = models.CharField(max_length=180, blank=True, default='')
    seo_description_ru = models.CharField(max_length=320, blank=True, default='')
    seo_description_en = models.CharField(max_length=320, blank=True, default='')
    seo_description_he = models.CharField(max_length=320, blank=True, default='')
    work_mode = models.CharField(
        max_length=10, choices=WORK_MODE_CHOICES, default='onsite',
    )
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Порядок сортировки')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        verbose_name = 'Подкатегория'
        verbose_name_plural = 'Подкатегории'
        db_table = 'marketplace_subcategory'
        ordering = ['sort_order', 'name_ru']
        constraints = [
            models.UniqueConstraint(
                fields=['category', 'slug'],
                name='unique_subcategory_slug_per_category'
            )
        ]

    @property
    def localized_name(self):
        return localized_catalog_value(self, 'name')

    @property
    def localized_description(self):
        return localized_catalog_value(self, 'description')

    def __str__(self):
        return f'{self.category.name_ru} → {self.name_ru}'


class Order(models.Model):
    """Заявка на услугу от заказчика."""

    class Status(models.TextChoices):
        DRAFT = 'draft', 'Черновик'
        PUBLISHED = 'published', 'Опубликован'
        IN_DISCUSSION = 'in_discussion', 'Обсуждение'
        ASSIGNED = 'assigned', 'Исполнитель выбран'
        IN_PROGRESS = 'in_progress', 'В процессе'
        COMPLETED = 'completed', 'Выполнен'
        CANCELLED = 'cancelled', 'Отменён'
        EXPIRED = 'expired', 'Истёк срок'
        DISPUTED = 'disputed', 'Спор'

    client = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='client_orders',
        verbose_name='Заказчик'
    )
    customer_name = models.CharField(
        max_length=120, blank=True, default='',
        verbose_name='Имя клиента'
    )
    customer_phone = models.CharField(
        max_length=30, blank=True, default='',
        verbose_name='Телефон клиента'
    )
    worker = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='worker_orders',
        verbose_name='Исполнитель'
    )
    category = models.ForeignKey(
        Category, on_delete=models.PROTECT,
        related_name='orders', verbose_name='Категория'
    )
    subcategory = models.ForeignKey(
        Subcategory, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='orders',
        verbose_name='Подкатегория'
    )
    city = models.ForeignKey(
        'locations.City', on_delete=models.PROTECT,
        related_name='orders', verbose_name='Город'
    )
    address = models.CharField(max_length=255, verbose_name='Адрес')
    description = models.TextField(verbose_name='Описание задачи')
    price = models.CharField(
        max_length=50, default='Договорная',
        verbose_name='Цена'
    )
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PUBLISHED,
        db_index=True, verbose_name='Статус'
    )
    legacy_status = models.CharField(
        max_length=20, null=True, blank=True, editable=False,
        verbose_name='Исходный исторический статус',
    )
    wizard_data = models.JSONField(
        default=dict, blank=True, editable=False,
        verbose_name='Приватные данные мастера создания заявки',
    )
    wizard_token = models.UUIDField(
        null=True, blank=True, unique=True, editable=False,
        verbose_name='Ключ защиты от повторного создания черновика',
    )
    submission_digest = models.CharField(
        max_length=64, blank=True, default='', db_index=True, editable=False,
        verbose_name='Защищённый отпечаток подачи заявки',
    )
    class PriceKind(models.TextChoices):
        LEGACY = 'legacy', 'Историческая цена'
        FIXED = 'fixed', 'Фиксированная'
        RANGE = 'range', 'Диапазон'
        NEGOTIABLE = 'negotiable', 'Договорная'

    class WorkMode(models.TextChoices):
        LEGACY = 'legacy', 'Не указан'
        ONSITE = 'onsite', 'На месте'
        ONLINE = 'online', 'Онлайн'

    class Urgency(models.TextChoices):
        LEGACY = 'legacy', 'Не указана'
        NORMAL = 'normal', 'Обычная'
        SOON = 'soon', 'В ближайшие дни'
        URGENT = 'urgent', 'Срочно'

    price_kind = models.CharField(
        max_length=12, choices=PriceKind.choices, default=PriceKind.LEGACY,
    )
    amount_min_ils = models.DecimalField(
        max_digits=9, decimal_places=2, blank=True, null=True,
    )
    amount_max_ils = models.DecimalField(
        max_digits=9, decimal_places=2, blank=True, null=True,
    )
    preferred_date = models.DateField(blank=True, null=True)
    urgency = models.CharField(
        max_length=8, choices=Urgency.choices, default=Urgency.LEGACY,
    )
    work_mode = models.CharField(
        max_length=8, choices=WorkMode.choices, default=WorkMode.LEGACY,
    )
    approximate_area = models.CharField(max_length=80, blank=True, default='')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        verbose_name = 'Заказ'
        verbose_name_plural = 'Заказы'
        db_table = 'marketplace_order'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', '-created_at'], name='order_status_created_idx'),
            models.Index(fields=['city', 'status'], name='order_city_status_idx'),
            models.Index(fields=['category', 'status'], name='order_category_status_idx'),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=[
                    'draft', 'published', 'in_discussion', 'assigned',
                    'in_progress', 'completed', 'cancelled', 'expired', 'disputed',
                ]),
                name='order_status_allowed',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        price_kind__in=['legacy', 'negotiable'],
                        amount_min_ils__isnull=True, amount_max_ils__isnull=True,
                    )
                    | models.Q(
                        price_kind='fixed', amount_min_ils__gte=0,
                        amount_min_ils__isnull=False, amount_max_ils__isnull=True,
                    )
                    | models.Q(
                        price_kind='range', amount_min_ils__gte=0,
                        amount_min_ils__isnull=False, amount_max_ils__isnull=False,
                        amount_max_ils__gte=models.F('amount_min_ils'),
                    )
                ),
                name='order_structured_price_valid',
            ),
        ]

    @property
    def localized_status(self):
        from .wizard_ui import localized_order_status
        return localized_order_status(self.status)

    def __str__(self):
        return f'Заказ #{self.pk} — {self.category.name_ru} ({self.get_status_display()})'



class OrderAttachment(models.Model):
    """Server-gated, metadata-free JPEG; source image never stored publicly."""

    class Visibility(models.TextChoices):
        PRIVATE = 'private', 'Только заказчик'
        ASSIGNEE = 'assignee', 'Выбранный исполнитель'
        PUBLIC = 'public', 'Публично (по согласию)'

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name='attachments',
    )
    uploaded_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='order_photo_uploads',
    )
    file_key = models.CharField(max_length=120, unique=True, editable=False)
    visibility = models.CharField(
        max_length=9, choices=Visibility.choices, default=Visibility.PRIVATE,
    )
    content_sha256 = models.CharField(max_length=64, editable=False)
    byte_size = models.PositiveIntegerField()
    public_consent_at = models.DateTimeField(null=True, blank=True, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_order_attachment'
        ordering = ('created_at', 'pk')
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'content_sha256', 'visibility'],
                name='order_photo_unique_content_scope',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(visibility__in=['private', 'assignee', 'public'])
                    & (models.Q(visibility='public', public_consent_at__isnull=False)
                       | ~models.Q(visibility='public'))
                ),
                name='order_photo_visibility_allowed',
            ),
        ]

    def __str__(self):
        return f'Фото #{self.pk} заказа #{self.order_id}'


class OrderStatusEvent(models.Model):
    """Append-only, non-PII history of significant lifecycle changes."""

    class Reason(models.TextChoices):
        CREATED = 'created', 'Создание'
        TRANSITION = 'transition', 'Смена статуса'
        WORKER_ASSIGNED = 'worker_assigned', 'Выбор мастера'
        WORK_STARTED = 'work_started', 'Начало работы'
        LEGACY_MIGRATION = 'legacy_migration', 'Историческая миграция'

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name='status_events',
    )
    actor = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, null=True, blank=True,
        related_name='order_status_actions',
    )
    previous_status = models.CharField(max_length=20, blank=True, default='')
    new_status = models.CharField(max_length=20, choices=Order.Status.choices)
    reason = models.CharField(
        max_length=32, choices=Reason.choices, default=Reason.TRANSITION,
    )
    operation_key = models.UUIDField(default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_order_status_event'
        verbose_name = 'Событие статуса заявки'
        verbose_name_plural = 'События статусов заявок'
        ordering = ['-occurred_at', '-pk']
        indexes = [
            models.Index(fields=['order', '-occurred_at'], name='order_event_time_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'operation_key'],
                name='order_event_unique_operation',
            ),
        ]


class OrderManagementEvent(models.Model):
    """Immutable record of owner actions, containing field NAMES only."""

    class Action(models.TextChoices):
        EDITED = 'edited', 'Условия изменены'
        DUPLICATED = 'duplicated', 'Создана копия'

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name='management_events',
    )
    actor = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='order_management_actions',
    )
    action = models.CharField(max_length=16, choices=Action.choices)
    changed_fields = models.JSONField(default=list, blank=True)
    target_order = models.ForeignKey(
        Order, null=True, blank=True, on_delete=models.PROTECT,
        related_name='duplicate_source_events',
    )
    operation_key = models.UUIDField(default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_order_management_event'
        ordering = ['occurred_at', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'operation_key'],
                name='order_mgmt_unique_operation',
            ),
        ]
        indexes = [
            models.Index(fields=['order', 'occurred_at'], name='order_mgmt_time_idx'),
        ]


class OrderQuestionnaireAnswerArchive(models.Model):
    """Private immutable copy of a questionnaire before re-publication."""

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT,
        related_name='questionnaire_answer_archives',
    )
    version = models.ForeignKey(
        'QuestionnaireVersion', on_delete=models.PROTECT,
        related_name='archived_order_answers',
    )
    schema_snapshot = models.JSONField(default=list)
    answers = models.JSONField(default=dict)
    archived_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_order_questionnaire_answer_archive'
        ordering = ['archived_at', 'pk']




class OrderWriteQuota(models.Model):
    """Durable per-account fixed window for order mutations across web workers."""

    class Kind(models.TextChoices):
        CREATE = 'create', 'Создания заявок'
        WIZARD = 'wizard', 'Сохранения шагов'
        EDIT = 'edit', 'Редактирование условий'
        RESPONSE = 'response', 'Отклики исполнителей'
        PHOTO = 'photo', 'Новые фотографии'
        STATE = 'state', 'Переходы статусов'
        INVITE = 'invite', 'Приглашения мастерам'

    owner = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='order_write_quotas',
    )
    kind = models.CharField(max_length=8, choices=Kind.choices)
    bucket_start = models.DateTimeField()
    used = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = 'marketplace_order_write_quota'
        constraints = [
            models.UniqueConstraint(
                fields=['owner', 'kind', 'bucket_start'],
                name='order_quota_owner_kind_window_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['bucket_start'], name='order_quota_window_idx'),
        ]




class OrderDomainEvent(models.Model):
    """Immutable, PII-free order event captured in the mutation transaction."""

    class Kind(models.TextChoices):
        CREATED = 'order_created', 'Создание заявки'
        PUBLISHED = 'order_published', 'Публикация заявки'
        UPDATED = 'order_updated', 'Изменение условий'
        CANCELLED = 'order_cancelled', 'Отмена заявки'

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name='domain_events',
    )
    kind = models.CharField(max_length=24, choices=Kind.choices)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    city = models.ForeignKey('locations.City', on_delete=models.PROTECT)
    source_key = models.UUIDField(editable=False)
    event_key = models.UUIDField(unique=True, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_order_domain_event'
        ordering = ['occurred_at', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'kind', 'source_key'],
                name='order_domain_source_unique',
            ),
        ]
        indexes = [
            models.Index(
                fields=['kind', 'occurred_at'], name='order_domain_kind_time_idx',
            ),
        ]


class OrderEventDelivery(models.Model):
    """Idempotent in-app notifications and local analytics consumer receipt."""

    class Consumer(models.TextChoices):
        NOTIFICATIONS = 'notifications', 'Внутренние уведомления'
        ANALYTICS = 'analytics', 'Внутренняя аналитика'

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает'
        DONE = 'done', 'Обработано'

    event = models.ForeignKey(
        OrderDomainEvent, on_delete=models.PROTECT, related_name='deliveries',
    )
    consumer = models.CharField(max_length=16, choices=Consumer.choices)
    status = models.CharField(
        max_length=8, choices=Status.choices, default=Status.PENDING,
    )
    attempts = models.PositiveIntegerField(default=0)
    last_error_code = models.CharField(max_length=32, blank=True, default='')
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'marketplace_order_event_delivery'
        ordering = ['event_id', 'consumer']
        constraints = [
            models.UniqueConstraint(
                fields=['event', 'consumer'], name='order_delivery_consumer_unique',
            ),
        ]


class OrderAnalyticsFact(models.Model):
    """One coarse-grained fact per event, without content or contacts."""

    event = models.OneToOneField(
        OrderDomainEvent, on_delete=models.PROTECT,
        related_name='analytics_fact',
    )
    kind = models.CharField(max_length=24, choices=OrderDomainEvent.Kind.choices)
    category = models.ForeignKey(Category, on_delete=models.PROTECT)
    city = models.ForeignKey('locations.City', on_delete=models.PROTECT)
    occurred_at = models.DateTimeField()

    class Meta:
        db_table = 'marketplace_order_analytics_fact'
        indexes = [
            models.Index(
                fields=['kind', 'occurred_at'], name='order_fact_kind_time_idx',
            ),
        ]




class Response(models.Model):
    """Отклик исполнителя на заказ."""

    class Status(models.TextChoices):
        # Legacy pending/cancelled values remain readable for pre-stage-06 rows.
        PENDING = 'pending', 'Исторический отклик'
        CANCELLED = 'cancelled', 'Исторически отменён'
        SENT = 'sent', 'Отправлено'
        VIEWED = 'viewed', 'Просмотрено'
        NEGOTIATING = 'negotiating', 'Обсуждение'
        ACCEPTED = 'accepted', 'Принято'
        REJECTED = 'rejected', 'Отклонено'
        WITHDRAWN = 'withdrawn', 'Отозвано'
        EXPIRED = 'expired', 'Истекло'

    class PriceKind(models.TextChoices):
        NEGOTIABLE = 'negotiable', 'По договорённости'
        FIXED = 'fixed', 'Фиксированная цена'
        RANGE = 'range', 'Диапазон'
        METHOD = 'method', 'Способ расчёта'

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE,
        related_name='responses', verbose_name='Заказ'
    )
    worker = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='responses', verbose_name='Исполнитель'
    )
    message = models.TextField(blank=True, default='', verbose_name='Сообщение')
    price_kind = models.CharField(
        max_length=12, choices=PriceKind.choices, default=PriceKind.NEGOTIABLE,
    )
    amount_min_ils = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True,
    )
    amount_max_ils = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True,
    )
    pricing_method = models.CharField(max_length=240, blank=True, default='')
    estimated_timeline = models.CharField(max_length=160, blank=True, default='')
    terms = models.TextField(blank=True, default='')
    revision = models.PositiveIntegerField(default=1, editable=False)
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
        verbose_name='Статус'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Отклик'
        verbose_name_plural = 'Отклики'
        db_table = 'marketplace_response'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'worker'],
                name='unique_response_per_worker_per_order'
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=[
                    'pending', 'cancelled', 'sent', 'viewed', 'negotiating',
                    'accepted', 'rejected', 'withdrawn', 'expired',
                ]),
                name='response_status_allowed',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        price_kind__in=['negotiable', 'method'],
                        amount_min_ils__isnull=True, amount_max_ils__isnull=True,
                    )
                    | models.Q(
                        price_kind='fixed', amount_min_ils__gte=0,
                        amount_max_ils__isnull=True,
                    )
                    | models.Q(
                        price_kind='range', amount_min_ils__gte=0,
                        amount_max_ils__gte=models.F('amount_min_ils'),
                    )
                ),
                name='response_price_valid',
            ),
        ]

    def __str__(self):
        return f'Отклик {self.worker} на заказ #{self.order_id}'


class ResponseRevision(models.Model):
    """Append-only private offer snapshot and idempotency record."""

    response = models.ForeignKey(
        Response, on_delete=models.PROTECT, related_name='revisions',
    )
    number = models.PositiveIntegerField()
    actor = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='offer_actions',
    )
    operation_key = models.UUIDField(default=uuid.uuid4, editable=False)
    action = models.CharField(max_length=16)
    status = models.CharField(max_length=20)
    message = models.TextField(blank=True, default='')
    price_kind = models.CharField(max_length=12)
    amount_min_ils = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True,
    )
    amount_max_ils = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True,
    )
    pricing_method = models.CharField(max_length=240, blank=True, default='')
    estimated_timeline = models.CharField(max_length=160, blank=True, default='')
    terms = models.TextField(blank=True, default='')
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_response_revision'
        ordering = ['number', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['response', 'number'], name='offer_revision_number_unique',
            ),
            models.UniqueConstraint(
                fields=['response', 'operation_key'], name='offer_revision_operation_unique',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Offer revisions are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Offer revisions cannot be deleted.')



class OrderAgreementVersion(models.Model):
    """Immutable negotiated terms; only an accepted decision activates a version."""

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name='agreement_versions',
    )
    response = models.ForeignKey(
        Response, on_delete=models.PROTECT, related_name='agreement_versions',
    )
    number = models.PositiveIntegerField()
    response_revision = models.PositiveIntegerField()
    proposed_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='proposed_agreements',
    )
    operation_key = models.UUIDField(default=uuid.uuid4, editable=False)
    price_kind = models.CharField(max_length=12, choices=Response.PriceKind.choices)
    amount_min_ils = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True,
    )
    amount_max_ils = models.DecimalField(
        max_digits=9, decimal_places=2, null=True, blank=True,
    )
    pricing_method = models.CharField(max_length=240, blank=True, default='')
    estimated_timeline = models.CharField(max_length=160, blank=True, default='')
    terms = models.TextField(blank=True, default='')
    note = models.TextField(blank=True, default='')
    proposed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_order_agreement_version'
        ordering = ['number', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'number'], name='agreement_version_number_unique',
            ),
            models.UniqueConstraint(
                fields=['order', 'operation_key'], name='agreement_version_operation_unique',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Agreement versions are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Agreement versions cannot be deleted.')


class OrderAgreementDecision(models.Model):
    """Immutable counterparty consent or rejection of one proposed version."""

    class Result(models.TextChoices):
        ACCEPTED = 'accepted', 'Принято'
        REJECTED = 'rejected', 'Отклонено'

    agreement = models.OneToOneField(
        OrderAgreementVersion, on_delete=models.PROTECT, related_name='decision',
    )
    actor = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='agreement_decisions',
    )
    result = models.CharField(max_length=8, choices=Result.choices)
    operation_key = models.UUIDField(default=uuid.uuid4, editable=False)
    decided_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_order_agreement_decision'

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Agreement decisions are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Agreement decisions cannot be deleted.')


class OrderWorkEvent(models.Model):
    """Append-only confirmation and dispute evidence, no free-text PII."""

    class Action(models.TextChoices):
        STARTED = 'started', 'Начало работы'
        RESULT_SUBMITTED = 'result_submitted', 'Результат передан'
        RESULT_CONFIRMED = 'result_confirmed', 'Результат подтверждён'
        PROBLEM = 'problem', 'Сообщено о проблеме'

    class ProblemCode(models.TextChoices):
        NONE = '', 'Нет'
        TIMING = 'timing', 'Сроки'
        QUALITY = 'quality', 'Качество'
        OTHER = 'other', 'Другая проблема'

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name='work_events',
    )
    actor = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='order_work_events',
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    problem_code = models.CharField(
        max_length=8, choices=ProblemCode.choices, default=ProblemCode.NONE,
    )
    operation_key = models.UUIDField(default=uuid.uuid4, editable=False)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_order_work_event'
        ordering = ['occurred_at', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'operation_key'], name='work_event_operation_unique',
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(action='problem', problem_code__in=['timing', 'quality', 'other'])
                    | (models.Q(
                        action__in=['started', 'result_submitted', 'result_confirmed'],
                        problem_code='',
                    ))
                ),
                name='work_event_action_problem_valid',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Work events are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Work events cannot be deleted.')


class OrderInvitation(models.Model):
    """One registered specialist may be invited once to an existing order.

    An invitation is not an assignment and cannot grant private order access.
    """

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает'
        ACCEPTED = 'accepted', 'Принято'
        DECLINED = 'declined', 'Отклонено'
        WITHDRAWN = 'withdrawn', 'Отозвано'
        EXPIRED = 'expired', 'Истекло'
        UNAVAILABLE = 'unavailable', 'Недоступно'

    order = models.ForeignKey(
        Order, on_delete=models.PROTECT, related_name='specialist_invitations',
    )
    client = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='sent_order_invitations',
    )
    worker = models.ForeignKey(
        'accounts.WorkerProfile', on_delete=models.PROTECT,
        related_name='order_invitations',
    )
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING,
    )
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'marketplace_order_invitation'
        ordering = ['-created_at', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['order', 'worker'],
                name='market_order_worker_invite_unique',
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=[
                    'pending', 'accepted', 'declined', 'withdrawn',
                    'expired', 'unavailable',
                ]),
                name='market_order_invite_status_allowed',
            ),
        ]
        indexes = [
            models.Index(
                fields=['worker', 'status', '-created_at'],
                name='market_inv_worker_status_idx',
            ),
            models.Index(
                fields=['client', '-created_at'],
                name='market_inv_client_created_idx',
            ),
        ]

    @property
    def effective_status(self):
        """Present expired/cancelled/unavailable pending invites truthfully."""
        if self.status != self.Status.PENDING:
            return self.status
        if self.expires_at <= timezone.now():
            return self.Status.EXPIRED
        if self.order.status != Order.Status.PUBLISHED or self.order.worker_id is not None:
            return self.Status.UNAVAILABLE
        if (not self.worker.is_published
                or self.worker.availability == self.worker.Availability.UNAVAILABLE
                or not self.worker.user.is_active
                or self.worker.user.is_blocked
                or self.worker.user.email_verification_required):
            return self.Status.UNAVAILABLE
        return self.Status.PENDING

    @property
    def localized_status(self):
        from .invitation_ui import invitation_copy
        return invitation_copy()[self.effective_status]


class Rating(models.Model):
    """Отзыв и рейтинг заказчика на исполнителя."""

    order = models.OneToOneField(
        Order, on_delete=models.CASCADE,
        related_name='rating', verbose_name='Заказ'
    )
    worker = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='received_ratings', verbose_name='Исполнитель'
    )
    client = models.ForeignKey(
        'accounts.User', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='given_ratings',
        verbose_name='Заказчик'
    )
    rating = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        verbose_name='Оценка'
    )
    review_text = models.TextField(blank=True, default='', verbose_name='Текст отзыва')
    public_review_text_snapshot = models.TextField(
        blank=True, default='', editable=False,
    )
    public_content_safe = models.BooleanField(default=False, editable=False)
    public_content_policy_version = models.PositiveSmallIntegerField(
        default=0, editable=False,
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')

    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        db_table = 'marketplace_rating'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(rating__gte=1, rating__lte=5),
                name='rating_score_five_point_valid',
            ),
        ]

    def __str__(self):
        return f'{self.worker} — {self.rating}/5'

    @property
    def public_review_text(self):
        from apps.accounts.public_text import MARKER, POLICY_VERSION
        if (
            self.public_content_safe
            and self.public_content_policy_version == POLICY_VERSION
        ):
            return self.public_review_text_snapshot or (MARKER if self.review_text else '')
        return MARKER if self.review_text else ''

    def save(self, *args, **kwargs):
        from apps.accounts.public_text import POLICY_VERSION, build_caption_snapshot
        updates = kwargs.get('update_fields')
        if updates is None or 'review_text' in set(updates):
            snapshot = build_caption_snapshot(self.review_text)
            self.public_review_text_snapshot = snapshot or ''
            self.public_content_safe = True
            self.public_content_policy_version = POLICY_VERSION
            if updates is not None:
                updates = set(updates)
                updates.update({
                    'public_review_text_snapshot', 'public_content_safe',
                    'public_content_policy_version',
                })
                kwargs['update_fields'] = updates
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Verified reviews cannot be deleted.')


class ServiceQuestionnaire(models.Model):
    """Editable draft for exactly one concrete Subcategory."""
    service = models.OneToOneField(
        Subcategory, on_delete=models.PROTECT, related_name='questionnaire',
    )
    draft_schema = models.JSONField(default=list, blank=True)
    published_version = models.ForeignKey(
        'QuestionnaireVersion', null=True, blank=True,
        on_delete=models.PROTECT, related_name='+',
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'marketplace_service_questionnaire'
        verbose_name = 'Анкета услуги'
        verbose_name_plural = 'Анкеты услуг'

    def clean(self):
        super().clean()
        from .questionnaires import validate_question_schema
        validate_question_schema(self.draft_schema)
        if self.published_version_id and self.published_version.questionnaire_id != self.pk:
            raise ValidationError('Published version belongs to another questionnaire.')

    def __str__(self):
        return f'Анкета: {self.service}'


class QuestionnaireVersion(models.Model):
    """Published immutable version. Publishing a draft creates a NEW row."""
    questionnaire = models.ForeignKey(
        ServiceQuestionnaire, on_delete=models.PROTECT, related_name='versions',
    )
    number = models.PositiveIntegerField()
    schema = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_questionnaire_version'
        constraints = [
            models.UniqueConstraint(
                fields=['questionnaire', 'number'], name='unique_questionnaire_version',
            ),
        ]
        ordering = ['questionnaire_id', '-number']
        verbose_name = 'Опубликованная версия анкеты'
        verbose_name_plural = 'Опубликованные версии анкет'

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Published versions are immutable.')
        from .questionnaires import validate_question_schema
        validate_question_schema(self.schema)
        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.questionnaire.service} / v{self.number}'


class OrderQuestionnaireAnswer(models.Model):
    """Private immutable order-time snapshot; NEVER read current draft to display."""
    order = models.OneToOneField(
        Order, on_delete=models.CASCADE, related_name='questionnaire_answer',
    )
    version = models.ForeignKey(
        QuestionnaireVersion, on_delete=models.PROTECT, related_name='order_answers',
    )
    schema_snapshot = models.JSONField(default=list)
    answers = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_order_questionnaire_answer'
        verbose_name = 'Ответы на анкету заказа'
        verbose_name_plural = 'Ответы на анкеты заказов'

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Order questionnaire snapshots are immutable.')
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Анкета заказа #{self.order_id} / v{self.version.number}'


class Conversation(models.Model):
    """Private conversation bound to one existing, authorized worker offer."""

    response = models.OneToOneField(
        Response, on_delete=models.PROTECT, related_name='conversation',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_conversation'
        ordering = ['-created_at', '-pk']

    @property
    def order_id(self):
        return self.response.order_id

    @property
    def client_id(self):
        return self.response.order.client_id

    @property
    def worker_id(self):
        return self.response.worker_id


class Message(models.Model):
    """Original message is immutable; only recipient read status may change."""

    conversation = models.ForeignKey(
        Conversation, on_delete=models.PROTECT, related_name='messages',
    )
    sender = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='sent_chat_messages',
    )
    body = models.TextField()
    client_nonce = models.UUIDField(default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'marketplace_message'
        ordering = ['created_at', 'pk']
        constraints = [
            models.UniqueConstraint(
                fields=['conversation', 'sender', 'client_nonce'],
                name='chat_message_nonce_unique',
            ),
        ]
        indexes = [
            models.Index(
                fields=['conversation', 'id'], name='chat_message_page_idx',
            ),
            models.Index(
                fields=['conversation', 'sender', '-created_at'],
                name='chat_msg_actor_time_idx',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            previous = type(self).objects.filter(pk=self.pk).values(
                'conversation_id', 'sender_id', 'body', 'client_nonce',
            ).first()
            if previous is not None and any(
                previous[field] != getattr(self, field)
                for field in ('conversation_id', 'sender_id', 'body', 'client_nonce')
            ):
                raise ValidationError('Original chat messages cannot be modified.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Original chat messages cannot be deleted.')


class MessageAttachment(models.Model):
    """Opaque private JPEG only; no direct URL, original filename or metadata."""

    message = models.ForeignKey(
        Message, on_delete=models.PROTECT, related_name='attachments',
    )
    file_key = models.CharField(max_length=120, unique=True, editable=False)
    content_sha256 = models.CharField(max_length=64, editable=False)
    byte_size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_message_attachment'
        ordering = ['pk']
        constraints = [
            models.UniqueConstraint(
                fields=['message', 'content_sha256'],
                name='chat_attachment_digest_unique',
            ),
        ]

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Private attachment evidence is immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Private attachment evidence is immutable.')


class RatingReply(models.Model):
    """At most one public answer from the selected worker to a verified review."""

    rating = models.OneToOneField(
        Rating, on_delete=models.PROTECT, related_name='worker_reply',
    )
    worker = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='rating_replies',
    )
    body = models.TextField()
    public_body_snapshot = models.TextField(blank=True, default='', editable=False)
    policy_version = models.PositiveSmallIntegerField(default=0, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_rating_reply'

    @property
    def public_text(self):
        from apps.accounts.public_text import MARKER, POLICY_VERSION
        if self.policy_version == POLICY_VERSION:
            return self.public_body_snapshot or MARKER
        return MARKER

    def save(self, *args, **kwargs):
        from apps.accounts.public_text import POLICY_VERSION, build_caption_snapshot
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Review replies are append-only.')
        self.public_body_snapshot = build_caption_snapshot(self.body) or ''
        self.policy_version = POLICY_VERSION
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Review replies are append-only.')


class RatingAuditEvent(models.Model):
    """No mutable score history: a score and its creation/reply events are permanent."""

    class Action(models.TextChoices):
        CREATED = 'created', 'Review created'
        REPLIED = 'replied', 'Worker replied'

    rating = models.ForeignKey(
        Rating, on_delete=models.PROTECT, related_name='audit_events',
    )
    actor = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT, related_name='review_actions',
    )
    action = models.CharField(max_length=12, choices=Action.choices)
    score = models.PositiveSmallIntegerField()
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_rating_audit'
        constraints = [
            models.UniqueConstraint(
                fields=['rating', 'action'], name='rating_audit_action_unique',
            ),
        ]
        ordering = ['occurred_at', 'pk']

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Review audit entries are immutable.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Review audit entries are immutable.')

class MessageTranslation(models.Model):
    """Optional private machine translation; never replaces the original Message."""

    class Language(models.TextChoices):
        RU = 'ru', 'Русский'
        EN = 'en', 'English'
        HE = 'he', 'עברית'

    message = models.ForeignKey(
        Message, on_delete=models.PROTECT, related_name='machine_translations',
    )
    requested_by = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='requested_chat_translations',
    )
    target_language = models.CharField(max_length=2, choices=Language.choices)
    translated_body = models.TextField()
    engine = models.CharField(max_length=32, default='gemini')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'marketplace_message_translation'
        constraints = [
            models.UniqueConstraint(
                fields=['message', 'target_language'],
                name='chat_translation_target_unique',
            ),
            models.CheckConstraint(
                condition=models.Q(target_language__in=['ru', 'en', 'he']),
                name='chat_translation_language_valid',
            ),
        ]
        ordering = ['created_at', 'pk']

    def save(self, *args, **kwargs):
        if self.pk is not None and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError('Machine translations are append-only.')
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError('Machine translations are append-only.')
