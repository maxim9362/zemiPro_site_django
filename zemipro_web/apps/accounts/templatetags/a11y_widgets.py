"""Shared, presentation-only Django widget attributes for accessibility."""
from django import template

register = template.Library()


@register.simple_tag
def ui_widget(field, help_id="", errors_id=""):
    """Keep native Django widget/validation while joining ARIA descriptions."""
    if field.is_hidden:
        return field.as_widget()
    refs = str(field.field.widget.attrs.get("aria-describedby", "")).split()
    if field.help_text and help_id:
        refs.append(str(help_id))
    if field.errors and errors_id:
        refs.append(str(errors_id))
    attrs = {}
    if refs:
        attrs["aria-describedby"] = " ".join(dict.fromkeys(refs))
    if field.errors:
        attrs["aria-invalid"] = "true"
    return field.as_widget(attrs=attrs)
