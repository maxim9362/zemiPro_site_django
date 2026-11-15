from django import forms
from django.utils.translation import gettext_lazy as _

from .models import SeoContentPage, SeoLegacyUrl


PAGE_TYPE_LABELS = {
    SeoContentPage.PageType.SECTION: _('Раздел услуг'),
    SeoContentPage.PageType.CATEGORY: _('Категория'),
    SeoContentPage.PageType.SERVICE: _('Услуга'),
    SeoContentPage.PageType.CITY: _('Город'),
    SeoContentPage.PageType.SERVICE_CITY: _('Услуга в городе'),
}


class SeoContentPageForm(forms.ModelForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput, required=False)

    class Meta:
        model = SeoContentPage
        fields = (
            'page_type', 'language', 'section', 'category', 'service', 'city',
            'topic', 'title', 'meta_description', 'summary', 'body', 'source_facts',
        )
        labels = {
            'page_type': _('Тип страницы'),
            'language': _('Язык'),
            'section': _('Раздел'),
            'category': _('Категория'),
            'service': _('Услуга'),
            'city': _('Город'),
            'topic': _('Тема'),
            'title': _('Заголовок'),
            'meta_description': _('Мета-описание'),
            'summary': _('Краткое описание'),
            'body': _('Основной текст'),
            'source_facts': _('Источники фактов'),
        }
        help_texts = {
            'source_facts': _(
                'Укажите проверяемые источники фактов; не добавляйте секреты '
                'или персональные данные.'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['page_type'].choices = [
            (value, PAGE_TYPE_LABELS.get(value, label))
            for value, label in self.fields['page_type'].choices
        ]


class SeoContentEditForm(forms.ModelForm):
    expected_version = forms.IntegerField(widget=forms.HiddenInput)

    class Meta:
        model = SeoContentPage
        fields = (
            'topic', 'title', 'meta_description', 'summary', 'body', 'source_facts',
        )
        labels = {
            'topic': _('Тема'),
            'title': _('Заголовок'),
            'meta_description': _('Мета-описание'),
            'summary': _('Краткое описание'),
            'body': _('Основной текст'),
            'source_facts': _('Источники фактов'),
        }
        help_texts = {
            'source_facts': _(
                'Укажите проверяемые источники фактов; не добавляйте секреты '
                'или персональные данные.'
            ),
        }


class SeoLegacyUrlForm(forms.ModelForm):
    class Meta:
        model = SeoLegacyUrl
        fields = (
            'path', 'page_type', 'decision', 'target_path', 'redirect_status',
            'evidence_source',
        )
