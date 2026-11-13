"""Django display filter backed by the SAME policy as directory search."""
from django import template
from apps.accounts.public_text import redact_public_contact

register = template.Library()


@register.filter
def public_text(value):
    return redact_public_contact(value)


@register.filter
def public_hours(value):
    """Only the explicit working-hours slot may display valid HH:MM ranges."""
    return redact_public_contact(value, allow_work_hours=True)
