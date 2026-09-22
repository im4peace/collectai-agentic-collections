"""Prefixed opaque id generation and validation (data-models.md section 1).

Ids are opaque prefixed strings, format `^<prefix>_[A-Za-z0-9]{6,40}$`.
Generated ids are time-sortable ULIDs so new rows cluster in the database
B-tree; seed ids are deterministic (e.g. `acc_000123`) so reseeding never
orphans audit events. Both shapes validate against the same pattern.
"""

from __future__ import annotations

import os
import re
import time
from collections.abc import Callable
from enum import StrEnum
from typing import Final

_CROCKFORD_ALPHABET: Final[str] = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
_TIMESTAMP_BITS_MASK: Final[int] = (1 << 48) - 1


class EntityPrefix(StrEnum):
    """Every id prefix in the system, including the internal-only `evc_`."""

    CUSTOMER = "cus_"
    ACCOUNT = "acc_"
    ITEM = "itm_"
    INTERACTION = "int_"
    PROMISE_TO_PAY = "ptp_"
    PAYMENT_EVENT = "pay_"
    ARRANGEMENT = "arr_"
    HARDSHIP_CASE = "hsp_"
    DISPUTE = "dsp_"
    ESCALATION_CASE = "esc_"
    DECISION = "dec_"
    CONVERSATION = "conv_"
    MESSAGE = "msg_"
    CHAT_TURN = "trn_"
    PROPOSAL = "prp_"
    RECOMMENDATION = "rec_"
    AUDIT_EVENT = "aud_"
    EVAL_RUN = "evr_"
    EVAL_CASE_RESULT = "evc_"  # internal-only: never returned by a public API


class InvalidIdError(ValueError):
    """Raised when a string does not match the expected prefixed-id shape."""

    def __init__(self, value: str, expected_prefix: str | None = None) -> None:
        self.value = value
        self.expected_prefix = expected_prefix
        message = f"Invalid id {value!r}"
        if expected_prefix is not None:
            message += f"; expected prefix {expected_prefix!r}"
        super().__init__(message)


_ID_PATTERN: Final[re.Pattern[str]] = re.compile(r"^(?P<prefix>[a-z]{3,4}_)[A-Za-z0-9]{6,40}$")
_KNOWN_PREFIXES: Final[frozenset[str]] = frozenset(member.value for member in EntityPrefix)


def _encode_base32(value: int, length: int) -> str:
    characters = [""] * length
    for index in range(length - 1, -1, -1):
        characters[index] = _CROCKFORD_ALPHABET[value & 0x1F]
        value >>= 5
    return "".join(characters)


def _generate_ulid() -> str:
    """Generate a 26-character Crockford-base32 ULID (48-bit time, 80-bit random)."""
    timestamp_ms = int(time.time() * 1000) & _TIMESTAMP_BITS_MASK
    randomness = int.from_bytes(os.urandom(10), byteorder="big")
    return _encode_base32(timestamp_ms, 10) + _encode_base32(randomness, 16)


def _prefix_value(prefix: EntityPrefix | str) -> str:
    return prefix.value if isinstance(prefix, EntityPrefix) else prefix


def generate_id(prefix: EntityPrefix | str) -> str:
    """Generate a new time-sortable, ULID-suffixed id for the given prefix."""
    prefix_value = _prefix_value(prefix)
    return f"{prefix_value}{_generate_ulid()}"


def is_valid_id(value: str, prefix: EntityPrefix | str | None = None) -> bool:
    """Return whether `value` matches the id shape (and `prefix`, if given)."""
    match = _ID_PATTERN.match(value)
    if match is None:
        return False
    found_prefix = match.group("prefix")
    if found_prefix not in _KNOWN_PREFIXES:
        return False
    if prefix is not None and found_prefix != _prefix_value(prefix):
        return False
    return True


def assert_valid_id(value: str, prefix: EntityPrefix | str | None = None) -> str:
    """Return `value` unchanged if valid, else raise `InvalidIdError`."""
    if not is_valid_id(value, prefix):
        expected = _prefix_value(prefix) if prefix is not None else None
        raise InvalidIdError(value, expected)
    return value


def id_validator(prefix: EntityPrefix | str) -> Callable[[str], str]:
    """Build a reusable validator function for a specific id prefix.

    Intended for use as a Pydantic `AfterValidator`, e.g.
    `Annotated[str, AfterValidator(id_validator(EntityPrefix.ACCOUNT))]`.
    """

    def _validate(value: str) -> str:
        return assert_valid_id(value, prefix)

    return _validate
