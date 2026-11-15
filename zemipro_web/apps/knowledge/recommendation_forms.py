from django import forms
from django.utils.translation import get_language


class RecommendationForm(forms.Form):
    language = forms.ChoiceField(choices=(('ru', 'Русский'), ('en', 'English'), ('he', 'עברית')))
    body = forms.CharField(
        min_length=30, max_length=4000,
        widget=forms.Textarea(attrs={'rows': 7, 'dir': 'auto'}),
    )
    experience_confirmed = forms.BooleanField(required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        language = (get_language() or 'ru').split('-')[0]
        labels = {
            'ru': ('Язык', 'Ваш личный опыт', 'Подтверждаю реальный личный опыт'),
            'en': ('Language', 'Your personal experience', 'I confirm genuine personal experience'),
            'he': ('שפה', 'הניסיון האישי שלכם', 'אני מאשר/ת ניסיון אישי אמיתי'),
        }.get(language, ('Язык', 'Ваш личный опыт', 'Подтверждаю личный опыт'))
        for name, label in zip(
            ('language', 'body', 'experience_confirmed'), labels,
        ):
            self.fields[name].label = label
