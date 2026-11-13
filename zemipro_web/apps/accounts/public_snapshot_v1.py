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
_DOMAIN_WITH_PATH = re.compile(
    r"(?<![\w@])(?:[\w-]+\s*\.\s*)+[\w-]{2,63}"
    r"(?::\d{2,5})?\s*/\s*[^\s<>\"']+",
    re.I,
)
_BROAD_DOMAIN = re.compile(
    r'(?<![\w@])(?:[\w-]+\.)+'
    r'(?P<tld>[^\W\d_][\w-]{1,62})',
    re.I,
)
_SPACED_BROAD_DOMAIN = re.compile(
    r'(?<![\w@])(?:[\w-]+\s+\.\s+)+[^\W\d_][\w-]{1,62}',
    re.I,
)
_CONTACT_INTENT = re.compile(
    r'(?<!\w)(?:contact|visit|see|website|web\s*site|url|link|reach|message|'
    r'контакт|сайт|ссылка|пишите|связаться|'
    r'צור\s+קשר|אתר|קישור)(?!\w)',
    re.I,
)
_SAFE_DOTTED_TECH_NAMES = frozenset({
    'react.js', 'node.js', 'next.js', 'nuxt.js', 'vue.js', 'angular.js',
    'asp.net',
})
_SAFE_DOTTED_ABBREVIATIONS = frozenset({'e.g', 'i.e', 'u.s', 'u.k'})
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
_PRIVATE_LABEL_PREFIX = re.compile(
    r'^(?:telegram|instagram|whatsapp|contact|phone|email|tel|tg|ig|wa|'
    r'телеграм|инстаграм|ватсап|контакт|телефон|почта|'
    r'טלגרם|אינסטגרם|וואטסאפ|קשר|טלפון|דוא[״"]?ל)\b\s*[:/-]?\s*',
    re.I,
)
_GENERIC_MAILBOX_LOCALS = frozenset({
    'admin', 'contact', 'hello', 'help', 'info', 'mail', 'office', 'sales',
    'service', 'support', 'team',
})


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


def _has_domain_contact(text):
    """Reject arbitrary domain-like tokens without maintaining a TLD list.

    A deliberately narrow exception preserves common technology names such as
    ``React.js developer``.  Domains with paths, ports or URI syntax are
    rejected by the earlier unconditional detectors.
    """
    if _DOMAIN_WITH_PATH.search(text):
        return True
    has_contact_intent = bool(_CONTACT_INTENT.search(text))
    for match in _SPACED_BROAD_DOMAIN.finditer(text):
        token = re.sub(r'\s+', '', match.group(0)).strip('.!?').casefold()
        if re.match(r'\s*[?#/:]', text[match.end():]):
            return True
        if (
            token in _SAFE_DOTTED_TECH_NAMES
            or token in _SAFE_DOTTED_ABBREVIATIONS
        ) and not has_contact_intent:
            continue
        return True
    fixed_matches = list(_DOMAIN.finditer(text))
    broad_matches = list(_BROAD_DOMAIN.finditer(text))
    for match in fixed_matches:
        token = re.sub(r'\s+', '', match.group(0)).strip('.!?').casefold()
        if re.match(r'\s*[?#/:]', text[match.end():]):
            return True
        if token in _SAFE_DOTTED_TECH_NAMES and not has_contact_intent:
            continue
        return True
    for match in broad_matches:
        token = match.group(0).casefold()
        if re.match(r'\s*[?#/:]', text[match.end():]):
            return True
        if token in _SAFE_DOTTED_TECH_NAMES and not has_contact_intent:
            continue
        if token.strip('.!?') in _SAFE_DOTTED_ABBREVIATIONS:
            continue
        # A contiguous dotted token is domain-shaped regardless of TLD case or
        # surrounding prose. Human abbreviations with whitespace after the dot
        # ("Dr. Cohen", "Ltd. Company") do not match _BROAD_DOMAIN.
        return True
    return False


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
    if _has_domain_contact(probe) or _IPV4.search(probe):
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
        split_components = False
        digits = ''.join(char for char in text if char.isdecimal())
        if len(digits) >= 4:
            tokens.add(digits)
        email_match = _EMAIL.search(text)
        handle_tokens = re.findall(r'@\s*([\w][\w._-]*)', text)
        if email_match:
            split_components = True
            # Labels such as "Email:" are not identity.  Only the mailbox
            # local-part immediately before @ can correlate a public profile.
            local_tokens = re.findall(
                r'[\w.-]{1,}', email_match.group(0).split('@', 1)[0],
            )
            raw_tokens = local_tokens[-1:]
            if raw_tokens and raw_tokens[0].strip('._-') in _GENERIC_MAILBOX_LOCALS:
                raw_tokens = []
        elif handle_tokens:
            split_components = True
            # Handles may be prefixed by labels ("Telegram: @name").  The
            # token after @ is the private identifier, never the label.
            raw_tokens = handle_tokens
        else:
            label_match = _PRIVATE_LABEL_PREFIX.match(text)
            candidate = text[label_match.end():] if label_match else text
            if '://' in candidate:
                candidate = candidate.split('://', 1)[1]
            minimum = 3 if label_match else 4
            raw_tokens = re.findall(
                rf'[\w.-]{{{minimum},}}', candidate,
            )[-1:]
        tokens.update(raw_tokens)
        tokens.update(
            compact for token in raw_tokens
            if len(compact := re.sub(r'[\W_]+', '', token)) >= 4
        )
        # Meaningful alphabetic components remain correlation identifiers when
        # a private handle/mailbox mixes letters with digits or punctuation.
        if split_components:
            for token in raw_tokens:
                tokens.update(
                    component for component in re.findall(r'[^\W\d_]{3,}', token)
                    if component not in _GENERIC_MAILBOX_LOCALS
                )
    return {
        stripped for token in tokens
        if len(stripped := token.strip('._-')) >= 3
    }


def _projection_is_safe(prepared, private_values):
    aggregate = ' '.join((
        prepared['display_name'], prepared['description'],
        prepared['pricing_details'],
        _HOURS.sub('', prepared['working_hours']),
    ))
    if contains_public_contact(aggregate):
        return False
    public_folded = normalize_public_text(aggregate).casefold()
    public_compact = re.sub(r'[\W_]+', '', public_folded)
    public_digits = ''.join(char for char in public_folded if char.isdecimal())
    display_folded = normalize_public_text(prepared['display_name']).casefold()
    display_words = set(re.findall(r'[\w.-]+', display_folded))
    display_compact_words = {
        re.sub(r'[\W_]+', '', word) for word in display_words
    }
    for token in _private_identifier_tokens(private_values):
        if token.isdecimal():
            if token in public_digits:
                return False
        elif len(token) == 3:
            # Three-character identifiers are meaningful only as an exact
            # public-name component. Comparing them to arbitrary prose would
            # reject common words based on a private short mailbox/handle.
            if token in display_words or token in display_compact_words:
                return False
        elif token in public_folded or token in public_compact:
            return False
    return True


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
    if not _projection_is_safe(prepared, private_values):
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
    if not _projection_is_safe(projected, private_values):
        return {key: '' for key in values}
    return projected


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
