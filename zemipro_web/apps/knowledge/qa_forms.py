"""Bounded Stage 14.6 forms; all ownership remains in qa_services."""
from django import forms
from django.utils.translation import get_language

from apps.marketplace.models import Category

from .models import ExpertQuestion, KnowledgeQAReport


_TEXT = {
    'ru': {
        'title': 'Краткий вопрос', 'body': 'Подробности', 'category': 'Категория',
        'language': 'Язык вопроса', 'answer': 'Ответ специалиста',
        'reason': 'Причина', 'message': 'Описание жалобы',
    },
    'en': {
        'title': 'Question title', 'body': 'Details', 'category': 'Category',
        'language': 'Question language', 'answer': 'Specialist answer',
        'reason': 'Reason', 'message': 'Report details',
    },
    'he': {
        'title': 'כותרת השאלה', 'body': 'פרטים', 'category': 'קטגוריה',
        'language': 'שפת השאלה', 'answer': 'תשובת בעל המקצוע',
        'reason': 'סיבה', 'message': 'פרטי הדיווח',
    },
}


def _lang():
    value = (get_language() or 'ru').split('-')[0]
    return value if value in _TEXT else 'ru'


class QuestionForm(forms.Form):
    title = forms.CharField(min_length=8, max_length=180)
    body = forms.CharField(
        min_length=20, max_length=8000,
        widget=forms.Textarea(attrs={'rows': 8, 'dir': 'auto'}),
    )
    category = forms.ModelChoiceField(queryset=Category.objects.none())
    language = forms.ChoiceField(choices=ExpertQuestion._meta.get_field('language').choices)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = _TEXT[_lang()]
        self.fields['title'].label = labels['title']
        self.fields['body'].label = labels['body']
        self.fields['category'].label = labels['category']
        self.fields['language'].label = labels['language']
        self.fields['category'].queryset = Category.objects.filter(
            is_active=True,
        ).order_by('sort_order', 'pk')
        self.fields['category'].label_from_instance = lambda row: row.localized_name


class AnswerForm(forms.Form):
    body = forms.CharField(
        min_length=20, max_length=12000,
        widget=forms.Textarea(attrs={'rows': 7, 'dir': 'auto'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['body'].label = _TEXT[_lang()]['answer']


class ReportForm(forms.Form):
    reason = forms.ChoiceField(choices=KnowledgeQAReport.Reason.choices)
    message = forms.CharField(
        min_length=10, max_length=2000,
        widget=forms.Textarea(attrs={'rows': 4, 'dir': 'auto'}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['reason'].label = _TEXT[_lang()]['reason']
        self.fields['message'].label = _TEXT[_lang()]['message']


class ModerationForm(forms.Form):
    expected_version = forms.IntegerField(min_value=1)
    action = forms.ChoiceField(choices=(('approve', 'Approve'), ('reject', 'Reject')))
    note = forms.CharField(max_length=500, required=False)
