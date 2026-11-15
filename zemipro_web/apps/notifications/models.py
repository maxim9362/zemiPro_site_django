from django.conf import settings
from django.db import models
from django.utils.translation import get_language, gettext as _


class Notification(models.Model):
    """Внутреннее уведомление пользователя."""

    class Type(models.TextChoices):
        ORDER_CREATED = 'order_created', 'Заявка создана'
        ORDER_UPDATED = 'order_updated', 'Условия заявки изменены'
        NEW_RESPONSE = 'new_response', 'Новый отклик'
        RESPONSE_ACCEPTED = 'response_accepted', 'Вас выбрали'
        RESPONSE_REJECTED = 'response_rejected', 'Выбран другой мастер'
        ORDER_CANCELLED = 'order_cancelled', 'Заявка отменена'
        ORDER_COMPLETED = 'order_completed', 'Заявка завершена'
        REVIEW_CREATED = 'review_created', 'Новый отзыв'
        NEW_MESSAGE = 'new_message', 'Новое сообщение'
        INVITATION = 'invitation', 'Приглашение'
        COMPLAINT = 'complaint', 'Жалоба'
        REVIEW_REPLY = 'review_reply', 'Ответ на отзыв'
        SYSTEM = 'system', 'Системное'

    recipient = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='notifications', verbose_name='Получатель'
    )
    title = models.CharField(max_length=200, verbose_name='Заголовок')
    message = models.TextField(verbose_name='Сообщение')
    notification_type = models.CharField(
        max_length=30, choices=Type.choices, default=Type.SYSTEM,
        db_index=True, verbose_name='Тип'
    )
    related_order = models.ForeignKey(
        'marketplace.Order', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='notifications',
        verbose_name='Связанный заказ'
    )
    related_response = models.ForeignKey(
        'marketplace.Response', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='notifications',
        verbose_name='Связанный отклик'
    )
    order_event = models.ForeignKey(
        'marketplace.OrderDomainEvent', on_delete=models.PROTECT,
        null=True, blank=True, editable=False, related_name='notifications',
    )
    dedupe_key = models.CharField(max_length=120, null=True, blank=True, editable=False)
    is_read = models.BooleanField(default=False, verbose_name='Прочитано')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='Прочитано в')

    class Meta:
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        db_table = 'notifications_notification'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(
                fields=['recipient', 'dedupe_key'], name='notif_recipient_key_unique',
            ),
            models.UniqueConstraint(
                fields=['order_event', 'recipient'],
                name='notif_order_event_recipient_unique',
            ),
        ]
        indexes = [
            models.Index(fields=['recipient', 'is_read'], name='notif_recipient_read_idx'),
            models.Index(fields=['recipient', '-created_at'], name='notif_recipient_created_idx'),
            models.Index(fields=['notification_type'], name='notif_type_idx'),
            models.Index(fields=['-created_at'], name='notif_created_idx'),
        ]

    @property
    def localized_title(self):
        """Localize known system events at display time, not at write time."""
        if self.notification_type == self.Type.SYSTEM:
            return _(self.title)
        if self.notification_type == self.Type.ORDER_UPDATED:
            language = (get_language() or 'ru').split('-')[0]
            return {
                'ru': 'Условия заявки изменены',
                'en': 'Request details updated',
                'he': 'פרטי הבקשה עודכנו',
            }.get(language, 'Условия заявки изменены')
        title_map = {
            self.Type.ORDER_CREATED: 'Заявка создана',
            self.Type.NEW_RESPONSE: 'Новый отклик',
            self.Type.RESPONSE_ACCEPTED: 'Вас выбрали',
            self.Type.RESPONSE_REJECTED: 'Выбран другой мастер',
            self.Type.ORDER_CANCELLED: 'Заявка отменена',
            self.Type.ORDER_COMPLETED: 'Заявка завершена',
            self.Type.REVIEW_CREATED: 'Новый отзыв',
        }
        return _(title_map.get(self.notification_type, self.title))

    @property
    def localized_message(self):
        """Reconstruct only predefined notifications without changing stored text."""
        if not self.related_order_id:
            return self.message
        if self.notification_type == self.Type.ORDER_UPDATED:
            language = (get_language() or 'ru').split('-')[0]
            message = {
                'ru': 'Условия заявки №{number} изменены.',
                'en': 'The details of request #{number} have changed.',
                'he': 'פרטי הבקשה מס׳ {number} עודכנו.',
            }.get(language, 'Условия заявки №{number} изменены.')
            return message.format(number=self.related_order_id)
        templates = {
            self.Type.ORDER_CREATED: 'Ваша заявка №%(number)s успешно создана. Мастера смогут откликнуться на неё.',
            self.Type.NEW_RESPONSE: 'Мастер откликнулся на вашу заявку №%(number)s.',
            self.Type.RESPONSE_ACCEPTED: 'Клиент выбрал вас исполнителем по заявке №%(number)s.',
            self.Type.RESPONSE_REJECTED: 'По заявке №%(number)s клиент выбрал другого мастера.',
            self.Type.ORDER_CANCELLED: 'Заявка №%(number)s, на которую вы откликались, была отменена клиентом.',
            self.Type.ORDER_COMPLETED: 'Клиент отметил заявку №%(number)s как выполненную.',
            self.Type.REVIEW_CREATED: 'Клиент оставил отзыв по заявке №%(number)s.',
        }
        message_id = templates.get(self.notification_type)
        if message_id is None:
            return self.message
        return _(message_id) % {'number': self.related_order_id}

    def __str__(self):
        return f'{self.title} → {self.recipient}'


class NotificationPreference(models.Model):
    """Only optional notices may be muted; security notices are mandatory."""

    recipient = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE,
        related_name='notification_preference',
    )
    in_app_optional = models.BooleanField(default=True)
    email_optional = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'notifications_preference'


class NotificationDelivery(models.Model):
    """Durable email outbox; sending is never performed in a business transaction."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        RETRY = 'retry', 'Retry'
        DELIVERED = 'delivered', 'Delivered'
        DEAD = 'dead', 'Dead letter'
        SUPPRESSED = 'suppressed', 'Suppressed'

    notification = models.ForeignKey(
        Notification, on_delete=models.PROTECT, related_name='deliveries',
    )
    channel = models.CharField(max_length=12, default='email')
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING,
    )
    attempts = models.PositiveSmallIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=models.functions.Now)
    last_error_code = models.CharField(max_length=40, blank=True, default='')
    delivered_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'notifications_delivery'
        constraints = [
            models.UniqueConstraint(
                fields=['notification', 'channel'], name='notif_delivery_unique',
            ),
            models.CheckConstraint(
                condition=models.Q(
                    status__in=['pending', 'retry', 'delivered', 'dead', 'suppressed'],
                ),
                name='notif_delivery_status_valid',
            ),
        ]
        indexes = [
            models.Index(
                fields=['status', 'next_attempt_at'], name='notif_delivery_due_idx',
            ),
        ]
