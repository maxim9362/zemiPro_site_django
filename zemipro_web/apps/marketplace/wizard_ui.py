"""Stage 04.2 wizard copy in RU/EN/HE; independent of compiled PO releases."""
from django.utils.translation import get_language


COPY = {
    'ru': {
        'throttled': 'Слишком много действий. Повторите позже.',
        'draft': 'Черновик', 'edit': 'Редактировать условия',
        'withdraw': 'Снять с публикации', 'duplicate': 'Создать копию',
        'history': 'История заявки', 'conditions_changed': 'изменены условия',
        'edit_saved': 'Изменения сохранены', 'save_changes': 'Сохранить изменения',
        'photos': 'Добавьте до 5 фотографий (JPEG, PNG, WebP; до 5 МБ каждая). Они очищаются от метаданных.',
        'photo_input': 'Фотографии', 'photo_access': 'Кто сможет увидеть фотографии',
        'photo_private': 'Только я и уполномоченный модератор',
        'photo_assignee': 'Только я и выбранный исполнитель',
        'photo_public': 'Любой посетитель после публикации заявки',
        'photo_consent': 'Я понимаю, что содержимое этих фотографий станет публичным.',
        'photos_saved': 'Сохранённые фотографии', 'delete_photo': 'Удалить фотографию',
        'photo_notice': 'Не загружайте документы, номера телефонов и точный адрес.',
        'area_private': 'Укажите только район, без номера дома, улицы и контактов.',
        'heading': 'Создание заявки', 'intro': 'Сохраните черновик и вернитесь позже.',
        'step1': 'Выбор услуги', 'step2': 'Вопросы об услуге',
        'step3': 'Город и формат', 'step4': 'Дата и срочность',
        'step5': 'Бюджет', 'step6': 'Описание и фотографии',
        'step7': 'Настройки связи', 'step8': 'Проверка и публикация',
        'category': 'Категория', 'service': 'Услуга', 'city': 'Город',
        'mode': 'Формат выполнения', 'onsite': 'На месте', 'online': 'Онлайн',
        'area': 'Примерный район (не точный адрес)', 'date': 'Желаемая дата',
        'urgency': 'Срочность', 'normal': 'Обычная', 'soon': 'В ближайшие дни',
        'urgent': 'Срочно', 'price_type': 'Как указать цену',
        'fixed': 'Фиксированная', 'range': 'Диапазон', 'negotiable': 'Договорная',
        'amount_min': 'Цена / минимум (₪)', 'amount_max': 'Максимум (₪)',
        'description': 'Дополнительное описание', 'display_name': 'Как к вам обращаться',
        'chat_ack': 'Связь только через приватный чат. Телефон и точный адрес передаются по вашему решению.',
        'confirm': 'Я проверил(а) данные заявки и хочу опубликовать её.',
        
        'privacy': 'Точный адрес и номер телефона не запрашиваются и не публикуются.',
        'next': 'Сохранить и продолжить', 'back': 'Назад', 'publish': 'Опубликовать',
        'drafts': 'Мои черновики', 'resume': 'Продолжить', 'summary': 'Ваши ответы',
        'no_questions': 'Для этой услуги дополнительных вопросов нет.',
        'no_date': 'Дата не указана', 'not_set': 'Не указано',
        'step_of': 'Шаг', 'of': 'из', 'no_service': 'Выберите активную услугу.',
        'changed': 'Опросник изменился. Вернитесь к вопросам и сохраните ответы заново.',
        'incomplete': 'Сначала завершите предыдущие шаги.',
        'not_eligible': 'Аккаунт недоступен для создания заказов.',
        'no_city': 'Сейчас нет доступного города для публикации.',
        'no_description': 'Добавьте описание или ответьте на вопросы услуги.',
    },
    'en': {
        'throttled': 'Too many actions. Please try later.',
        'draft': 'Draft', 'edit': 'Edit terms',
        'withdraw': 'Withdraw publication', 'duplicate': 'Create a copy',
        'history': 'Request history', 'conditions_changed': 'terms changed',
        'edit_saved': 'Changes saved', 'save_changes': 'Save changes',
        'photos': 'Add up to 5 photos (JPEG, PNG, WebP; up to 5 MB each). Metadata is removed.',
        'photo_input': 'Photos', 'photo_access': 'Who can see these photos',
        'photo_private': 'Only me and an authorized moderator',
        'photo_assignee': 'Only me and the selected professional',
        'photo_public': 'Anyone after the request is published',
        'photo_consent': 'I understand that the contents of these photos will be public.',
        'photos_saved': 'Saved photos', 'delete_photo': 'Delete photo',
        'photo_notice': 'Do not upload documents, phone numbers or a precise address.',
        'area_private': 'Enter only an approximate area, without streets, numbers or contacts.',
        'heading': 'Create a request', 'intro': 'Save a draft and come back later.',
        'step1': 'Choose a service', 'step2': 'Service questions',
        'step3': 'City and delivery', 'step4': 'Date and urgency',
        'step5': 'Budget', 'step6': 'Description and photos',
        'step7': 'Contact preferences', 'step8': 'Review and publish',
        'category': 'Category', 'service': 'Service', 'city': 'City',
        'mode': 'Delivery mode', 'onsite': 'On-site', 'online': 'Online',
        'area': 'Approximate area (not your address)', 'date': 'Preferred date',
        'urgency': 'Urgency', 'normal': 'Standard', 'soon': 'In the next few days',
        'urgent': 'Urgent', 'price_type': 'Price type',
        'fixed': 'Fixed', 'range': 'Range', 'negotiable': 'Negotiable',
        'amount_min': 'Price / minimum (₪)', 'amount_max': 'Maximum (₪)',
        'description': 'Additional details', 'display_name': 'Your preferred name',
        'chat_ack': 'Contact by private chat only. Sharing your phone number or exact address is your choice.',
        'confirm': 'I have reviewed this request and want to publish it.',
        
        'privacy': 'We do not request or publish your precise address or phone number.',
        'next': 'Save and continue', 'back': 'Back', 'publish': 'Publish',
        'drafts': 'My drafts', 'resume': 'Continue', 'summary': 'Your answers',
        'no_questions': 'No additional questions for this service.',
        'no_date': 'No date selected', 'not_set': 'Not specified',
        'step_of': 'Step', 'of': 'of', 'no_service': 'Choose an active service.',
        'changed': 'The questionnaire has changed. Return to the questions and save your answers again.',
        'incomplete': 'Please finish earlier steps first.',
        'not_eligible': 'This account cannot create requests.',
        'no_city': 'No city is currently available for publication.',
        'no_description': 'Add a description or answer the service questions.',
    },
    'he': {
        'throttled': 'יותר מדי פעולות. יש לנסות שוב מאוחר יותר.',
        'draft': 'טיוטה', 'edit': 'עריכת פרטי הבקשה',
        'withdraw': 'ביטול פרסום', 'duplicate': 'יצירת עותק',
        'history': 'היסטוריית הבקשה', 'conditions_changed': 'פרטים השתנו',
        'edit_saved': 'השינויים נשמרו', 'save_changes': 'שמירת שינויים',
        'photos': 'עד 5 תמונות (JPEG, PNG, WebP; עד 5MB לכל תמונה). נתוני המטא מוסרים.',
        'photo_input': 'תמונות', 'photo_access': 'מי יכול לראות את התמונות',
        'photo_private': 'רק אני ומנהל מורשה',
        'photo_assignee': 'רק אני ובעל המקצוע שנבחר',
        'photo_public': 'כל אחד לאחר פרסום הבקשה',
        'photo_consent': 'אני מבין/ה שתוכן התמונות יהיה גלוי לציבור.',
        'photos_saved': 'תמונות שנשמרו', 'delete_photo': 'מחיקת תמונה',
        'photo_notice': 'אין להעלות מסמכים, מספרי טלפון או כתובת מדויקת.',
        'area_private': 'יש לציין אזור משוער בלבד ללא רחוב, מספר בית או פרטי קשר.',
        'heading': 'יצירת בקשת שירות', 'intro': 'אפשר לשמור טיוטה ולחזור אליה בהמשך.',
        'step1': 'בחירת שירות', 'step2': 'שאלות על השירות',
        'step3': 'עיר ואופן הביצוע', 'step4': 'תאריך ודחיפות',
        'step5': 'תקציב', 'step6': 'תיאור ותמונות',
        'step7': 'העדפות קשר', 'step8': 'בדיקה ופרסום',
        'category': 'קטגוריה', 'service': 'שירות', 'city': 'עיר',
        'mode': 'אופן ביצוע', 'onsite': 'במקום', 'online': 'מקוון',
        'area': 'אזור משוער (לא כתובת מדויקת)', 'date': 'תאריך רצוי',
        'urgency': 'דחיפות', 'normal': 'רגיל', 'soon': 'בימים הקרובים',
        'urgent': 'דחוף', 'price_type': 'סוג מחיר',
        'fixed': 'קבוע', 'range': 'טווח', 'negotiable': 'לפי סיכום',
        'amount_min': 'מחיר / מינימום (₪)', 'amount_max': 'מקסימום (₪)',
        'description': 'פרטים נוספים', 'display_name': 'איך לפנות אליך',
        'chat_ack': 'התקשורת בצ׳אט פרטי בלבד. שיתוף מספר טלפון או כתובת מדויקת נתון לבחירתך.',
        'confirm': 'בדקתי את פרטי הבקשה וברצוני לפרסם אותה.',
        
        'privacy': 'לא נבקש ולא נפרסם כתובת מדויקת או מספר טלפון.',
        'next': 'שמירה והמשך', 'back': 'חזרה', 'publish': 'פרסום',
        'drafts': 'הטיוטות שלי', 'resume': 'המשך',
        'summary': 'התשובות שלך', 'no_questions': 'אין שאלות נוספות לשירות הזה.',
        'no_date': 'לא נבחר תאריך', 'not_set': 'לא צוין',
        'step_of': 'שלב', 'of': 'מתוך', 'no_service': 'יש לבחור שירות פעיל.',
        'changed': 'השאלון השתנה. יש לחזור לשאלות ולשמור את התשובות מחדש.',
        'incomplete': 'יש להשלים תחילה את השלבים הקודמים.',
        'not_eligible': 'החשבון אינו מורשה ליצור בקשות.',
        'no_city': 'אין כרגע עיר זמינה לפרסום.',
        'no_description': 'יש להוסיף תיאור או להשיב על שאלות השירות.',
    },
}


# Stable status codes are translated at render time instead of relying on
# compiled PO catalogues that may not yet contain the new lifecycle values.
STATUS_LABELS = {
    'ru': {
        'draft': 'Черновик', 'published': 'Опубликован',
        'in_discussion': 'Обсуждение', 'assigned': 'Исполнитель выбран',
        'in_progress': 'В процессе', 'completed': 'Выполнен',
        'cancelled': 'Отменён', 'expired': 'Истёк срок', 'disputed': 'Спор',
    },
    'en': {
        'draft': 'Draft', 'published': 'Published',
        'in_discussion': 'In discussion', 'assigned': 'Professional selected',
        'in_progress': 'In progress', 'completed': 'Completed',
        'cancelled': 'Cancelled', 'expired': 'Expired', 'disputed': 'Disputed',
    },
    'he': {
        'draft': 'טיוטה', 'published': 'פורסמה',
        'in_discussion': 'בדיון', 'assigned': 'נבחר בעל מקצוע',
        'in_progress': 'בתהליך', 'completed': 'הושלמה',
        'cancelled': 'בוטלה', 'expired': 'פג תוקף', 'disputed': 'במחלוקת',
    },
}

ACTION_LABELS = {
    'ru': {'edited': 'Условия изменены', 'duplicated': 'Создана копия'},
    'en': {'edited': 'Terms updated', 'duplicated': 'Copy created'},
    'he': {'edited': 'פרטי הבקשה עודכנו', 'duplicated': 'נוצר עותק'},
}


def localized_order_status(status):
    lang = (get_language() or 'ru').split('-')[0]
    return STATUS_LABELS.get(lang, STATUS_LABELS['ru']).get(status, status)


def localized_order_action(action):
    lang = (get_language() or 'ru').split('-')[0]
    return ACTION_LABELS.get(lang, ACTION_LABELS['ru']).get(action, action)


def wizard_copy():
    lang = (get_language() or 'ru').split('-')[0]
    return COPY.get(lang, COPY['ru'])
