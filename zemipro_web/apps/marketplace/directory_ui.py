"""Stage 05 directory text that works before compiling PO/MO catalogs."""
from django.utils.translation import get_language

COPY = {
    'ru': {
        'views_opt_in': 'Сохранять историю просмотренных специалистов только в моём кабинете',
        'history_heading': 'Недавно просмотренные специалисты',
        'history_empty': 'История просмотров пока пуста.',
        'history_disabled': 'История просмотров выключена. Включить можно в настройках.',
        'history_clear': 'Очистить историю просмотров',
        'history_cleared': 'История просмотров очищена.',
        'favorites_empty': 'Пока нет избранных специалистов.',
        'empty_help': 'Попробуйте изменить фильтры или создать заявку.',
        'invalid_help': 'Исправьте ошибки фильтров или сбросьте их.',
        'no_reviews': 'Пока нет отзывов',
        'privacy_hint': 'Не указывайте личные контакты и точный адрес в публичном описании.',
    },
    'en': {
        'views_opt_in': 'Save my viewed specialists only in my account',
        'history_heading': 'Recently viewed specialists',
        'history_empty': 'No viewing history yet.',
        'history_disabled': 'Viewing history is off. Enable it in settings.',
        'history_clear': 'Clear viewing history',
        'history_cleared': 'Viewing history cleared.',
        'favorites_empty': 'No saved specialists yet.',
        'empty_help': 'Try changing the filters or create a request.',
        'invalid_help': 'Fix the invalid filters or reset them.',
        'no_reviews': 'No reviews yet',
        'privacy_hint': 'Do not include personal contacts or exact addresses in public descriptions.',
    },
    'he': {
        'views_opt_in': 'שמירת בעלי המקצוע שבהם צפיתי בחשבון שלי בלבד',
        'history_heading': 'בעלי מקצוע שנצפו לאחרונה',
        'history_empty': 'אין עדיין היסטוריית צפייה.',
        'history_disabled': 'היסטוריית הצפייה כבויה. אפשר להפעיל אותה בהגדרות.',
        'history_clear': 'מחיקת היסטוריית הצפייה',
        'history_cleared': 'היסטוריית הצפייה נמחקה.',
        'favorites_empty': 'עדיין אין בעלי מקצוע שמורים.',
        'empty_help': 'נסו לשנות את המסננים או ליצור בקשה.',
        'invalid_help': 'תקנו את המסננים הלא תקינים או אפסו אותם.',
        'no_reviews': 'עדיין אין ביקורות',
        'privacy_hint': 'אין לפרסם פרטי קשר או כתובות מדויקות בתיאור ציבורי.',
    },
}


def directory_copy(language=None):
    code = (language or get_language() or 'ru').split('-')[0]
    return COPY.get(code, COPY['ru'])
