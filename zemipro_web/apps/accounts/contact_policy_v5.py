"""Frozen v5: public contact removal and keyword privacy (ZP-05-006/007).

Unrestricted natural language cannot be guaranteed PII-free with regex.
No raw user-authored contact-bearing profile field is used for public search.
Future changes must version policy and add a forward data migration.
"""
import html
import re
import unicodedata
from urllib.parse import unquote

MARKER = '[…]'
_DASHES = '\u2212\ufe63\uff0d'
_DOTS = '·•∙⋅․‧﹒。｡'
_SLASHES = '⁄∕'
_OBF_DOT = re.compile(
    r'(?<=\w)\s*(?:\[\s*(?:dot|\.)\s*\]|\(\s*(?:dot|\.)\s*\)|\s+dot\s+)\s*(?=\w)',
    re.I,
)
_OBF_AT = re.compile(
    r'(?<=\w)\s*(?:\[\s*at\s*\]|\(\s*at\s*\))\s*(?=\w)',
    re.I,
)
# A heavily nested %25 escape surviving the decode cap is NOT considered safe.
_RESIDUAL = re.compile(r"""(?<!\w)[^\s<>"']*%[0-9a-fA-F]{2}[^\s<>"']*""")


def normalize_public_text(value):
    """Canonical Unicode, HTML, percent encoding, bidi and punctuation."""
    text = str(value or '')
    for _ in range(32):
        decoded = html.unescape(unquote(text))
        if decoded == text:
            break
        text = decoded
    text = unicodedata.normalize('NFKC', text)
    normalized = []
    for char in text:
        category = unicodedata.category(char)
        if category in ('Cf', 'Cs') or char in ('\u034f', '\u180e'):
            continue
        if '\ufe00' <= char <= '\ufe0f' or '\U000e0100' <= char <= '\U000e01ef':
            continue
        if category == 'Cc':
            normalized.append(' ')
        elif category == 'Pd' or char in _DASHES:
            normalized.append('-')
        elif char in _DOTS:
            normalized.append('.')
        elif char in _SLASHES:
            normalized.append('/')
        else:
            normalized.append(char)
    text = _OBF_DOT.sub('.', ''.join(normalized))
    return _OBF_AT.sub('@', text)


# Consume local part WITH the domain. Never leave 'john' indexed for
# "john @ example.com" or "john at example dot com".
_EMAIL = re.compile(
    r"""(?<![\w!#$%&'*+/=?^\x60{|}~.-])"""
    r"""[\w.!#$%&'*+/=?^\x60{|}~-]{1,128}"""
    r"""(?:\s*@\s*|\s+at\s+)"""
    r"""[\w-]+(?:\s*\.\s*[\w-]+)+""",
    re.I,
)
# x:// is a valid one-letter scheme and must be excluded.
_URI = re.compile(r"""(?<!\w)[A-Za-z][A-Za-z0-9+.-]{0,24}:[^\s<>"']+""", re.I)
_DOMAIN = re.compile(
    r"""(?<![\w@])(?:[\w-]+\.)+[^\W\d_][\w-]{1,62}(?::\d{2,5})?(?:/[^\s<>"']*)?""",
    re.I,
)
_HANDLE = re.compile(r'(?<!\w)@\s*[\w][\w._-]*')
# No delimiter-count limit. Eight or more digits across punctuation/whitespace
# are treated as a possible number, including six dashes or large spaces.
_PHONE = re.compile(r'(?<!\w)\+?\d(?:[^\w]*\d){7,30}(?!\w)')
_PHONE_QUERY = re.compile(r'(?<!\w)\+?\d(?:[^\w]*\d){4,30}(?!\w)')
_HOURS = re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d\s*-\s*(?:[01]\d|2[0-3]):[0-5]\d')


def redact_public_contact(value, *, allow_work_hours=False):
    text = normalize_public_text(value)
    for pattern in (_RESIDUAL, _EMAIL, _URI, _DOMAIN, _HANDLE):
        text = pattern.sub(MARKER, text)
    return _PHONE.sub(
        lambda match: match.group()
        if allow_work_hours and _HOURS.fullmatch(match.group())
        else MARKER,
        text,
    )


def searchable_public_text(value):
    return ' '.join(redact_public_contact(value).replace(MARKER, ' ').split())


def searchable_public_name(value):
    return searchable_public_text(value)[:120]


def contains_public_contact(value, *, allow_work_hours=False):
    return MARKER in redact_public_contact(
        value, allow_work_hours=allow_work_hours,
    )


def contact_shaped_query(value):
    text = normalize_public_text(value).strip()
    if '@' in text or contains_public_contact(text):
        return True
    if text.startswith('+') and sum(c.isdigit() for c in text) >= 3:
        return True
    return _PHONE_QUERY.search(text) is not None
