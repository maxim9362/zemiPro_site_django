import uuid

from django.core.validators import MinValueValidator, MaxValueValidator
from django.core.exceptions import ValidationError
from django.db import models
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
        ]

    def __str__(self):
        return f'Заказ #{self.pk} — {self.category.name_ru} ({self.get_status_display()})'


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


class Response(models.Model):
    """Отклик исполнителя на заказ."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Ожидает'
        ACCEPTED = 'accepted', 'Принят'
        REJECTED = 'rejected', 'Отклонён'
        CANCELLED = 'cancelled', 'Отменён'

    order = models.ForeignKey(
        Order, on_delete=models.CASCADE,
        related_name='responses', verbose_name='Заказ'
    )
    worker = models.ForeignKey(
        'accounts.User', on_delete=models.PROTECT,
        related_name='responses', verbose_name='Исполнитель'
    )
    message = models.TextField(blank=True, default='', verbose_name='Сообщение')
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
                condition=models.Q(status__in=['pending', 'accepted', 'rejected', 'cancelled']),
                name='response_status_allowed',
            ),
        ]

    def __str__(self):
        return f'Отклик {self.worker} на заказ #{self.order_id}'


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
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')

    class Meta:
        verbose_name = 'Отзыв'
        verbose_name_plural = 'Отзывы'
        db_table = 'marketplace_rating'
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.worker} — {self.rating}/5'


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
