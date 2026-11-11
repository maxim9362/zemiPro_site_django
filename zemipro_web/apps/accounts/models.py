from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    """Кастомная модель пользователя с поддержкой ролей и Telegram."""

    class Role(models.TextChoices):
        CLIENT = 'client', 'Заказчик'
        WORKER = 'worker', 'Исполнитель'
        ADMIN = 'admin', 'Администратор'

    telegram_id = models.BigIntegerField(
        unique=True, null=True, blank=True,
        verbose_name='Telegram ID'
    )
    role = models.CharField(
        max_length=10, choices=Role.choices, default=Role.CLIENT,
        verbose_name='Роль'
    )
    phone = models.CharField(
        max_length=20, blank=True, null=True,
        verbose_name='Телефон'
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
        return self.role == self.Role.CLIENT

    @property
    def is_worker(self):
        return self.role == self.Role.WORKER


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
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Профиль заказчика'
        verbose_name_plural = 'Профили заказчиков'
        db_table = 'accounts_client_profile'

    def __str__(self):
        return f'Клиент: {self.user}'


class WorkerProfile(models.Model):
    """Профиль исполнителя (мастера)."""

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
    service_cities = models.ManyToManyField(
        'locations.City', blank=True,
        related_name='service_workers', verbose_name='Города обслуживания',
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

    def __str__(self):
        return f'Мастер: {self.user}'

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
