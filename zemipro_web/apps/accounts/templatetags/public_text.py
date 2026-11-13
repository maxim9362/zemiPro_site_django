"""Mask likely phone and email strings in user-supplied public fields.

Structured private addresses and contacts must never reach this filter.
"""
import re
from django import template

register = template.Library()
EMAIL = re.compile(r'(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?!\w)')
PHONE = re.compile(r'(?<!\w)(?:\+?\d[\d \-().]{6,}\d)(?!\w)')


@register.filter
def public_text(value):
    text = EMAIL.sub('[…]', str(value or ''))
    return PHONE.sub(
        lambda match: '[…]' if sum(ch.isdigit() for ch in match.group()) >= 8
        else match.group(), text,
    )
