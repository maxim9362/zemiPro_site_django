from django import forms
from django.utils.translation import gettext_lazy as _

from .models import SeoContentPage, SeoLegacyUrl


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


class SeoLegacyUrlForm(forms.ModelForm):
    class Meta:
        model = SeoLegacyUrl
        fields = (
            'path', 'page_type', 'decision', 'target_path', 'redirect_status',
            'evidence_source',
        )
