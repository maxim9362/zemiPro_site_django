"""Frozen fail-closed public text policy (Stage 05 privacy hardening).

Free-form text cannot be proven contact-free by selectively replacing regex
matches.  This version therefore treats the *whole field* as private whenever
it observes a contact signal.  Search receives either the complete safe field
or an empty value; it never receives the remainder of a partially redacted
email, phone number, URL, URI or messenger handle.

The original user text is preserved in the model.  Public callers must use the
helpers exported by ``accounts.public_text``.  Future policy changes require a
new version and a forward-only migration.
"""
import html
import re
import unicodedata
from urllib.parse import unquote

MARKER = '[…]'
_MAX_DECODE_ROUNDS = 32
_DASHES = '\u2212\ufe63\uff0d'
_DOTS = '·•∙⋅․‧﹒。｡'
_SLASHES = '⁄∕'

_HOURS = re.compile(
    r'(?:[01]\d|2[0-3]):[0-5]\d\s*-\s*(?:[01]\d|2[0-3]):[0-5]\d',
)
_RESIDUAL_ENCODING = re.compile(r'%[0-9a-fA-F]{2}')
_URI = re.compile(r"(?<!\w)[A-Za-z][A-Za-z0-9+.-]{0,31}:[^\s<>\"']+", re.I)
_DOMAIN = re.compile(
    r"(?<![\w@])(?:[\w-]+\s*\.\s*)+[^\W\d_][\w-]{1,62}"
    r"(?::\d{2,5})?(?:\s*/\s*[^\s<>\"']*)?",
    re.I,
)
_BRACKET_DOT = re.compile(
    r'[\[({]\s*(?:dot|point|\.|точка|נקודה)\s*[\])}]', re.I,
)
_BRACKET_AT = re.compile(
    r'[\[({]\s*(?:at|@|собака|штрудель|שטרודל)\s*[\])}]', re.I,
)
_DOT_WORD = re.compile(r'(?<=\w)\s+(?:dot|point|точка|נקודה)\s+(?=\w)', re.I)
_AT_WORD = re.compile(r'(?<=\w)\s+(?:at|собака|штрудель|שטרודל)\s+(?=\w)', re.I)
_EMAIL = re.compile(
    r"(?<![\w!#$%&'*+/=?^\x60{|}~.-])"
    r"[\w.!#$%&'*+/=?^\x60{|}~-]{1,128}\s*@\s*"
    r"[\w-]+(?:\s*\.\s*[\w-]+)+",
    re.I,
)
_HANDLE = re.compile(r'(?<!\w)@\s*[\w][\w._-]*')

# A public profile is not the place for directions to an off-platform contact
# channel.  Exact words are deliberately conservative and multilingual; the
# word boundaries avoid blocking unrelated words such as "contactless".
_CONTACT_WORD = re.compile(
    r'(?<!\w)(?:'
    r'contact|call|phone|mobile|telephone|tel|email|e-mail|mail|dm|'
    r'telegram|whatsapp|instagram|facebook|messenger|signal|viber|wechat|'
    r'skype|discord|tiktok|linkedin|snapchat|'
    r'контакт|связь|звоните|пишите|телефон|номер|почта|телеграм|'
    r'ватсап|вотсап|инстаграм|фейсбук|'
    r'טלפון|נייד|דוא["״\']?ל|מייל|טלגרם|וואטסאפ|אינסטגרם|פייסבוק'
    r')(?!\w)',
    re.I,
)
_SPACED_CHANNEL = re.compile(
    r'(?<!\w)(?:'
    r't\W*e\W*l\W*e\W*g\W*r\W*a\W*m|'
    r'w\W*h\W*a\W*t\W*s\W*a\W*p\W*p|'
    r'i\W*n\W*s\W*t\W*a\W*g\W*r\W*a\W*m'
    r')(?!\w)',
    re.I,
)


def normalize_public_text(value):
    """Decode bounded nesting and canonicalize Unicode without losing '+'."""
    text = str(value or '')
    for _ in range(_MAX_DECODE_ROUNDS):
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
        elif category == 'Nd':
            normalized.append(str(unicodedata.digit(char)))
        elif category == 'Pd' or char in _DASHES:
            normalized.append('-')
        elif char in _DOTS:
            normalized.append('.')
        elif char in _SLASHES:
            normalized.append('/')
        else:
            normalized.append(char)
    return ''.join(normalized)


def _contact_probe(text):
    """Return canonical detection text; never use this value for display."""
    probe = _BRACKET_DOT.sub('.', text)
    probe = _BRACKET_AT.sub('@', probe)
    probe = _DOT_WORD.sub('.', probe)
    return _AT_WORD.sub('@', probe)


def _has_contact_signal(text, *, allow_work_hours=False):
    """Conservative field-level decision; no partial text is ever returned."""
    probe = _contact_probe(text)
    without_hours = _HOURS.sub('', probe) if allow_work_hours else probe
    compact = re.sub(r'\s+', '', without_hours)

    if _RESIDUAL_ENCODING.search(without_hours):
        return True
    if '@' in without_hours or _EMAIL.search(probe) or _HANDLE.search(probe):
        return True
    if _URI.search(without_hours) or _URI.search(compact):
        return True
    if _DOMAIN.search(probe):
        return True
    if _CONTACT_WORD.search(without_hours) or _SPACED_CHANNEL.search(without_hours):
        return True

    # Seven digits are enough to identify a local phone fragment.  Counting
    # across the complete field also catches alphabetic separators such as
    # 0a5a0a7a6a5a4a3a2a1.  Structured numeric price and availability fields
    # remain available for legitimate numbers.
    return sum(char.isdecimal() for char in without_hours) >= 7


def redact_public_contact(value, *, allow_work_hours=False):
    """Return the full safe field or one neutral marker, never a remainder."""
    text = normalize_public_text(value)
    if _has_contact_signal(text, allow_work_hours=allow_work_hours):
        return MARKER
    return text


def searchable_public_text(value):
    """A contact signal removes the complete value from keyword search."""
    public = redact_public_contact(value)
    if public == MARKER:
        return ''
    return ' '.join(public.split())


def searchable_public_name(value):
    return searchable_public_text(value)[:120]


def contains_public_contact(value, *, allow_work_hours=False):
    text = normalize_public_text(value)
    return _has_contact_signal(text, allow_work_hours=allow_work_hours)


def profile_public_content_is_safe(*, display_name, description,
                                   pricing_details, working_hours):
    """One publication decision shared by model, service and migration."""
    return not any((
        contains_public_contact(display_name),
        contains_public_contact(description),
        contains_public_contact(pricing_details),
        contains_public_contact(working_hours, allow_work_hours=True),
    ))


def contact_shaped_query(value):
    """Block contact lookups, including short numeric suffix oracles."""
    text = normalize_public_text(value).strip()
    if _has_contact_signal(text):
        return True
    return sum(char.isdecimal() for char in text) >= 4
