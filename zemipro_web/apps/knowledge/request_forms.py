from django import forms
from django.utils.translation import get_language

from apps.accounts.client_favorites import public_worker_queryset
from apps.accounts.models import WorkerProfile
from apps.marketplace.models import Category


class RecommendationRequestForm(forms.Form):
    title = forms.CharField(min_length=8, max_length=180)
    body = forms.CharField(
        min_length=20, max_length=5000,
        widget=forms.Textarea(attrs={'rows': 7, 'dir': 'auto'}),
    )
    category = forms.ModelChoiceField(queryset=Category.objects.none())
    language = forms.ChoiceField(choices=(('ru', 'Русский'), ('en', 'English'), ('he', 'עברית')))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        language = (get_language() or 'ru').split('-')[0]
        labels = {
            'ru': ('Заголовок', 'Подробности', 'Категория', 'Язык'),
            'en': ('Title', 'Details', 'Category', 'Language'),
            'he': ('כותרת', 'פרטים', 'קטגוריה', 'שפה'),
        }.get(language, ('Заголовок', 'Подробности', 'Категория', 'Язык'))
        for name, label in zip(('title', 'body', 'category', 'language'), labels):
            self.fields[name].label = label
        self.fields['category'].queryset = Category.objects.filter(
            is_active=True,
        ).order_by('sort_order', 'pk')
        self.fields['category'].label_from_instance = lambda row: row.localized_name


class RecommendationResponseForm(forms.Form):
    # Keep module import side-effect free: public_worker_queryset() resolves the
    # pilot city and therefore must only run when a request instantiates the
    # form, never while Django imports URL configuration for system checks.
    worker = forms.ModelChoiceField(queryset=WorkerProfile.objects.none())
    body = forms.CharField(
        min_length=20, max_length=3000,
        widget=forms.Textarea(attrs={'rows': 5, 'dir': 'auto'}),
    )

    def __init__(self, *args, category_id, **kwargs):
        super().__init__(*args, **kwargs)
        language = (get_language() or 'ru').split('-')[0]
        labels = {
            'ru': ('Публичный мастер', 'Почему вы советуете мастера'),
            'en': ('Public specialist', 'Why you recommend this specialist'),
            'he': ('בעל מקצוע ציבורי', 'מדוע אתם ממליצים'),
        }.get(language, ('Публичный мастер', 'Почему вы советуете мастера'))
        self.fields['worker'].label, self.fields['body'].label = labels
        self.fields['worker'].queryset = public_worker_queryset().filter(
            city__slug='ashdod', city__is_active=True, skills__pk=category_id,
        ).order_by('pk')
        self.fields['worker'].label_from_instance = (
            lambda row: row.public_display_name_snapshot
        )
