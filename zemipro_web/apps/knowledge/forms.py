"""Bounded, CSRF-protected form inputs; ownership is enforced in services."""
from django import forms
from django.utils.translation import gettext_lazy as _, get_language

from apps.marketplace.models import Category, Subcategory
from .models import ExpertArticle, ExpertArticleReport

_LABELS = {
    'title': ('Заголовок', 'Title', 'כותרת'),
    'excerpt': ('Краткое описание', 'Summary', 'תקציר'),
    'body': ('Текст статьи', 'Article text', 'תוכן המאמר'),
    'category': ('Категория', 'Category', 'קטגוריה'),
    'subcategory': ('Услуга', 'Service', 'שירות'),
    'language': ('Язык оригинала', 'Original language', 'שפת המקור'),
    'rights_confirmed': (
        'Подтверждаю права на текст и изображения',
        'I confirm rights to this content',
        'אני מאשר/ת זכויות על התוכן',
    ),
    'image': ('Фотография', 'Image', 'תמונה'),
    'caption': ('Подпись', 'Caption', 'כיתוב'),
    'reason': ('Причина', 'Reason', 'סיבה'),
    'message': ('Описание жалобы', 'Report details', 'פרטי הדיווח'),
}


class LocalizedLabels:
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        language = (get_language() or 'ru').split('-')[0]
        column = {'ru': 0, 'en': 1, 'he': 2}.get(language, 0)
        for name, field in self.fields.items():
            if name in _LABELS:
                field.label = _LABELS[name][column]




class ArticleForm(LocalizedLabels, forms.Form):
    title = forms.CharField(max_length=180, label=_('Заголовок'))
    excerpt = forms.CharField(
        max_length=400, required=False, label=_('Краткое описание'),
    )
    body = forms.CharField(
        max_length=16000, required=False, label=_('Текст статьи'),
        widget=forms.Textarea(attrs={'rows': 12, 'dir': 'auto'}),
    )
    category = forms.ModelChoiceField(
        queryset=Category.objects.none(), label=_('Категория'),
    )
    subcategory = forms.ModelChoiceField(
        queryset=Subcategory.objects.none(), required=False, label=_('Услуга'),
    )
    language = forms.ChoiceField(
        choices=ExpertArticle.Language.choices, label=_('Язык оригинала'),
    )
    rights_confirmed = forms.BooleanField(
        required=False, label=_('Подтверждаю авторские права на текст'),
    )

    def __init__(self, *args, worker, article=None, **kwargs):
        super().__init__(*args, **kwargs)
        category_ids = worker.skills.filter(is_active=True).values_list('pk', flat=True)
        self.fields['category'].queryset = Category.objects.filter(pk__in=category_ids)
        self.fields['subcategory'].queryset = Subcategory.objects.filter(
            category_id__in=category_ids, is_active=True,
        )
        self.fields['category'].label_from_instance = lambda obj: obj.localized_name
        self.fields['subcategory'].label_from_instance = lambda obj: obj.localized_name
        if article is not None:
            self.fields['language'].disabled = True
            self.fields['language'].initial = article.language

    def clean(self):
        cleaned = super().clean()
        category, subcategory = cleaned.get('category'), cleaned.get('subcategory')
        if category and subcategory and subcategory.category_id != category.pk:
            self.add_error('subcategory', _('Услуга не относится к категории.'))
        return cleaned


class ArticleActionForm(LocalizedLabels, forms.Form):
    expected_version = forms.IntegerField(min_value=0)
    rights_confirmed = forms.BooleanField(required=False)


class ArticleImageForm(LocalizedLabels, forms.Form):
    image = forms.FileField(label=_('Фотография'))
    caption = forms.CharField(max_length=200, required=False, label=_('Подпись'))
    rights_confirmed = forms.BooleanField(
        required=True, label=_('Подтверждаю право на изображение'),
    )
    expected_version = forms.IntegerField(min_value=0)


class ArticleDecisionForm(LocalizedLabels, forms.Form):
    action = forms.ChoiceField(choices=[
        ('approve', _('Одобрить')), ('reject', _('Отклонить')),
    ])
    expected_version = forms.IntegerField(min_value=0)
    content_reviewed = forms.BooleanField(required=False)
    media_reviewed = forms.BooleanField(required=False)
    note = forms.CharField(max_length=500, required=False)


class ArticleReportForm(LocalizedLabels, forms.Form):
    reason = forms.ChoiceField(choices=ExpertArticleReport.Reason.choices)
    message = forms.CharField(
        min_length=10, max_length=2000, widget=forms.Textarea(attrs={'rows': 4}),
    )


class ArticleReportDecisionForm(LocalizedLabels, forms.Form):
    action = forms.ChoiceField(choices=[
        ('dismiss', _('Отклонить жалобу')), ('remove', _('Снять статью')),
    ])
    note = forms.CharField(max_length=500, required=False)
