"""Stage 02.5 optional curated pilot questionnaires (review all translations)."""

def tr(ru, en, he):
    return {'ru': ru, 'en': en, 'he': he}


def option(value, ru, en, he):
    return {'value': value, 'labels': tr(ru, en, he)}


def question(key, kind, ru, en, he, *, required=False, options=None, depends=None):
    data = {
        'key': key, 'type': kind, 'labels': tr(ru, en, he),
        'required': required,
    }
    if options:
        data['options'] = options
    if depends:
        data['depends_on'] = depends
    return data


DEMO_QUESTIONNAIRES = [
    ('plumbing', 'leak-repair', [
        question('issue', 'single', 'Где протечка?', 'Where is the leak?',
                 'איפה הנזילה?', required=True, options=[
                     option('faucet', 'Кран', 'Faucet', 'ברז'),
                     option('pipe', 'Труба', 'Pipe', 'צינור'),
                     option('toilet', 'Унитаз', 'Toilet', 'אסלה'),
                 ]),
        question('urgent', 'boolean', 'Нужен срочный выезд?',
                 'Is urgent service required?', 'נדרש שירות דחוף?', required=True),
        question('access', 'text', 'Дополнительные сведения',
                 'Additional details', 'פרטים נוספים',
                 depends={'key': 'urgent', 'equals': True}),
    ]),
    ('tutoring', 'math-tutoring', [
        question('level', 'single', 'Уровень ученика', 'Student level',
                 'רמת התלמיד', required=True, options=[
                     option('primary', 'Начальная школа', 'Primary school', 'בית ספר יסודי'),
                     option('secondary', 'Средняя школа', 'Secondary school', 'חטיבת ביניים'),
                     option('high', 'Старшая школа', 'High school', 'תיכון'),
                 ]),
        question('format', 'single', 'Формат занятий', 'Lesson format',
                 'אופן הלימוד', required=True, options=[
                     option('online', 'Онлайн', 'Online', 'מקוון'),
                     option('onsite', 'Лично', 'In person', 'פרונטלי'),
                 ]),
        question('goal', 'text', 'Цель занятий', 'Learning goal',
                 'מטרת הלימוד'),
    ]),
    ('website-development', 'landing-page', [
        question('purpose', 'text', 'Задача сайта', 'Website goal',
                 'מטרת האתר', required=True),
        question('timeline', 'single', 'Желаемый срок', 'Desired timeline',
                 'לוח זמנים רצוי', required=True, options=[
                     option('week', 'До недели', 'Within a week', 'תוך שבוע'),
                     option('month', 'До месяца', 'Within a month', 'תוך חודש'),
                     option('flexible', 'Гибкий', 'Flexible', 'גמיש'),
                 ]),
        question('budget', 'number', 'Ориентировочный бюджет (₪)',
                 'Approximate budget (₪)', 'תקציב משוער (₪)'),
    ]),
    ('event-services', 'event-photography', [
        question('event', 'single', 'Тип мероприятия', 'Event type',
                 'סוג האירוע', required=True, options=[
                     option('wedding', 'Свадьба', 'Wedding', 'חתונה'),
                     option('birthday', 'День рождения', 'Birthday', 'יום הולדת'),
                     option('business', 'Деловое', 'Business', 'עסקי'),
                 ]),
        question('event_date', 'date', 'Дата мероприятия', 'Event date',
                 'תאריך האירוע', required=True),
        question('hours', 'number', 'Длительность (часы)', 'Duration (hours)',
                 'משך האירוע (שעות)'),
        question('extras', 'multiple', 'Дополнительные услуги', 'Extra services',
                 'שירותים נוספים', options=[
                     option('albums', 'Фотоальбом', 'Photo album', 'אלבום תמונות'),
                     option('video', 'Видео', 'Video', 'וידאו'),
                 ], depends={'key': 'event', 'equals': 'wedding'}),
    ]),
]
