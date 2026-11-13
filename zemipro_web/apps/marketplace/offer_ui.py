"""Explicit three-language offer UI copy; independent of compiled .mo bundles."""
from django.utils.translation import get_language

_COPY = {
    'ru': {
        'offers': 'Отклики мастеров', 'comparison': 'Сравнение предложений',
        'profile': 'Анкета мастера', 'unavailable': 'Анкета недоступна',
        'price': 'Цена', 'fixed': 'Фиксированная', 'range': 'Диапазон',
        'negotiable': 'По договорённости', 'method': 'Способ расчёта',
        'timeline': 'Срок выполнения', 'terms': 'Условия', 'message': 'Сообщение',
        'rating': 'Оценка', 'no_ratings': 'Пока нет отзывов',
        'reviews': 'отзывов', 'status': 'Статус', 'select': 'Выбрать мастера',
        'viewed': 'Отметить просмотренным', 'negotiate': 'Обсудить условия',
        'reject': 'Отклонить', 'withdraw': 'Отозвать',
        'edit': 'Изменить предложение', 'submit': 'Отправить предложение',
        'save': 'Сохранить изменения', 'back': 'Назад',
        'sent': 'Отправлено', 'pending': 'Ожидает',
        'negotiating': 'Обсуждается', 'accepted': 'Выбрано',
        'rejected': 'Отклонено', 'withdrawn': 'Отозвано',
        'expired': 'Истекло', 'cancelled': 'Отменено',
        'amount_min': 'Сумма, ₪', 'amount_max': 'До, ₪',
    },
    'en': {
        'offers': 'Specialist responses', 'comparison': 'Compare offers',
        'profile': 'Specialist profile', 'unavailable': 'Profile unavailable',
        'price': 'Price', 'fixed': 'Fixed', 'range': 'Range',
        'negotiable': 'Negotiable', 'method': 'Pricing method',
        'timeline': 'Estimated timeline', 'terms': 'Terms', 'message': 'Message',
        'rating': 'Rating', 'no_ratings': 'No reviews yet',
        'reviews': 'reviews', 'status': 'Status', 'select': 'Select specialist',
        'viewed': 'Mark as viewed', 'negotiate': 'Discuss terms',
        'reject': 'Reject', 'withdraw': 'Withdraw',
        'edit': 'Edit offer', 'submit': 'Send offer',
        'save': 'Save changes', 'back': 'Back',
        'sent': 'Sent', 'pending': 'Pending', 'negotiating': 'Negotiating',
        'accepted': 'Selected', 'rejected': 'Rejected',
        'withdrawn': 'Withdrawn', 'expired': 'Expired',
        'cancelled': 'Cancelled', 'amount_min': 'Amount, ₪',
        'amount_max': 'Up to, ₪',
    },
    'he': {
        'offers': 'תגובות בעלי מקצוע', 'comparison': 'השוואת הצעות',
        'profile': 'פרופיל בעל המקצוע', 'unavailable': 'הפרופיל אינו זמין',
        'price': 'מחיר', 'fixed': 'מחיר קבוע', 'range': 'טווח מחירים',
        'negotiable': 'לפי הסכמה', 'method': 'שיטת תמחור',
        'timeline': 'זמן ביצוע משוער', 'terms': 'תנאים', 'message': 'הודעה',
        'rating': 'דירוג', 'no_ratings': 'אין חוות דעת עדיין',
        'reviews': 'חוות דעת', 'status': 'מצב', 'select': 'בחירת בעל מקצוע',
        'viewed': 'סימון כנצפה', 'negotiate': 'דיון בתנאים',
        'reject': 'דחייה', 'withdraw': 'משיכת ההצעה',
        'edit': 'עריכת הצעה', 'submit': 'שליחת הצעה',
        'save': 'שמירת שינויים', 'back': 'חזרה',
        'sent': 'נשלח', 'pending': 'ממתין', 'negotiating': 'בדיון',
        'accepted': 'נבחר', 'rejected': 'נדחה',
        'withdrawn': 'נמשך', 'expired': 'פג תוקף',
        'cancelled': 'בוטל', 'amount_min': 'סכום, ₪',
        'amount_max': 'עד, ₪',
    },
}


def offer_copy():
    return _COPY.get((get_language() or 'ru').split('-')[0], _COPY['ru'])
