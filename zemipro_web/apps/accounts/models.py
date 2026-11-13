from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


class User(AbstractUser):
    """One identity; legacy role retained for compatibility, not authorization."""

    class Role(models.TextChoices):
        CLIENT = 'client', 'Заказчик'
        WORKER = 'worker', 'Исполнитель'
        ADMIN = 'admin', 'Администратор'

    class ActiveRole(models.TextChoices):
        CLIENT = 'client', 'Заказчик'
        WORKER = 'worker', 'Исполнитель'

    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.CLIENT,
        verbose_name='Роль'
    )
    active_role = models.CharField(
        max_length=10, choices=ActiveRole.choices, default=ActiveRole.CLIENT,
        verbose_name='Выбранный кабинет',
        help_text='Только выбор интерфейса; права определяются профилями и доступом к объекту.',
    )
    phone = models.CharField(
        max_length=20, blank=True, null=True,
        verbose_name='Телефон'
    )
    email_verified_at = models.DateTimeField(null=True, blank=True)
    phone_verified_at = models.DateTimeField(null=True, blank=True)
    email_verification_required = models.BooleanField(
        default=False,
        verbose_name='Требуется подтверждение email для доступа',
        help_text=(
            'Включается только для новых email-регистраций. Значение по '
            'умолчанию сохраняет доступ исторических username/password аккаунтов.'
        ),
    )
    preferred_language = models.CharField(
        max_length=2, choices=[('ru', 'Русский'), ('en', 'English'), ('he', 'עברית')],
        default='ru', verbose_name='Предпочитаемый язык',
    )
    is_blocked = models.BooleanField(
        default=False, verbose_name='Заблокирован'
    )
    last_active = models.DateTimeField(
        auto_now=True, verbose_name='Последняя активность'
    )

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        db_table = 'accounts_user'

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def is_client(self):
        # Client access still requires authentication and order ownership.
        return self.active_role == self.ActiveRole.CLIENT or hasattr(self, 'client_profile')

    @property
    def is_worker(self):
        # A selected worker dashboard alone never grants worker permissions.
        return hasattr(self, 'worker_profile')


class ClientProfile(models.Model):
    """Профиль заказчика."""

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='client_profile',
        verbose_name='Пользователь'
    )
    city = models.ForeignKey(
        'locations.City', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Город'
    )
    contact = models.CharField(
        max_length=100, blank=True,
        verbose_name='Контакт для связи'
    )
    receive_optional_updates = models.BooleanField(
        default=True, verbose_name='Дополнительные уведомления',
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Профиль заказчика'
        verbose_name_plural = 'Профили заказчиков'
        db_table = 'accounts_client_profile'

    def __str__(self):
        return f'Клиент: {self.user}'


class WorkerProfile(models.Model):
    """One professional/company card. Draft until explicit owner publication."""

    class ProviderType(models.TextChoices):
        INDIVIDUAL = 'individual', _('Частный мастер')
        COMPANY = 'company', _('Компания')

    class Availability(models.TextChoices):
        AVAILABLE = 'available', _('Принимаю заказы')
        LIMITED = 'limited', _('Ограниченная доступность')
        UNAVAILABLE = 'unavailable', _('Пока не принимаю заказы')

    provider_type = models.CharField(
        max_length=10, choices=ProviderType.choices,
        default=ProviderType.INDIVIDUAL, verbose_name=_('Тип исполнителя'),
    )
    display_name = models.CharField(
        max_length=120, blank=True, default='',
        verbose_name=_('Публичное имя или компания'),
    )
    spoken_languages = models.JSONField(
        default=list, blank=True, verbose_name=_('Языки общения'),
    )
    pricing_details = models.CharField(
        max_length=240, blank=True, default='',
        verbose_name=_('Цены или принцип расчёта'),
    )
    starting_price_ils = models.DecimalField(
        max_digits=10, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(0)], db_index=True,
        verbose_name=_('Заявленная стартовая цена, ₪'),
        help_text=_('Необязательная цена от мастера; текст не преобразуется в число.'),
    )
    availability = models.CharField(
        max_length=12, choices=Availability.choices,
        default=Availability.AVAILABLE, verbose_name=_('Доступность'),
    )
    working_hours = models.CharField(
        max_length=200, blank=True, default='', verbose_name=_('График работы'),
    )
    is_published = models.BooleanField(default=False, verbose_name=_('Опубликован'))
    published_at = models.DateTimeField(null=True, blank=True, verbose_name=_('Опубликован с'))

    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name='worker_profile',
        verbose_name='Пользователь'
    )
    city = models.ForeignKey(
        'locations.City', on_delete=models.SET_NULL,
        null=True, blank=True, verbose_name='Город'
    )
    contact = models.CharField(
        max_length=100, blank=True,
        verbose_name='Контакт для связи'
    )
    description = models.TextField(
        blank=True, default='',
        verbose_name='Описание услуг'
    )
    skills = models.ManyToManyField(
        'marketplace.Category', blank=True,
        related_name='workers', verbose_name='Навыки'
    )
    services = models.ManyToManyField(
        'marketplace.Subcategory', blank=True,
        related_name='workers', verbose_name=_('Конкретные услуги'),
    )
    service_cities = models.ManyToManyField(
        'locations.City', blank=True,
        related_name='service_workers', verbose_name='Города обслуживания',
    )
    service_neighborhoods = models.ManyToManyField(
        'locations.Neighborhood', blank=True,
        related_name='service_workers',
        verbose_name=_('Районы обслуживания'),
    )
    offers_remote = models.BooleanField(
        default=False, verbose_name='Работаю онлайн',
    )
    receive_notifications = models.BooleanField(
        default=True, verbose_name='Получать уведомления'
    )
    is_verified = models.BooleanField(
        default=False, verbose_name='Верифицирован'
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Профиль исполнителя'
        verbose_name_plural = 'Профили исполнителей'
        db_table = 'accounts_worker_profile'
        indexes = [
            models.Index(
                fields=['is_published', 'city', 'availability'],
                name='worker_public_search_idx',
            ),
        ]

    def __str__(self):
        return f'Мастер: {self.user}'

class WorkerPortfolioPhoto(models.Model):
    """Worker-owned image with opaque, private storage and opt-in public access."""

    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.PROTECT, related_name='portfolio_photos',
    )
    file_key = models.CharField(max_length=96, unique=True)
    caption = models.CharField(max_length=300, blank=True, default='')
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_public = models.BooleanField(default=False)
    rights_confirmed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_worker_portfolio_photo'
        ordering = ['sort_order', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(sort_order__lte=999),
                name='worker_portfolio_sort_order_max_999',
            ),
        ]


class SensitivePostCounter(models.Model):
    """Opaque time-window counters shared atomically between Gunicorn workers.

    Only HMAC digests are stored; raw IP addresses and submitted credentials
    must never be written to this table.
    """

    bucket_hash = models.CharField(max_length=64, primary_key=True)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField(db_index=True)

    class Meta:
        db_table = 'accounts_sensitive_post_counter'

class ContactChallenge(models.Model):
    """One time-limited, hashed verification code per account and channel."""

    class Channel(models.TextChoices):
        EMAIL = 'email', 'Email'
        PHONE = 'phone', 'Телефон'

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='contact_challenges',
    )
    channel = models.CharField(max_length=8, choices=Channel.choices)
    destination_digest = models.CharField(max_length=64)
    code_digest = models.CharField(max_length=64)
    attempts = models.PositiveSmallIntegerField(default=0)
    expires_at = models.DateTimeField()
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'accounts_contact_challenge'
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'channel'], name='accounts_one_contact_challenge',
            ),
        ]


class VerifiedContact(models.Model):
    """DB-unique verified identity: prevents two accounts claiming one address."""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='verified_contacts',
    )
    channel = models.CharField(max_length=8, choices=ContactChallenge.Channel.choices)
    fingerprint = models.CharField(max_length=64, unique=True)
    verified_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'accounts_verified_contact'


class ContactDeliveryEvent(models.Model):
    """Audit outcome only. Never persist verification codes or raw contacts."""

    class Outcome(models.TextChoices):
        SENT = 'sent', 'Передано адаптеру'
        UNAVAILABLE = 'unavailable', 'Доставка не настроена'
        FAILED = 'failed', 'Ошибка доставки'

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='contact_delivery_events',
    )
    channel = models.CharField(max_length=8, choices=ContactChallenge.Channel.choices)
    destination_digest = models.CharField(max_length=64)
    outcome = models.CharField(max_length=12, choices=Outcome.choices)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_contact_delivery_event'

class PrivacyRequest(models.Model):
    """Owner-initiated request, NEVER an automatic cascade-deletion command."""

    class Kind(models.TextChoices):
        EXPORT = 'export', _('Экспорт данных')
        DELETE = 'delete', _('Удаление данных')

    class Status(models.TextChoices):
        PENDING = 'pending', _('Ожидает обработки')
        PROCESSING = 'processing', _('На рассмотрении')
        COMPLETED = 'completed', _('Выполнен')
        REJECTED = 'rejected', _('Отклонён')

    user = models.ForeignKey(
        User, on_delete=models.PROTECT, related_name='privacy_requests',
    )
    kind = models.CharField(max_length=10, choices=Kind.choices)
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'accounts_privacy_request'
        ordering = ['-created_at', '-pk']
        constraints = [
            models.UniqueConstraint(
                fields=['user', 'kind'],
                condition=models.Q(status='pending'),
                name='accounts_unique_pending_privacy_request',
            ),
        ]

class FavoriteWorker(models.Model):
    """Private customer bookmark; not a public recommendation or endorsement."""

    client = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='favorite_workers',
    )
    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='favorited_by',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'accounts_favorite_worker'
        constraints = [
            models.UniqueConstraint(
                fields=['client', 'worker'],
                name='accounts_unique_client_favorite_worker',
            ),
        ]
