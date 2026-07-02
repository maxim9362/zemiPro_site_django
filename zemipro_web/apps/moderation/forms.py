from django import forms

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
                'placeholder': 'Опишите проблему подробнее',
            }),
        }
        labels = {
            'reason': 'Причина жалобы',
            'message': 'Описание',
        }
