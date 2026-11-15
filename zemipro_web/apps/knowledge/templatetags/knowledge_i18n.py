"""Small locale-safe dynamic labels, without editing approved Stage08 templates."""
from django import template
from django.utils.translation import get_language

register = template.Library()

_STATUS = {
    'draft': ('Черновик', 'Draft', 'טיוטה'),
    'pending_review': ('На проверке', 'Awaiting review', 'ממתין לבדיקה'),
    'published': ('Одобрена', 'Approved', 'אושר'),
    'rejected': ('Отклонена', 'Rejected', 'נדחה'),
    'archived': ('Архив', 'Archived', 'בארכיון'),
}
_REASON = {
    'spam': ('Спам', 'Spam', 'ספאם'),
    'private': ('Персональные данные', 'Private information', 'מידע אישי'),
    'dangerous': ('Небезопасный совет', 'Unsafe advice', 'עצה מסוכנת'),
    'copyright': ('Нарушение авторских прав', 'Copyright issue', 'זכויות יוצרים'),
    'other': ('Другое', 'Other', 'אחר'),
}


def _localized(value, mapping):
    language = (get_language() or 'ru').split('-')[0]
    column = {'ru': 0, 'en': 1, 'he': 2}.get(language, 0)
    return mapping.get(str(value), ('', '', ''))[column]


@register.filter
def article_status(value):
    return _localized(value, _STATUS)


@register.filter
def knowledge_report_reason(value):
    return _localized(value, _REASON)
