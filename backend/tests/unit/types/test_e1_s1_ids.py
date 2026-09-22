"""Tests for prefixed id generation and validation (data-models.md section 1)."""

from __future__ import annotations

import re

import pytest

from collectai.types.ids import (
    EntityPrefix,
    InvalidIdError,
    assert_valid_id,
    generate_id,
    id_validator,
    is_valid_id,
)

_ID_SHAPE = re.compile(r"^[a-z]{3,4}_[A-Za-z0-9]{6,40}$")


def test_generate_id_produces_the_requested_prefix() -> None:
    account_id = generate_id(EntityPrefix.ACCOUNT)
    assert account_id.startswith("acc_")
    assert _ID_SHAPE.match(account_id)


def test_generate_id_accepts_a_bare_prefix_string() -> None:
    customer_id = generate_id("cus_")
    assert customer_id.startswith("cus_")


def test_generate_id_produces_distinct_time_sortable_ulids() -> None:
    first = generate_id(EntityPrefix.PROMISE_TO_PAY)
    second = generate_id(EntityPrefix.PROMISE_TO_PAY)
    assert first != second
    # Same millisecond-derived time prefix is common; the suffix differs.
    assert first[:4] == "ptp_"
    assert second[:4] == "ptp_"


@pytest.mark.parametrize(
    "prefix",
    list(EntityPrefix),
)
def test_generate_id_is_valid_for_every_entity_prefix(prefix: EntityPrefix) -> None:
    generated = generate_id(prefix)
    assert is_valid_id(generated, prefix)


def test_is_valid_id_accepts_deterministic_seed_ids() -> None:
    assert is_valid_id("acc_000123")
    assert is_valid_id("acc_000123", EntityPrefix.ACCOUNT)


def test_is_valid_id_rejects_unknown_prefix() -> None:
    assert not is_valid_id("xyz_000123")


def test_is_valid_id_rejects_wrong_prefix_for_expected_entity() -> None:
    assert not is_valid_id("acc_000123", EntityPrefix.CUSTOMER)


def test_is_valid_id_rejects_malformed_suffix() -> None:
    assert not is_valid_id("acc_")  # too short
    assert not is_valid_id("acc_has spaces")
    assert not is_valid_id("not-an-id")


def test_assert_valid_id_raises_invalid_id_error_for_bad_value() -> None:
    with pytest.raises(InvalidIdError):
        assert_valid_id("not-an-id")


def test_assert_valid_id_passes_through_a_valid_value() -> None:
    assert assert_valid_id("acc_000123", EntityPrefix.ACCOUNT) == "acc_000123"


def test_id_validator_returns_a_callable_usable_as_a_pydantic_validator() -> None:
    validate_account_id = id_validator(EntityPrefix.ACCOUNT)
    assert validate_account_id("acc_000123") == "acc_000123"
    with pytest.raises(InvalidIdError):
        validate_account_id("cus_000123")


def test_entity_prefix_covers_every_documented_prefix() -> None:
    expected = {
        "cus_",
        "acc_",
        "itm_",
        "int_",
        "ptp_",
        "pay_",
        "arr_",
        "hsp_",
        "dsp_",
        "esc_",
        "dec_",
        "conv_",
        "msg_",
        "trn_",
        "prp_",
        "rec_",
        "aud_",
        "evr_",
        "evc_",
    }
    assert {member.value for member in EntityPrefix} == expected
