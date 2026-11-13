"""Frozen public-text snapshot policy for Stage 05.

Raw profile text is private input.  Public callers consume persisted snapshots
created by this module; they never render or index raw fields directly.  The
detector is defence in depth, while the snapshot/read gate is the security
boundary.  A future policy change must use a new version and migration.
"""
import html
import re
import unicodedata
from urllib.parse import unquote


POLICY_VERSION = 1
MARKER = '[…]'
_MAX_DECODE_ROUNDS = 32
_DASHES = '\u2212\ufe63\uff0d'
_DOTS = '·•∙⋅․‧﹒。｡'
_SLASHES = '⁄∕'

_HOURS = re.compile(
    r'(?:[01]\d|2[0-3]):[0-5]\d\s*-\s*(?:[01]\d|2[0-3]):[0-5]\d',
)
_RESIDUAL_PERCENT = re.compile(r'%[0-9a-fA-F]{2}')
_RESIDUAL_ENTITY = re.compile(
    r'&(?:#(?:x[0-9a-fA-F]+|\d+)|[a-zA-Z][a-zA-Z0-9]+);',
)
_ASCII_URI = re.compile(
    r"(?<!\w)[A-Za-z][A-Za-z0-9+.-]{0,31}\s*:\s*[^\s<>\"']+",
    re.I,
)
_UNICODE_URI = re.compile(r'(?<!\w)[^\W\d_][\w+.-]{0,31}\s*:\s*/{2}\s*\S+')
_PROTOCOL_RELATIVE = re.compile(r'(?<![:/])/{2}\s*[^\s/]+(?:/\S*)?')
_IPV4 = re.compile(
    r'(?<![\w.])(?:25[0-5]|2[0-4]\d|1?\d?\d)'
    r'(?:\s*\.\s*(?:25[0-5]|2[0-4]\d|1?\d?\d)){3}(?![\w.])',
)
_DOMAIN = re.compile(
    r"(?<![\w@])(?:[\w-]+\s*\.\s*)+"
    r"(?:com|org|net|info|biz|io|co|il|me|app|dev|online|site|store|"
    r"ru|uk|de|fr|ישראל|xn--[a-z0-9-]+)(?![\w-])"
    r"(?::\d{2,5})?(?:\s*/\s*[^\s<>\"']*)?",
    re.I,
)
_EMAIL = re.compile(
    r"(?<![\w!#$%&'*+/=?^\x60{|}~.-])"
    r"[\w.!#$%&'*+/=?^\x60{|}~-]{1,128}\s*@\s*"
    r"[\w-]+(?:\s*\.\s*[\w-]+)+",
    re.I,
)
_HANDLE = re.compile(r'(?<!\w)@\s*[\w][\w._-]*')

_AT = r'(?:at|собака|штрудель|שטרודל)'
_DOT = r'(?:dot|point|точка|נקודה)'
_OBFUSCATED_EMAIL = re.compile(
    rf'(?<!\w)[\w.!#$%&*+?^`{{|}}~]{{1,64}}'
    rf'(?:[^\w]{{1,12}}){_AT}(?:[^\w]{{1,12}})'
    rf'[\w-]{{1,63}}(?:[^\w]{{1,12}}){_DOT}'
    rf'(?:[^\w]{{1,12}})[^\W\d_]\w{{1,62}}',
    re.I,
)
_BRACKET_DOT = re.compile(
    rf'[^\w\s]{{1,3}}\s*(?:{_DOT}|\.)\s*[^\w\s]{{1,3}}', re.I,
)
_BRACKET_AT = re.compile(
    rf'[^\w\s]{{1,3}}\s*(?:{_AT}|@)\s*[^\w\s]{{1,3}}', re.I,
)
_DOT_WORD = re.compile(rf'(?<=\w)\s+{_DOT}\s+(?=\w)', re.I)
_AT_WORD = re.compile(rf'(?<=\w)\s+{_AT}\s+(?=\w)', re.I)

_MESSENGER_DIRECTION = re.compile(
    r'(?<!\w)(?:tg|тг|wa|ig|insta|telegram|whatsapp|instagram|'
    r'viber|wechat|skype|discord|телеграм|ватсап|вотсап|'
    r'инстаграм|טלגרם|וואטסאפ|אינסטגרם)'
    r'(?:\s*[:/@-]\s*|\s+)(?:[\w._-]{4,})(?!\w)',
    re.I,
)
_AMBIGUOUS_MESSENGER = re.compile(
    r'(?<!\w)(?:signal|dm|mail)\s*[:/@]\s*[\w._-]{4,}(?!\w)', re.I,
)
_SPACED_CHANNEL = re.compile(
    r'(?<!\w)(?:'
    r't[\W_]*e[\W_]*l[\W_]*e[\W_]*g[\W_]*r[\W_]*a[\W_]*m|'
    r'w[\W_]*h[\W_]*a[\W_]*t[\W_]*s[\W_]*a[\W_]*p[\W_]*p|'
    r'i[\W_]*n[\W_]*s[\W_]*t[\W_]*a[\W_]*g[\W_]*r[\W_]*a[\W_]*m'
    r')(?:[\W_]+)[\w._-]{4,}(?!\w)',
    re.I,
)
_PHONE_SEQUENCE = re.compile(
    r'(?<!\w)(?:\d[\W_]{0,32}){6,}\d(?!\w)',
)
_NUMBER_WORD = re.compile(
    r'(?<!\w)(?:zero|one|two|three|four|five|six|seven|eight|nine|'
    r'ноль|нуль|один|два|три|четыре|пять|шесть|семь|восемь|девять|'
    r'אפס|אחת|אחד|שתיים|שניים|שלוש|שלושה|ארבע|חמש|שש|שבע|שמונה|תשע)'
    r'(?:[\W_]+(?:zero|one|two|three|four|five|six|seven|eight|nine|'
    r'ноль|нуль|один|два|три|четыре|пять|шесть|семь|восемь|девять|'
    r'אפס|אחת|אחד|שתיים|שניים|שלוש|שלושה|ארבע|חמש|שש|שבע|שמונה|תשע)){6,}'
    r'(?!\w)',
    re.I,
)


def normalize_public_text(value):
    """Canonicalize bounded encoded/Unicode input without changing raw data."""
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
    text = re.sub(r'(?i)(?<!\w)[aа][tт](?!\w)', 'at', text)
    text = re.sub(r'(?i)(?<!\w)d[oо][tт](?!\w)', 'dot', text)
    text = re.sub(r'(?i)telegra[mм]', 'telegram', text)
    probe = _BRACKET_DOT.sub('.', text)
    probe = _BRACKET_AT.sub('@', probe)
    probe = _DOT_WORD.sub('.', probe)
    return _AT_WORD.sub('@', probe)


def contains_public_contact(value, *, allow_work_hours=False):
    """Conservative contact/link detector used before snapshot persistence."""
    text = normalize_public_text(value)
    probe = _contact_probe(text)
    without_hours = _HOURS.sub('', probe) if allow_work_hours else probe
    compact = re.sub(r'\s+', '', without_hours)

    if allow_work_hours and any(char.isdecimal() for char in without_hours):
        return True

    if _RESIDUAL_PERCENT.search(without_hours) or _RESIDUAL_ENTITY.search(without_hours):
        return True
    if '@' in without_hours or _EMAIL.search(probe) or _HANDLE.search(probe):
        return True
    if _OBFUSCATED_EMAIL.search(text):
        return True
    if _ASCII_URI.search(without_hours) or _ASCII_URI.search(compact):
        return True
    if _UNICODE_URI.search(without_hours) or _PROTOCOL_RELATIVE.search(without_hours):
        return True
    if _DOMAIN.search(probe) or _IPV4.search(probe):
        return True
    if (_MESSENGER_DIRECTION.search(without_hours)
            or _AMBIGUOUS_MESSENGER.search(without_hours)
            or _SPACED_CHANNEL.search(without_hours)):
        return True
    if _NUMBER_WORD.search(without_hours):
        return True
    return (
        bool(_PHONE_SEQUENCE.search(without_hours))
        or sum(char.isdecimal() for char in without_hours) >= 7
    )


def prepare_public_text(value, *, allow_work_hours=False):
    """Return normalized snapshot text, or ``None`` when publication is unsafe."""
    text = normalize_public_text(value)
    if contains_public_contact(text, allow_work_hours=allow_work_hours):
        return None
    return text


def _private_identifier_tokens(values):
    tokens = set()
    for value in values or ():
        text = normalize_public_text(value).casefold()
        if '@' in text:
            local = text.split('@', 1)[0]
            tokens.update(re.findall(r'[\w.-]{4,}', local))
        raw_tokens = re.findall(r'[\w.-]{4,}', text.lstrip('@'))
        tokens.update(raw_tokens)
        tokens.update(
            re.sub(r'[\W_]+', '', token)
            for token in raw_tokens
            if len(re.sub(r'[\W_]+', '', token)) >= 4
        )
        digits = ''.join(char for char in text if char.isdecimal())
        if len(digits) >= 4:
            tokens.add(digits)
    return {token.strip('._-') for token in tokens if len(token.strip('._-')) >= 4}


def build_profile_snapshot(*, display_name, description,
                           pricing_details, working_hours,
                           private_values=()):
    prepared = {
        'display_name': prepare_public_text(display_name),
        'description': prepare_public_text(description),
        'pricing_details': prepare_public_text(pricing_details),
        'working_hours': prepare_public_text(
            working_hours, allow_work_hours=True,
        ),
    }
    if any(value is None for value in prepared.values()):
        return None
    # A contact may be deliberately split between separately valid fields.
    # Evaluate their public composition as it will be exposed on one page.
    aggregate = ' '.join((
        prepared['display_name'], prepared['description'],
        prepared['pricing_details'],
        _HOURS.sub('', prepared['working_hours']),
    ))
    if contains_public_contact(aggregate):
        return None
    public_folded = normalize_public_text(aggregate).casefold()
    public_compact = re.sub(r'[\W_]+', '', public_folded)
    public_digits = ''.join(char for char in public_folded if char.isdecimal())
    for token in _private_identifier_tokens(private_values):
        if token.isdecimal():
            if token in public_digits:
                return None
        elif token in public_folded or token in public_compact:
            return None
    return prepared


def build_fail_closed_profile_snapshot(*, display_name, description,
                                       pricing_details, working_hours,
                                       private_values=()):
    """Build a safe projection even when historical raw fields are unsafe.

    A detected contact hides the complete field.  Cross-field composition or
    correlation with private identity hides all free-text fields because no
    individual fragment can then act as a search/public correlation oracle.
    """
    values = {
        'display_name': prepare_public_text(display_name),
        'description': prepare_public_text(description),
        'pricing_details': prepare_public_text(pricing_details),
        'working_hours': prepare_public_text(
            working_hours, allow_work_hours=True,
        ),
    }
    projected = {key: value or '' for key, value in values.items()}
    if any(value is None for value in values.values()):
        return projected
    strict = build_profile_snapshot(
        display_name=display_name,
        description=description,
        pricing_details=pricing_details,
        working_hours=working_hours,
        private_values=private_values,
    )
    if strict is None:
        return {key: '' for key in values}
    return strict


def build_caption_snapshot(caption):
    return prepare_public_text(caption)


def redact_public_contact(value, *, allow_work_hours=False):
    prepared = prepare_public_text(value, allow_work_hours=allow_work_hours)
    return MARKER if prepared is None else prepared


def searchable_public_text(value):
    prepared = prepare_public_text(value)
    return '' if prepared is None else ' '.join(prepared.split())


def searchable_public_name(value):
    return searchable_public_text(value)[:120]


def profile_public_content_is_safe(*, display_name, description,
                                   pricing_details, working_hours):
    return build_profile_snapshot(
        display_name=display_name,
        description=description,
        pricing_details=pricing_details,
        working_hours=working_hours,
    ) is not None


def contact_shaped_query(value):
    text = normalize_public_text(value).strip()
    if contains_public_contact(text):
        return True
    digits = ''.join(char for char in text if char.isdecimal())
    if re.fullmatch(r'(?:19|20)\d{2}', text):
        return False
    if re.fullmatch(r'(?i)ISO\s*\d{4}', text):
        return False
    return len(digits) >= 4
