from django.conf import settings
from django.db import models
from django.utils.translation import gettext as _


class Notification(models.Model):
    """Внутреннее уведомление пользователя."""

    class Type(models.TextChoices):
        ORDER_CREATED = 'order_created', 'Заявка создана'
        NEW_RESPONSE = 'new_response', 'Новый отклик'
        RESPONSE_ACCEPTED = 'response_accepted', 'Вас выбрали'
        RESPONSE_REJECTED = 'response_rejected', 'Выбран другой мастер'
        ORDER_CANCELLED = 'order_cancelled', 'Заявка отменена'
        ORDER_COMPLETED = 'order_completed', 'Заявка завершена'
        REVIEW_CREATED = 'review_created', 'Новый отзыв'
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
    is_read = models.BooleanField(default=False, verbose_name='Прочитано')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создано')
    read_at = models.DateTimeField(null=True, blank=True, verbose_name='Прочитано в')

    class Meta:
        verbose_name = 'Уведомление'
        verbose_name_plural = 'Уведомления'
        db_table = 'notifications_notification'
        ordering = ['-created_at']
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
            return self.title
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
