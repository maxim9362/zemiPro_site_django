"""Frozen Stage 05 public-contact policy, shared by runtime and migration 0016.

Public free-text is not an authorized channel for personal contacts. Keep this
module stable: any future policy revision needs a new, versioned module and
forward backfill migration, not a historical migration edit.
"""
import re

# Mailbox without a TLD is still contact-like; remove its whole local part
# rather than leaving an oracle for searches on the fragment before '@'.
EMAIL = re.compile(r'(?<![\w.+-])[\w.+-]+@[\w.-]+(?:\.[A-Za-z]{2,})?(?!\w)')
# Bare social/messenger account handles, including Unicode usernames.
HANDLE = re.compile(r'@[\w][\w.-]*')
# Allow separators used by local/mobile phone spelling, including '/'.
PHONE = re.compile(r'(?<!\w)(?:\+?\d[\d \t\-./()]{6,}\d)(?!\w)')
PHONE_QUERY = re.compile(r'\d[\d \t\-./()]{2,}\d')

REDACTED = '[…]'


def redact_public_contact(value):
    """Mask the *entire* contact, never retaining searchable handle/suffix."""
    text = str(value or '')
    text = EMAIL.sub(REDACTED, text)
    text = HANDLE.sub(REDACTED, text)

    def mask_phone(match):
        return REDACTED if sum(ch.isdigit() for ch in match.group()) >= 8 else match.group()

    return PHONE.sub(mask_phone, text)


def searchable_public_text(value):
    """Store only visible words, never hidden tokens or a redaction marker."""
    return ' '.join(redact_public_contact(value).replace(REDACTED, ' ').split())


def contains_public_contact(value):
    """The form and publication service must use the same detection policy."""
    return redact_public_contact(value) != str(value or '')


def contact_shaped_query(value):
    """Reject known contact syntax; shorter fragments cannot match scrubbed text."""
    text = (value or '').strip()
    if '@' in text:
        return True
    if text.startswith('+') and sum(ch.isdigit() for ch in text) >= 3:
        return True
    return any(
        sum(ch.isdigit() for ch in found.group()) >= 5
        for found in PHONE_QUERY.finditer(text)
    )
