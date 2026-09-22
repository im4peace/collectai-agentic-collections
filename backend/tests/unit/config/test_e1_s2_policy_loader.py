"""Tests for loading a PolicyRuleSet from a JSON file (E1-S2 AC1)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from collectai.config.policy.loader import (
    PolicyFileNotFoundError,
    load_policy_rule_set_from_file,
    load_seed_policy_v1,
)
from collectai.config.policy.validator import PolicyValidationError
from collectai.types.clock import SimulatedClock
from collectai.types.enums import EscalationReason
from collectai.types.money import Money


def test_loading_seed_policy_v1_returns_expected_version_and_parameters() -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    rule_set = load_seed_policy_v1(clock)

    assert rule_set.policy_version == "policy-v1"
    assert rule_set.parameters.ptp.min_amount == Money("10.00")
    assert rule_set.parameters.arrangement.installment_counts == [3, 6, 12]
    assert len(rule_set.parameters.routing.table) == len(EscalationReason)
    assert rule_set.created_at == datetime(2026, 9, 1, tzinfo=UTC)
    assert rule_set.is_active is False
    assert rule_set.activated_at is None
    assert len(rule_set.content_hash) == 64


def test_loader_uses_injected_clock_for_created_at() -> None:
    clock = SimulatedClock(datetime(2030, 1, 15, tzinfo=UTC))
    rule_set = load_seed_policy_v1(clock)
    assert rule_set.created_at == datetime(2030, 1, 15, tzinfo=UTC)


def test_loading_missing_file_raises_named_error() -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    with pytest.raises(PolicyFileNotFoundError):
        load_policy_rule_set_from_file(
            Path("does/not/exist.json"), policy_version="policy-v1", clock=clock
        )


def test_loading_invalid_rule_set_raises_policy_validation_error(tmp_path: Path) -> None:
    invalid_path = tmp_path / "policy-invalid.json"
    payload = json.loads(
        Path("src/collectai/config/policy/policy-v1.json").read_text(encoding="utf-8")
    )
    del payload["ptp"]["min_amount"]
    invalid_path.write_text(json.dumps(payload), encoding="utf-8")

    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    with pytest.raises(PolicyValidationError) as exc_info:
        load_policy_rule_set_from_file(invalid_path, policy_version="policy-v1", clock=clock)
    assert "min_amount" in exc_info.value.parameter


def test_loading_malformed_json_raises_named_error(tmp_path: Path) -> None:
    malformed_path = tmp_path / "policy-malformed.json"
    malformed_path.write_text("{not valid json", encoding="utf-8")

    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    with pytest.raises(PolicyValidationError):
        load_policy_rule_set_from_file(malformed_path, policy_version="policy-v1", clock=clock)
