"""07.3 durable localized in-app notices and disabled-by-default email outbox."""
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from .models import Notification, NotificationDelivery, NotificationPreference


COPY = {
    'message': {
        'ru': ('Новое сообщение', 'Вам пришло сообщение в ZemiPro.'),
        'en': ('New message', 'You have a new message in ZemiPro.'),
        'he': ('הודעה חדשה', 'קיבלת הודעה חדשה ב-ZemiPro.'),
    },
    'invitation': {
        'ru': ('Приглашение', 'Вам отправлено приглашение по заявке.'),
        'en': ('Invitation', 'You have received a request invitation.'),
        'he': ('הזמנה', 'קיבלת הזמנה לבקשה.'),
    },
    'offer': {
        'ru': ('Новый отклик', 'Получен новый отклик на заявку.'),
        'en': ('New offer', 'A new offer was received for your request.'),
        'he': ('הצעה חדשה', 'התקבלה הצעה חדשה לבקשה.'),
    },
    'assignment': {
        'ru': ('Выбор исполнителя', 'Исполнитель для заявки выбран.'),
        'en': ('Specialist selected', 'A specialist was selected for the request.'),
        'he': ('נבחר בעל מקצוע', 'נבחר בעל מקצוע לבקשה.'),
    },
    'agreement': {
        'ru': ('Изменение условий', 'Условия договорённости изменены.'),
        'en': ('Agreement update', 'The agreement terms have changed.'),
        'he': ('עדכון הסכם', 'תנאי ההסכם השתנו.'),
    },
    'cancellation': {
        'ru': ('Отмена заказа', 'Заявка была отменена.'),
        'en': ('Request cancelled', 'The request has been cancelled.'),
        'he': ('בקשה בוטלה', 'הבקשה בוטלה.'),
    },
    'completion': {
        'ru': ('Завершение работы', 'Работа по заявке завершена.'),
        'en': ('Work completed', 'Work on the request was completed.'),
        'he': ('העבודה הושלמה', 'העבודה בבקשה הושלמה.'),
    },
    'review': {
        'ru': ('Новый отзыв', 'По завершённой работе оставлен отзыв.'),
        'en': ('New review', 'A review was posted for the completed work.'),
        'he': ('ביקורת חדשה', 'פורסמה ביקורת על העבודה שהושלמה.'),
    },
    'review_reply': {
        'ru': ('Ответ на отзыв', 'Специалист ответил на отзыв.'),
        'en': ('Review response', 'The specialist replied to a review.'),
        'he': ('תגובה לביקורת', 'בעל המקצוע הגיב לביקורת.'),
    },
    'complaint': {
        'ru': ('Жалоба', 'По обращению появилась новая информация.'),
        'en': ('Complaint', 'There is an update concerning a report.'),
        'he': ('תלונה', 'יש עדכון לגבי דיווח.'),
    },
}
TYPES = {
    'message': Notification.Type.NEW_MESSAGE,
    'invitation': Notification.Type.INVITATION,
    'offer': Notification.Type.NEW_RESPONSE,
    'assignment': Notification.Type.RESPONSE_ACCEPTED,
    'agreement': Notification.Type.ORDER_UPDATED,
    'cancellation': Notification.Type.ORDER_CANCELLED,
    'completion': Notification.Type.ORDER_COMPLETED,
    'review': Notification.Type.REVIEW_CREATED,
    'review_reply': Notification.Type.REVIEW_REPLY,
    'complaint': Notification.Type.COMPLAINT,
}


def eligible_recipient(user_id):
    return User.objects.filter(
        pk=user_id, is_active=True, is_blocked=False,
        email_verification_required=False,
    ).first()


def set_preferences(*, actor, in_app_optional, email_optional):
    stored = eligible_recipient(actor.pk) if getattr(actor, 'is_authenticated', False) else None
    if stored is None:
        raise PermissionDenied('Notification settings unavailable.')
    with transaction.atomic():
        row, _ = NotificationPreference.objects.select_for_update().get_or_create(
            recipient=stored,
        )
        row.in_app_optional = bool(in_app_optional)
        row.email_optional = bool(email_optional) and stored.email_verified_at is not None
        row.save(update_fields=['in_app_optional', 'email_optional', 'updated_at'])
    return row


@transaction.atomic
def create_domain_notification(*, recipient_id, event_key, event, mandatory=False,
                               related_order=None, related_response=None):
    """One notice per immutable business-event key and recipient, no message body or PII."""
    if event not in COPY or not isinstance(event_key, str) or not (1 <= len(event_key) <= 120):
        raise ValueError('Invalid notification event.')
    user = eligible_recipient(recipient_id)
    if user is None:
        return None, False
    pref = NotificationPreference.objects.filter(recipient_id=user.pk).first()
    if not mandatory and pref is not None and not pref.in_app_optional:
        return None, False
    language = user.preferred_language if user.preferred_language in ('ru', 'en', 'he') else 'ru'
    title, message = COPY[event][language]
    notice, created = Notification.objects.get_or_create(
        recipient=user, dedupe_key=event_key,
        defaults={
            'title': title, 'message': message, 'notification_type': TYPES[event],
            'related_order': related_order, 'related_response': related_response,
        },
    )
    if (created and pref is not None and pref.email_optional
            and user.email_verified_at is not None and bool(user.email)):
        NotificationDelivery.objects.get_or_create(
            notification=notice, channel='email',
        )
    return notice, created


def process_email_outbox(*, limit=20, sender=None):
    """Explicit worker. Provider calls never alter orders, messages or ratings.

    An exhausted item becomes dead-letter; failure diagnostics contain no PII.
    This worker is inert unless the dedicated opt-in deployment flag is on.
    """
    if not getattr(settings, 'ZEMIPRO_STAGE07_EMAIL_ENABLED', False):
        return {'sent': 0, 'retry': 0, 'dead': 0, 'disabled': True}
    from_email = getattr(settings, 'DEFAULT_FROM_EMAIL', '')
    if not from_email:
        return {'sent': 0, 'retry': 0, 'dead': 0, 'disabled': True}
    result = {'sent': 0, 'retry': 0, 'dead': 0, 'disabled': False}
    sender = sender or send_mail
    limit = min(100, max(1, int(limit)))
    for _ in range(limit):
        with transaction.atomic():
            row = NotificationDelivery.objects.select_for_update(skip_locked=True).select_related(
                'notification__recipient',
            ).filter(
                status__in=[NotificationDelivery.Status.PENDING,
                            NotificationDelivery.Status.RETRY],
                next_attempt_at__lte=timezone.now(),
            ).order_by('next_attempt_at', 'pk').first()
            if row is None:
                break
            # Serialize a delivery attempt across workers via row-level locking.
            user = row.notification.recipient
            pref = NotificationPreference.objects.filter(recipient=user).first()
            if (not user.is_active or user.is_blocked or user.email_verification_required
                    or not user.email_verified_at
                    or not user.email or pref is None or not pref.email_optional):
                row.status = NotificationDelivery.Status.SUPPRESSED
                row.last_error_code = 'ineligible'
                row.save(update_fields=['status', 'last_error_code'])
                continue
            row.attempts += 1
            try:
                delivered = sender(
                    row.notification.title, row.notification.message,
                    from_email, [user.email], fail_silently=False,
                )
                if delivered != 1:
                    raise RuntimeError('not_delivered')
            except Exception:
                if row.attempts >= 5:
                    row.status = NotificationDelivery.Status.DEAD
                    result['dead'] += 1
                else:
                    row.status = NotificationDelivery.Status.RETRY
                    row.next_attempt_at = timezone.now() + timedelta(
                        minutes=min(60, 2 ** row.attempts),
                    )
                    result['retry'] += 1
                row.last_error_code = 'provider_unavailable'
                row.save(update_fields=[
                    'attempts', 'status', 'next_attempt_at', 'last_error_code',
                ])
            else:
                row.status = NotificationDelivery.Status.DELIVERED
                row.delivered_at = timezone.now()
                row.last_error_code = ''
                row.save(update_fields=[
                    'attempts', 'status', 'delivered_at', 'last_error_code',
                ])
                result['sent'] += 1
    return result
