from django import forms


class RecommendationForm(forms.Form):
    language = forms.ChoiceField(choices=(('ru', 'Русский'), ('en', 'English'), ('he', 'עברית')))
    body = forms.CharField(
        min_length=30, max_length=4000,
        widget=forms.Textarea(attrs={'rows': 7, 'dir': 'auto'}),
    )
    experience_confirmed = forms.BooleanField(required=True)
