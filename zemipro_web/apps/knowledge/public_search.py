"""Bounded public GET filters, never search unapproved raw article fields."""
from django import forms
from django.utils.translation import get_language

from apps.accounts.public_text import contact_shaped_query


_LABELS = {
    'ru': ('Поиск по теме', 'Категория', 'Язык статьи', 'Все категории', 'Все языки'),
    'en': ('Search by topic', 'Category', 'Article language', 'All categories', 'All languages'),
    'he': ('חיפוש לפי נושא', 'קטגוריה', 'שפת המאמר', 'כל הקטגוריות', 'כל השפות'),
}


class PublicArticleSearchForm(forms.Form):
    q = forms.CharField(
        required=False, max_length=80,
        widget=forms.TextInput(attrs={'maxlength': 80, 'autocomplete': 'off'}),
    )
    category = forms.ChoiceField(required=False)
    language = forms.ChoiceField(required=False)

    def __init__(self, *args, categories, **kwargs):
        super().__init__(*args, **kwargs)
        language = (get_language() or 'ru').split('-')[0]
        search, category, article_language, all_categories, all_languages = _LABELS.get(
            language, _LABELS['ru'],
        )
        self.fields['q'].label = search
        self.fields['category'].label = category
        self.fields['language'].label = article_language
        self.fields['category'].choices = [
            ('', all_categories),
            *((str(item.pk), item.localized_name) for item in categories),
        ]
        self.fields['language'].choices = [
            ('', all_languages),
            ('ru', 'Русский'), ('en', 'English'), ('he', 'עברית'),
        ]

    def clean_q(self):
        value = self.cleaned_data.get('q', '').strip()
        if contact_shaped_query(value):
            raise forms.ValidationError('Invalid search query.')
        return value
