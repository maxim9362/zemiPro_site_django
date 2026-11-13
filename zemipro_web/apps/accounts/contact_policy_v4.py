"""Frozen, fail-closed public contact policy v4 (ZP-05-005).

Only publicly approved service prose belongs in public fields. This policy
normalizes Unicode, Unicode punctuation, nested URL/HTML encoding and common
contact obfuscations before display or keyword indexing. It is deliberately
conservative: external links, URI schemes and phone-shaped numeric runs are
redacted even if intended as benign text. No regex can detect arbitrary
semantic obfuscation; untrusted originals must never be searched directly.

IMPORTANT: migrations.0018 imports this module. Do not modify in later
releases: create a new policy version and a forward-only migration instead.
"""
import html
import re
import unicodedata
from urllib.parse import unquote

MARKER = '[…]'

# Treat Unicode dash punctuation, middle dots and Unicode slashes uniformly.
_EXTRA_DASHES = '\u2212\ufe63\uff0d'
_EXTRA_DOTS = '·•∙⋅․‧﹒。｡'
_EXTRA_SLASHES = '⁄∕'
_DOT_AT = re.compile(
    r'(?<=\w)\s*(?:\[\s*(?:dot|\.)\s*\]|\(\s*(?:dot|\.)\s*\)|\s+dot\s+)\s*(?=\w)',
    flags=re.IGNORECASE,
)
_AT = re.compile(
    r'(?<=\w)\s*(?:\[\s*at\s*\]|\(\s*at\s*\))\s*(?=\w)',
    flags=re.IGNORECASE,
)


def normalize_public_text(value):
    """Canonical text before policy checks and contact-free SQL matching."""
    text = str(value or '')
    # 050%25252F7654321 requires multiple unquote rounds; never turn +
    # into a space (unquote_plus would destroy the international dial prefix).
    for _ in range(5):
        decoded = html.unescape(unquote(text))
        if decoded == text:
            break
        text = decoded
    text = unicodedata.normalize('NFKC', text)
    output = []
    for char in text:
        category = unicodedata.category(char)
        if category in ('Cf', 'Cs') or char in ('\u034f', '\u180e'):
            continue
        if '\ufe00' <= char <= '\ufe0f' or '\U000e0100' <= char <= '\U000e01ef':
            continue
        if category == 'Cc':
            output.append(' ')
        elif category == 'Pd' or char in _EXTRA_DASHES:
            output.append('-')
        elif char in _EXTRA_DOTS:
            output.append('.')
        elif char in _EXTRA_SLASHES:
            output.append('/')
        else:
            output.append(char)
    text = ''.join(output)
    text = _DOT_AT.sub('.', text)
    return _AT.sub('@', text)


# Deny arbitrary alphabetic URI schemes, including tg:// and custom messenger
# schemes (not merely http, https and www). No network request is performed.
_URI = re.compile(r"""(?<!\w)[A-Za-z][A-Za-z0-9+.-]{1,24}:[^\s<>"']+""", re.I)
# Unicode (IDN) bare domains with optional paths. A final TLD must begin with
# a letter so version 2.0 does not become a fake domain.
_DOMAIN = re.compile(
    r"""(?<![\w@])(?:[\w-]+\.)+[^\W\d_][\w-]{1,62}(?::\d{2,5})?(?:/[^\s<>"']*)?""",
    re.I,
)
# Consume *whole* mail-like tokens, including RFC local characters ! and +,
# rather than masking only "doe@example" inside "john!doe@example".
_EMAIL = re.compile(r"""(?<!\S)[^\s@<>"']{1,128}@\s*[^\s@<>"']{1,128}""", re.I)
_HANDLE = re.compile(r'(?<!\w)@\s*[\w][\w._-]*')
# A phone is a bounded run with >=8 digits, separated by ANY Unicode
# punctuation/whitespace rather than a hand-picked ASCII character list.
_PHONE = re.compile(r'(?<!\w)\+?\d(?:[^\w]{0,5}\d){7,18}(?!\w)')
_PHONE_QUERY = re.compile(r'(?<!\w)\+?\d(?:[^\w]{0,5}\d){4,18}(?!\w)')
# Four pairs of digits may be a legitimate work schedule, not a phone.
# The strict hour/minute ranges deliberately do not admit 050:7654321.
_HOURS = re.compile(r'(?:[01]\d|2[0-3]):[0-5]\d\s*-\s*(?:[01]\d|2[0-3]):[0-5]\d')


def redact_public_contact(value, *, allow_work_hours=False):
    """Protect public text; allow only valid time ranges in the hours field."""
    result = normalize_public_text(value)
    for pattern in (_EMAIL, _URI, _DOMAIN, _HANDLE):
        result = pattern.sub(MARKER, result)
    result = _PHONE.sub(
        lambda match: match.group() if allow_work_hours and _HOURS.fullmatch(match.group())
        else MARKER,
        result,
    )
    return result


def searchable_public_text(value):
    """Make persisted search use only normalized and visible text."""
    return ' '.join(redact_public_contact(value).replace(MARKER, ' ').split())


def searchable_public_name(value):
    """NFKC expansion must not exceed the stored varchar(120) field."""
    return searchable_public_text(value)[:120]


def contains_public_contact(value, *, allow_work_hours=False):
    return MARKER in redact_public_contact(value, allow_work_hours=allow_work_hours)


def contact_shaped_query(value):
    """Reject direct contact searches; scrubbed columns close suffix oracles."""
    text = normalize_public_text(value).strip()
    if '@' in text or contains_public_contact(text):
        return True
    if text.startswith('+') and sum(char.isdigit() for char in text) >= 3:
        return True
    return _PHONE_QUERY.search(text) is not None
