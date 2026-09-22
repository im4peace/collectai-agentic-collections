"""Secret and prohibited-identifier redaction before an audit event is
stored (E1-S4 AC4; BRD 13.1 row 16).

Independent of `persistence/seed/scanner.py`: that module *validates* seed
data and fails a build if a prohibited pattern is found; this module
*transforms* arbitrary audit content by replacing any matching span with
`"[REDACTED]"` so the row can still be stored. The two modules deliberately
do not share regex objects -- different purpose (reject vs. redact), and
sharing would couple audit's writes to seed's validation.
"""

from __future__ import annotations

import re
from typing import Final

_API_KEY_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\bsk-ant-[A-Za-z0-9\-_]{8,}\b|\bsk-[A-Za-z0-9]{16,}\b|\bBearer\s+[A-Za-z0-9._\-]{8,}\b"
)
_CARD_LIKE_DIGIT_RUN: Final[re.Pattern[str]] = re.compile(r"\b\d{13,19}\b")
_SSN_SHAPED: Final[re.Pattern[str]] = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_CVV_OR_PIN_LABELLED: Final[re.Pattern[str]] = re.compile(
    r"\b(CVV|PIN)\b\s*[:=]?\s*\d{3,4}\b", re.IGNORECASE
)

_REDACTED: Final[str] = "[REDACTED]"
_PATTERNS: Final[tuple[re.Pattern[str], ...]] = (
    _API_KEY_PATTERN,
    _CARD_LIKE_DIGIT_RUN,
    _SSN_SHAPED,
    _CVV_OR_PIN_LABELLED,
)


def redact_text(text: str) -> str:
    """Replace every secret/prohibited-identifier match in `text` with
    `"[REDACTED]"`. Text with no match is returned unchanged."""
    redacted = text
    for pattern in _PATTERNS:
        redacted = pattern.sub(_REDACTED, redacted)
    return redacted


def redact_value(value: object) -> object:
    """Recursively redact every string found in `value` (dict, list, str, or
    a scalar passed through unchanged). Mirrors the recursive-walk shape of
    `persistence/seed/scanner.py`'s `_iter_string_values`, but transforms
    instead of collecting."""
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {key: redact_value(nested) for key, nested in value.items()}
    if isinstance(value, list):
        return [redact_value(nested) for nested in value]
    return value
