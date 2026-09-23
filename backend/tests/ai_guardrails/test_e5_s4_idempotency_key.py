"""E5-S4 AC3: `compute_idempotency_key` is a pure function -- deterministic
from `(turn_id, tool_name, canonical arguments)`, never a client-supplied
value, and never affected by dict key order.
"""

from __future__ import annotations

from collectai.ai_orchestration.schemas.tool_args import ProposePtpArgs
from collectai.ai_orchestration.tools.propose_tools import compute_idempotency_key

_ARGS = ProposePtpArgs.model_validate(
    {"account_id": "acc_000101", "promised_amount": "250.00", "promised_date": "2026-10-15"}
)


def test_same_turn_tool_and_args_produce_the_same_key() -> None:
    first = compute_idempotency_key("trn_ABC123", "propose_ptp", _ARGS)
    second = compute_idempotency_key("trn_ABC123", "propose_ptp", _ARGS)
    assert first == second


def test_different_turn_id_produces_a_different_key() -> None:
    first = compute_idempotency_key("trn_ABC123", "propose_ptp", _ARGS)
    second = compute_idempotency_key("trn_XYZ999", "propose_ptp", _ARGS)
    assert first != second


def test_different_tool_name_produces_a_different_key() -> None:
    first = compute_idempotency_key("trn_ABC123", "propose_ptp", _ARGS)
    second = compute_idempotency_key("trn_ABC123", "flag_hardship", _ARGS)
    assert first != second


def test_different_arguments_produce_a_different_key() -> None:
    other_args = ProposePtpArgs.model_validate(
        {"account_id": "acc_000101", "promised_amount": "300.00", "promised_date": "2026-10-15"}
    )
    first = compute_idempotency_key("trn_ABC123", "propose_ptp", _ARGS)
    second = compute_idempotency_key("trn_ABC123", "propose_ptp", other_args)
    assert first != second


def test_key_is_a_sha256_hex_digest() -> None:
    key = compute_idempotency_key("trn_ABC123", "propose_ptp", _ARGS)
    assert len(key) == 64
    assert all(char in "0123456789abcdef" for char in key)
