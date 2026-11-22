"""Moderation of player-authored messages, never an interpreter or SQL defense."""

import re
import unicodedata

URL_ERROR = "Use plain text without links."
DATABASE_ERROR = "Use plain text without database commands."
TEXT_LIMIT_ERROR = "Shorten your message and try again."
# The app's original per-field limits are applied separately (8,000 max today).
SCAN_LIMIT = 8000

_CONTACT = re.compile(
    r"(?<![\w+.-])(?:[a-z][a-z0-9+.-]{0,31}://|mailto:|tel:(?=[+\d])|"
    r"sms:(?=[+\d])|www\.)",
    re.IGNORECASE | re.ASCII,
)
_DOMAIN = re.compile(
    r"(?<![\w-])(?:[^\W_](?:[^\W_]|-){0,62}\.){1,31}"
    r"(?:[^\W\d_]{2,63}|xn--[a-z0-9-]{2,59})(?![\w-])",
    re.IGNORECASE,
)
# Only explicit address syntax, not stand-alone version numbers.
_NUMERIC_ADDRESS = re.compile(r"(?<![\w.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?=[:/])")
_MARKUP_LINK = re.compile(r"\[[^]\n]{1,180}\]\(\s*(?:/|#|\.{1,2}/)")

# Match recognizably structured statement forms. Single words such as
# "select", "drop", "update" and "table" are normal adventure vocabulary.
_IDENTIFIER = r'(?:[a-z_][a-z0-9_]*|"[a-z_][a-z0-9_]*"|\x60[a-z_][a-z0-9_]*\x60|\[[a-z_][a-z0-9_]*\])'
_ID = _IDENTIFIER + rf'(?:\.{_IDENTIFIER})?'
_SELECT_VALUE = rf'(?:\*|{_ID})'
_END = r'(?:\b(?:where|join|group\s+by|order\s+by|limit|offset)\b|[;)]|$)'
_DB_STATEMENTS = tuple(re.compile(rf'(?<![\w])(?:{s})', re.IGNORECASE | re.ASCII) for s in (
    rf'select\s+{_SELECT_VALUE}(?:\s*,\s*{_SELECT_VALUE})*\s+from\s+{_ID}\s*{_END}',
    r'select\s+[0-9]+\s*(?:;|$)',
    rf'select\s+(?:distinct\s+)?(?:count|sum|avg|min|max)\s*\(\s*{_SELECT_VALUE}\s*\)\s+from\s+{_ID}',
    rf'delete\s+from\s+{_ID}\s*{_END}',
    rf'update\s+{_ID}\s+set\s+{_ID}\s*=',
    rf'insert\s+into\s+{_ID}(?:\s*\([^)]{{1,500}}\))?\s+(?:values\s*\(|select\s+)',
    rf'(?:drop|truncate)\s+(?:table|database|view|index|schema)\s+(?:if\s+exists\s+)?{_ID}\s*(?:[;)]|$)',
    rf'create\s+table\s+(?:if\s+not\s+exists\s+)?{_ID}\s*\(',
    rf'alter\s+table\s+{_ID}\s+(?:(?:add|drop|rename)\s+column|rename\s+to)\s+{_ID}',
    rf'create\s+(?:unique\s+)?index\s+{_ID}\s+on\s+{_ID}\s*\(',
))


def post_rule_error(value: str, *, allow_urls: bool = False) -> str | None:
    """Return a neutral error or None without changing or retaining input.

    Matching uses a bounded normalized copy, not the stored/rendered text.
    allow_urls is reserved for a caller's *already authorized* official
    content. It never exempts a database statement from this content rule.
    Escaped output and parameterized database calls remain required.
    """
    if len(value) > SCAN_LIMIT:
        return TEXT_LIMIT_ERROR
    normalized = unicodedata.normalize('NFKC', value).translate(
        {0x3002: '.', 0xff61: '.', 0x200b: None, 0x2060: None, 0xfeff: None}
    )
    if len(normalized) > SCAN_LIMIT:
        return TEXT_LIMIT_ERROR
    sql = normalized.strip()
    if any(pattern.search(sql) for pattern in _DB_STATEMENTS):
        return DATABASE_ERROR
    if not allow_urls and any(test.search(normalized)
                              for test in (_CONTACT, _DOMAIN, _NUMERIC_ADDRESS, _MARKUP_LINK)):
        return URL_ERROR
    return None
