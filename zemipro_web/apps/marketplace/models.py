from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Category(models.Model):
    """Категория услуги (сантехника, электрика и т.д.)."""

    name_ru = models.CharField(max_length=100, verbose_name='Название (рус)')
    name_he = models.CharField(max_length=100, blank=True, default='', verbose_name='Название (иврит)')
    name_en = models.CharField(max_length=100, blank=True, default='', verbose_name='Название (англ)')
    slug = models.SlugField(unique=True, verbose_name='Slug')
    emoji = models.CharField(max_length=10, blank=True, default='', verbose_name='Эмодзи')
    description = models.TextField(blank=True, default='', verbose_name='Описание')
    is_active = models.BooleanField(default=True, verbose_name='Активна')
    sort_order = models.PositiveIntegerField(default=0, verbose_name='Порядок сортировки')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        verbose_name = 'Категория'
        verbose_name_plural = 'Категории'
        db_table = 'marketplace_category'
        ordering = ['sort_order', 'name_ru']

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

    def __str__(self):
        return f'{self.category.name_ru} → {self.name_ru}'


class Order(models.Model):
    """Заявка на услугу от заказчика."""

    class Status(models.TextChoices):
        NEW = 'new', 'В обработке'
        IN_PROGRESS = 'in_progress', 'В процессе'
        COMPLETED = 'completed', 'Выполнен'
        CANCELLED = 'cancelled', 'Отменён'

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
        max_length=20, choices=Status.choices, default=Status.NEW,
        db_index=True, verbose_name='Статус'
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

    def __str__(self):
        return f'Заказ #{self.pk} — {self.category.name_ru} ({self.get_status_display()})'


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
        'accounts.User', on_delete=models.CASCADE,
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
            )
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
        'accounts.User', on_delete=models.CASCADE,
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
