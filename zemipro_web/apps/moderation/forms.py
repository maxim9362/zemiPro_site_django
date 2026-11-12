from django import forms
from django.utils.translation import gettext as _, gettext_lazy

from .models import Complaint


class ComplaintForm(forms.ModelForm):
    """Форма подачи жалобы."""

    class Meta:
        model = Complaint
        fields = ['reason', 'message']
        widgets = {
            'reason': forms.Select(attrs={'class': 'form__select'}),
            'message': forms.Textarea(attrs={
                'rows': 4,
                'placeholder': gettext_lazy('Опишите проблему подробнее'),
            }),
        }
        labels = {
            'reason': gettext_lazy('Причина жалобы'),
            'message': gettext_lazy('Описание'),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Stored reason values remain stable; only choice labels follow locale.
        self.fields['reason'].choices = [
            (value, _(str(label)))
            for value, label in self.fields['reason'].choices
        ]
