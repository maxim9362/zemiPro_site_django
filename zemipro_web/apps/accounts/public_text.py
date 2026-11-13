"""Single contact-suppression policy for publicly displayed and SEARCHED text.

Existing published legacy rows may contain contacts. Never use raw editable
profile fields as search predicates, even when a template masks their output.
This is deliberate redaction rather than a claim to detect every possible PII.
"""
import re

EMAIL = re.compile(r'(?<![\w.+-])[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}(?!\w)')
PHONE = re.compile(r'(?<!\w)(?:\+?\d[\d \-().]{6,}\d)(?!\w)')
PHONE_QUERY = re.compile(r'\d[\d \-().]{2,}\d')


def redact_public_contact(value):
    """Use exactly the same suppression rules for HTML and persisted search."""
    text = EMAIL.sub('[…]', str(value or ''))

    def replace_phone(match):
        return '[…]' if sum(ch.isdigit() for ch in match.group()) >= 8 else match.group()

    return PHONE.sub(replace_phone, text)


def searchable_public_text(value):
    """Discard redaction markers; none of the contact's fragments stay indexed."""
    return ' '.join(redact_public_contact(value).replace('[…]', ' ').split())


def contains_public_contact(value):
    return redact_public_contact(value) != str(value or '')


def contact_shaped_query(value):
    """Fail closed on explicit contacts; short fragments are safe via redacted fields."""
    text = (value or '').strip()
    if '@' in text or EMAIL.search(text):
        return True
    if text.startswith('+') and sum(ch.isdigit() for ch in text) >= 3:
        return True
    return any(
        sum(ch.isdigit() for ch in candidate.group()) >= 5
        for candidate in PHONE_QUERY.finditer(text)
    )
