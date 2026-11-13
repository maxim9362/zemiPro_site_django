from contextvars import ContextVar

from django.contrib.auth.models import AbstractUser, UserManager
from django.core.validators import MinValueValidator
from django.db import models, router, transaction
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from .public_text import (
    MARKER,
    POLICY_VERSION,
    build_caption_snapshot,
    build_fail_closed_profile_snapshot,
)


_PROFILE_BULK_SNAPSHOT_WRITE = ContextVar(
    'profile_bulk_snapshot_write', default=False,
)
_USER_BULK_IDENTITY_WRITE = ContextVar(
    'user_bulk_identity_write', default=False,
)


class SafeUserQuerySet(models.QuerySet):
    """Invalidate public projections after supported bulk identity changes."""

    def _invalidate_profiles(self, user_ids):
        profiles = WorkerProfile.objects.using(self.db).filter(
            user_id__in=user_ids,
        )
        profile_ids = list(
            profiles.select_for_update().order_by('pk').values_list('pk', flat=True),
        )
        WorkerProfile.objects.using(self.db).filter(pk__in=profile_ids).update(
            public_content_safe=False,
            public_content_policy_version=0,
        )

    def update(self, **kwargs):
        identity_change = (
            bool(set(kwargs) & {'email', 'phone'})
            and not _USER_BULK_IDENTITY_WRITE.get()
        )
        if not identity_change:
            return super().update(**kwargs)
        with transaction.atomic(using=self.db):
            user_ids = list(
                self.select_for_update().order_by('pk').values_list('pk', flat=True),
            )
            result = super().update(**kwargs)
            if user_ids:
                self._invalidate_profiles(user_ids)
            return result

    def bulk_update(self, objs, fields, **kwargs):
        objs = tuple(objs)
        identity_change = bool(set(fields) & {'email', 'phone'})
        user_ids = [obj.pk for obj in objs if obj.pk] if identity_change else ()
        if not user_ids:
            return super().bulk_update(objs, fields, **kwargs)
        with transaction.atomic(using=self.db):
            list(
                self.model._base_manager.using(self.db).select_for_update()
                .filter(pk__in=user_ids).order_by('pk').values_list('pk', flat=True),
            )
            token = _USER_BULK_IDENTITY_WRITE.set(True)
            try:
                result = super().bulk_update(objs, fields, **kwargs)
            finally:
                _USER_BULK_IDENTITY_WRITE.reset(token)
            self._invalidate_profiles(user_ids)
            return result


class SafeUserManager(UserManager.from_queryset(SafeUserQuerySet)):
    use_in_migrations = False


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
    objects = SafeUserManager()

    class Meta:
        verbose_name = 'Пользователь'
        verbose_name_plural = 'Пользователи'
        db_table = 'accounts_user'

    def __str__(self):
        return self.get_full_name() or self.username

    def save(self, *args, **kwargs):
        updates = kwargs.get('update_fields')
        identity_change = updates is None or bool(set(updates) & {'email', 'phone'})
        if not identity_change:
            return super().save(*args, **kwargs)
        using = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            if self.pk:
                type(self).objects.using(using).select_for_update().filter(
                    pk=self.pk,
                ).exists()
            result = super().save(*args, **kwargs)
            persisted_identity = type(self).objects.using(using).only(
                'email', 'phone',
            ).get(pk=self.pk)
            profile = WorkerProfile.objects.using(using).select_for_update().filter(
                user_id=self.pk,
            ).first()
            if profile is not None:
                profile._refresh_public_snapshot(private_values=(
                    profile.contact,
                    persisted_identity.email,
                    persisted_identity.phone,
                ))
                # Only derived fields are written, so bypassing the profile
                # override here cannot publish unvalidated source text.
                super(WorkerProfile, profile).save(
                    using=using,
                    update_fields=profile.PUBLIC_DERIVED_FIELDS,
                )
            return result

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
    track_worker_views = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Профиль заказчика'
        verbose_name_plural = 'Профили заказчиков'
        db_table = 'accounts_client_profile'

    def __str__(self):
        return f'Клиент: {self.user}'


class WorkerProfileQuerySet(models.QuerySet):
    """Keep public projections safe for supported bulk write paths."""

    def bulk_create(self, objs, **kwargs):
        objs = list(objs)
        using = self.db
        with transaction.atomic(using=using):
            identities = {
                row.pk: (row.email, row.phone)
                for row in User.objects.using(using).select_for_update().filter(
                    pk__in={obj.user_id for obj in objs if obj.user_id},
                ).order_by('pk').only('pk', 'email', 'phone')
            }
            for obj in objs:
                email, phone = identities.get(obj.user_id, ('', ''))
                obj._refresh_public_snapshot(
                    private_values=(obj.contact, email, phone),
                )
            return super().bulk_create(objs, **kwargs)

    def bulk_update(self, objs, fields, **kwargs):
        fields = set(fields)
        objs = list(objs)
        using = self.db
        with transaction.atomic(using=using):
            if fields & WorkerProfile.PUBLIC_SOURCE_FIELDS:
                identities = {
                    row.pk: (row.email, row.phone)
                    for row in User.objects.using(using).select_for_update().filter(
                        pk__in={obj.user_id for obj in objs if obj.user_id},
                    ).order_by('pk').only('pk', 'email', 'phone')
                }
                persisted_profiles = {
                    row.pk: row
                    for row in self.select_for_update().filter(
                        pk__in={obj.pk for obj in objs if obj.pk},
                    ).order_by('pk')
                }
                for obj in objs:
                    persisted = persisted_profiles.get(obj.pk)
                    source_values = {
                        name: getattr(persisted, name)
                        for name in WorkerProfile.PUBLIC_SNAPSHOT_SOURCE_FIELDS
                    } if persisted is not None else {}
                    source_values.update({
                        name: getattr(obj, name)
                        for name in fields & WorkerProfile.PUBLIC_SNAPSHOT_SOURCE_FIELDS
                    })
                    email, phone = identities.get(obj.user_id, ('', ''))
                    obj._refresh_public_snapshot(
                        private_values=(
                            source_values.get('contact', obj.contact), email, phone,
                        ),
                        source_values=source_values,
                    )
                fields.update(WorkerProfile.PUBLIC_DERIVED_FIELDS)
            token = _PROFILE_BULK_SNAPSHOT_WRITE.set(True)
            try:
                return super().bulk_update(objs, list(fields), **kwargs)
            finally:
                _PROFILE_BULK_SNAPSHOT_WRITE.reset(token)

    def update(self, **kwargs):
        if (
            set(kwargs) & WorkerProfile.PUBLIC_SOURCE_FIELDS
            and not _PROFILE_BULK_SNAPSHOT_WRITE.get()
        ):
            kwargs.update({
                'public_display_name_snapshot': '',
                'public_description_snapshot': '',
                'public_pricing_details_snapshot': '',
                'public_working_hours_snapshot': '',
                'searchable_display_name': '',
                'searchable_description': '',
                'public_content_safe': False,
                'public_content_policy_version': 0,
            })
        return super().update(**kwargs)


class WorkerProfile(models.Model):
    """One professional/company card. Draft until explicit owner publication."""

    PUBLIC_SOURCE_FIELDS = frozenset({
        'display_name', 'description', 'pricing_details', 'working_hours',
        'contact', 'user', 'user_id',
    })
    PUBLIC_SNAPSHOT_SOURCE_FIELDS = frozenset({
        'display_name', 'description', 'pricing_details', 'working_hours',
        'contact',
    })
    PUBLIC_DERIVED_FIELDS = frozenset({
        'public_display_name_snapshot', 'public_description_snapshot',
        'public_pricing_details_snapshot', 'public_working_hours_snapshot',
        'searchable_display_name', 'searchable_description',
        'public_content_safe', 'public_content_policy_version',
    })
    objects = WorkerProfileQuerySet.as_manager()

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
    # Denormalized contact-free search data. Never query raw display_name or
    # description for anonymous directory keywords (including ranking).
    searchable_display_name = models.CharField(
        max_length=120, blank=True, default='', editable=False,
    )
    searchable_description = models.TextField(
        blank=True, default='', editable=False,
    )
    public_content_safe = models.BooleanField(
        default=False, editable=False, db_index=True,
        verbose_name=_('Публичный текст прошёл защитную проверку'),
    )
    public_content_policy_version = models.PositiveSmallIntegerField(
        default=0, editable=False, db_index=True,
    )
    public_display_name_snapshot = models.CharField(
        max_length=120, blank=True, default='', editable=False,
    )
    public_description_snapshot = models.TextField(
        blank=True, default='', editable=False,
    )
    public_pricing_details_snapshot = models.CharField(
        max_length=240, blank=True, default='', editable=False,
    )
    public_working_hours_snapshot = models.CharField(
        max_length=200, blank=True, default='', editable=False,
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
            models.Index(
                fields=[
                    'is_published', 'public_content_safe',
                    'public_content_policy_version', 'city',
                ],
                name='worker_safe_public_idx',
            ),
        ]

    @property
    def public_display_name(self):
        """Canonical persisted representation for every public consumer."""
        if self._has_current_public_snapshot():
            return self.public_display_name_snapshot or (MARKER if self.display_name else '')
        return MARKER

    @property
    def public_description(self):
        if not self._has_current_public_snapshot():
            return MARKER
        return self.public_description_snapshot or (MARKER if self.description else '')

    @property
    def public_pricing_details(self):
        if not self._has_current_public_snapshot():
            return MARKER
        return self.public_pricing_details_snapshot or (MARKER if self.pricing_details else '')

    @property
    def public_working_hours(self):
        if not self._has_current_public_snapshot():
            return MARKER
        return self.public_working_hours_snapshot or (MARKER if self.working_hours else '')

    def _has_current_public_snapshot(self):
        return bool(
            self.public_content_safe
            and self.public_content_policy_version == POLICY_VERSION
        )

    def _refresh_public_snapshot(self, *, private_values=None, source_values=None):
        source_values = source_values or {}

        def source(name):
            return source_values.get(name, getattr(self, name))
        if private_values is None:
            private_values = (
                source('contact'),
                getattr(self.user, 'email', ''),
                getattr(self.user, 'phone', ''),
            )
        snapshot = build_fail_closed_profile_snapshot(
            display_name=source('display_name'),
            description=source('description'),
            pricing_details=source('pricing_details'),
            working_hours=source('working_hours'),
            private_values=private_values,
        )
        self.public_display_name_snapshot = snapshot['display_name'][:120]
        self.public_description_snapshot = snapshot['description']
        self.public_pricing_details_snapshot = snapshot['pricing_details'][:240]
        self.public_working_hours_snapshot = snapshot['working_hours'][:200]
        self.searchable_display_name = ' '.join(
            self.public_display_name_snapshot.split(),
        )[:120]
        self.searchable_description = ''
        self.public_content_safe = True
        self.public_content_policy_version = POLICY_VERSION

    def save(self, *args, **kwargs):
        """Synchronize public search fields on normal edits and owner services.

        Description text is deliberately excluded from keyword search.  Search
        uses a safe name plus curated categories/services. QuerySet.update and
        bulk_create bypass save; the migration backfills legacy rows.
        """
        using = kwargs.get('using') or router.db_for_write(type(self), instance=self)
        with transaction.atomic(using=using):
            identity = User.objects.using(using).select_for_update().only(
                'email', 'phone',
            ).get(pk=self.user_id)
            persisted = None
            if self.pk:
                persisted = type(self).objects.using(using).select_for_update().filter(
                    pk=self.pk,
                ).first()
            updates = kwargs.get('update_fields')
            if updates is None:
                self._refresh_public_snapshot(private_values=(
                    self.contact, identity.email, identity.phone,
                ))
            else:
                updates = set(updates)
                if updates & self.PUBLIC_SOURCE_FIELDS:
                    source_values = {
                        name: getattr(persisted, name)
                        for name in self.PUBLIC_SNAPSHOT_SOURCE_FIELDS
                    } if persisted is not None else {}
                    source_values.update({
                        name: getattr(self, name)
                        for name in updates & self.PUBLIC_SNAPSHOT_SOURCE_FIELDS
                    })
                    self._refresh_public_snapshot(
                        private_values=(
                            source_values.get('contact', self.contact),
                            identity.email,
                            identity.phone,
                        ),
                        source_values=source_values,
                    )
                    updates.update(self.PUBLIC_DERIVED_FIELDS)
                kwargs['update_fields'] = updates
            return super().save(*args, **kwargs)

    def __str__(self):
        return f'Мастер: {self.user}'

class WorkerPortfolioPhoto(models.Model):
    """Worker-owned image with opaque, private storage and opt-in public access."""

    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.PROTECT, related_name='portfolio_photos',
    )
    file_key = models.CharField(max_length=96, unique=True)
    caption = models.CharField(max_length=300, blank=True, default='')
    public_caption_snapshot = models.CharField(
        max_length=300, blank=True, default='', editable=False,
    )
    public_content_safe = models.BooleanField(default=False, editable=False)
    public_content_policy_version = models.PositiveSmallIntegerField(
        default=0, editable=False,
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_public = models.BooleanField(default=False)
    rights_confirmed_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def public_caption(self):
        if (
            self.public_content_safe
            and self.public_content_policy_version == POLICY_VERSION
        ):
            return self.public_caption_snapshot or (MARKER if self.caption else '')
        return MARKER

    def save(self, *args, **kwargs):
        updates = kwargs.get('update_fields')
        if updates is None or 'caption' in set(updates):
            snapshot = build_caption_snapshot(self.caption)
            self.public_caption_snapshot = snapshot or ''
            self.public_content_safe = True
            self.public_content_policy_version = POLICY_VERSION
            if updates is not None:
                updates = set(updates)
                updates.update({
                    'public_caption_snapshot', 'public_content_safe',
                    'public_content_policy_version',
                })
                kwargs['update_fields'] = updates
        return super().save(*args, **kwargs)

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

class WorkerProfileView(models.Model):
    """Opt-in private history; never used for a public ranking or counter."""

    client = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='viewed_workers',
    )
    worker = models.ForeignKey(
        WorkerProfile, on_delete=models.CASCADE, related_name='viewer_history',
    )
    last_viewed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = 'accounts_worker_profile_view'
        constraints = [
            models.UniqueConstraint(
                fields=['client', 'worker'],
                name='accounts_unique_private_worker_view',
            ),
        ]
        indexes = [
            models.Index(
                fields=['client', '-last_viewed_at'],
                name='accounts_view_owner_recent_idx',
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
