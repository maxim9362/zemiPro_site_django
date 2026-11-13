"""Frozen public contact policy v3: Unicode + URLs + obfuscated contacts.

The raw owner-authored profile is retained privately. Public render and search
use this policy; newer revisions must use v4 and a forward-only migration.
"""
import html
import re
import unicodedata

MARKER = '[…]'
DASHES = {ord(ch): '-' for ch in '\u2010\u2011\u2012\u2013\u2014\u2015\u2212\ufe58\ufe63\uff0d'}
DOTS = {ord(ch): '.' for ch in '\u00b7\u2022\u2219\u22c5\u2027'}
ENCODED = re.compile(r'%(?:25)?(40|2e|2f|3a|2d|20)', flags=re.IGNORECASE)


def normalize_public_text(value):
    """NFKC + bidi/ignorable cleanup + URL/HTML-encoded contact separators."""
    text = html.unescape(str(value or ''))
    for _ in range(2):
        text = ENCODED.sub(lambda m: chr(int(m.group(1), 16)), text)
    text = unicodedata.normalize('NFKC', text).translate(DASHES).translate(DOTS)
    return ''.join(
        ' ' if ch in '\r\n\t' else ch
        for ch in text
        if unicodedata.category(ch) != 'Cf'
        and ch not in ('\u034f', '\u180e')
        and not ('\ufe00' <= ch <= '\ufe0f')
        and not ('\U000e0100' <= ch <= '\U000e01ef')
    )


OBFUSCATED_EMAIL = re.compile(
    r'(?<![\w.+-])[\w.+-]+'
    r'(?:\s*\[\s*at\s*\]\s*|\s*\(\s*at\s*\)\s*|\s+at\s+)'
    r'[\w-]+'
    r'(?:\s*(?:\.|\[\s*dot\s*\]|\(\s*dot\s*\)|\bdot\b)\s*[\w-]+)+',
    flags=re.IGNORECASE,
)
EMAIL = re.compile(r'(?<![\w.+-])[\w.+-]+@[\w.-]+(?:\.[A-Za-z]{2,})?(?!\w)')
# Conservatively hide all web links: contact URLs are not an approved channel.
URL = re.compile(
    r'(?<![\w@])(?:https?://|www\.)[^\s<>"\']+'
    r'|(?<![\w@])(?:[\w-]+\.)+[A-Za-z]{2,24}'
    r'(?::\d{2,5})?(?:/[^\s<>"\']*)?',
    flags=re.IGNORECASE,
)
HANDLE = re.compile(r'@[\w][\w.-]*')
PHONE = re.compile(r'(?<!\w)\+?\d(?:[\d\s\-./()]*\d)?(?!\w)')
PHONE_QUERY = re.compile(r'\d(?:[\d\s\-./()]*\d)?')


def redact_public_contact(value):
    """Replace whole contact tokens without leaving searchable suffixes."""
    text = normalize_public_text(value)
    for pattern in (OBFUSCATED_EMAIL, EMAIL, URL, HANDLE):
        text = pattern.sub(MARKER, text)
    return PHONE.sub(
        lambda m: MARKER if sum(ch.isdigit() for ch in m.group()) >= 8
        else m.group(), text,
    )


def searchable_public_text(value):
    """A normalized contact-free copy, never the untrusted raw description."""
    return ' '.join(redact_public_contact(value).replace(MARKER, ' ').split())


def searchable_public_name(value):
    """Do not overflow the existing 120-char varchar on NFKC expansion."""
    return searchable_public_text(value)[:120]


def contains_public_contact(value):
    return MARKER in redact_public_contact(value)


def contact_shaped_query(value):
    """Explicit contact syntax is invalid; partial suffixes have no index match."""
    text = normalize_public_text(value).strip()
    if '@' in text or contains_public_contact(text):
        return True
    if text.startswith('+') and sum(ch.isdigit() for ch in text) >= 3:
        return True
    return any(
        sum(ch.isdigit() for ch in match.group()) >= 5
        for match in PHONE_QUERY.finditer(text)
    )
