from django.conf import settings
from django.db import models


class Complaint(models.Model):
    """Жалоба на пользователя или контент."""

    class Reason(models.TextChoices):
        SPAM = 'spam', 'Спам'
        FRAUD = 'fraud', 'Мошенничество'
        INAPPROPRIATE = 'inappropriate', 'Неприемлемый контент'
        FAKE = 'fake', 'Фейковый профиль'
        BAD_SERVICE = 'bad_service', 'Плохое качество услуги'
        OTHER = 'other', 'Другое'

    class Status(models.TextChoices):
        PENDING = 'pending', 'На рассмотрении'
        RESOLVED = 'resolved', 'Рассмотрена'
        DISMISSED = 'dismissed', 'Отклонена'

    reporter = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='complaints_filed', verbose_name='Кто пожаловался'
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, blank=True, related_name='complaints_received',
        verbose_name='На кого жалоба'
    )
    target_order = models.ForeignKey(
        'marketplace.Order', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='complaints',
        verbose_name='На какой заказ'
    )
    target_rating = models.ForeignKey(
        'marketplace.Rating', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='complaints',
        verbose_name='На какой отзыв'
    )
    target_message = models.ForeignKey(
        'marketplace.Message', on_delete=models.SET_NULL,
        null=True, blank=True, related_name='complaints',
    )
    reason = models.CharField(
        max_length=20, choices=Reason.choices, verbose_name='Причина'
    )
    message = models.TextField(verbose_name='Описание жалобы')
    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.PENDING,
        db_index=True, verbose_name='Статус'
    )
    admin_note = models.TextField(blank=True, default='', verbose_name='Заметка админа')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name='Рассмотрена')

    class Meta:
        verbose_name = 'Жалоба'
        verbose_name_plural = 'Жалобы'
        db_table = 'moderation_complaint'
        ordering = ['-created_at']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=['pending', 'resolved', 'dismissed']),
                name='complaint_status_allowed',
            ),
        ]

    def __str__(self):
        target = self.target_user or self.target_order or '?'
        return f'Жалоба от {self.reporter} на {target} ({self.get_reason_display()})'


class ModerationEvent(models.Model):
    """An append-only minimal trace of verified moderation decisions."""

    class Action(models.TextChoices):
        RESOLVE = 'complaint_resolved', 'Рассмотрена жалоба'
        DISMISS = 'complaint_dismissed', 'Жалоба отклонена'
        BLOCK = 'account_blocked', 'Пользователь заблокирован'
        UNBLOCK = 'account_unblocked', 'Пользователь разблокирован'
        PRIVACY_REVIEW = 'privacy_processing', 'Запрос на рассмотрении'
        PRIVACY_REJECT = 'privacy_rejected', 'Запрос отклонён'
        APPEAL_FILED = 'appeal_filed', 'Апелляция подана'
        APPEAL_ACCEPTED = 'appeal_accepted', 'Апелляция удовлетворена'
        APPEAL_REJECTED = 'appeal_rejected', 'Апелляция отклонена'

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='moderation_actions_performed',
    )
    target_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name='moderation_actions_received',
    )
    complaint = models.ForeignKey(
        Complaint, on_delete=models.PROTECT,
        null=True, blank=True, related_name='audit_events',
    )
    privacy_request = models.ForeignKey(
        'accounts.PrivacyRequest', on_delete=models.PROTECT,
        null=True, blank=True, related_name='audit_events',
    )
    action = models.CharField(max_length=40, choices=Action.choices)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'moderation_event'
        ordering = ['-occurred_at', '-pk']
        permissions = [
            ('moderate_accounts', 'Can block and unblock user accounts'),
            ('review_complaints', 'Can review complaints'),
            ('review_privacy_requests', 'Can review privacy requests'),
        ]
        indexes = [
            models.Index(fields=['target_user', '-occurred_at'],
                         name='moderation_target_time_idx'),
        ]


class ComplaintAppeal(models.Model):
    """One participant-initiated, auditable appeal per decided complaint."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Awaiting review'
        ACCEPTED = 'accepted', 'Granted'
        REJECTED = 'rejected', 'Denied'

    complaint = models.OneToOneField(
        Complaint, on_delete=models.PROTECT, related_name='appeal',
    )
    filed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name='moderation_appeals',
    )
    reason = models.TextField()
    status = models.CharField(
        max_length=12, choices=Status.choices, default=Status.PENDING,
    )
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name='decided_moderation_appeals',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'moderation_complaint_appeal'
        ordering = ['-created_at', '-pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(status__in=['pending', 'accepted', 'rejected']),
                name='moderation_appeal_status_allowed',
            ),
        ]
