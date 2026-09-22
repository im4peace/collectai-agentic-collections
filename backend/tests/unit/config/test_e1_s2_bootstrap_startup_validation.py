"""Tests for fail-closed startup composition (E1-S2 AC2, AC3, AC7).

`run_startup_validation` is the narrow slice of `bootstrap/main.py` this story
owns: it loads settings and the policy provider and raises/logs a named error
if anything is invalid. It does not build an ASGI app (a later story does).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from collectai.bootstrap.main import run_startup_validation
from collectai.config.policy.loader import PolicyFileNotFoundError
from collectai.config.policy.provider import PolicyProvider
from collectai.config.policy.validator import PolicyValidationError
from collectai.config.settings import StartupConfigError
from collectai.types.clock import SimulatedClock
from collectai.types.reason_codes import ReasonCode
from collectai.types.results import PolicyUnavailable

_VALID_ENV = {
    "DATABASE_URL": "postgresql+asyncpg://collectai:synthetic@localhost:5432/collectai",
}


def test_valid_settings_and_policy_produce_an_active_provider() -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    result = run_startup_validation(env=_VALID_ENV, clock=clock)

    assert result.settings.database_url == _VALID_ENV["DATABASE_URL"]
    active = result.policy_provider.get_active()
    assert active.policy_version == "policy-v1"
    assert active.is_active is True


def test_invalid_settings_fail_startup_with_named_error() -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    with pytest.raises(StartupConfigError) as exc_info:
        run_startup_validation(env={"TOOL_CALL_CAP_PER_TURN": "0"}, clock=clock)
    assert exc_info.value.parameter in {"TOOL_CALL_CAP_PER_TURN", "DATABASE_URL"}


def test_missing_database_url_fails_startup() -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    with pytest.raises(StartupConfigError) as exc_info:
        run_startup_validation(env={}, clock=clock)
    assert exc_info.value.parameter == "DATABASE_URL"


def test_invalid_seed_policy_file_fails_startup_with_named_error(tmp_path: Path) -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    broken_file = tmp_path / "policy-v1.json"
    payload = json.loads(
        Path("src/collectai/config/policy/policy-v1.json").read_text(encoding="utf-8")
    )
    del payload["contact"]["max_attempts"]
    broken_file.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(PolicyValidationError) as exc_info:
        run_startup_validation(env=_VALID_ENV, clock=clock, policy_file_path=broken_file)
    assert "max_attempts" in exc_info.value.parameter


def test_missing_policy_file_fails_startup_with_named_error(tmp_path: Path) -> None:
    clock = SimulatedClock(datetime(2026, 9, 1, tzinfo=UTC))
    missing_file = tmp_path / "does-not-exist.json"
    with pytest.raises(PolicyFileNotFoundError):
        run_startup_validation(env=_VALID_ENV, clock=clock, policy_file_path=missing_file)


def test_no_valid_active_rule_set_fails_closed_via_policy_unavailable() -> None:
    """AC3, at this story's level: get_active() on an unactivated provider fails closed."""
    provider = PolicyProvider()
    with pytest.raises(PolicyUnavailable) as exc_info:
        provider.get_active()
    assert exc_info.value.reason_code == ReasonCode.POLICY_UNAVAILABLE
