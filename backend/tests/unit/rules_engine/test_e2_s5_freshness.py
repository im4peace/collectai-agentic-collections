"""Tests for `check_freshness` (E2-S5 AC1, AC2, AC3)."""

from __future__ import annotations

from datetime import UTC, datetime

from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.models import PolicyRuleSet
from collectai.rules_engine.freshness import check_freshness
from collectai.types.clock import SimulatedClock
from collectai.types.enums import Bucket, CollectionStatus, Freshness
from collectai.types.models.delinquency_record import DelinquencyRecord
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)


def _current_record(*, record_version: int = 7, as_of: datetime | None = _NOW) -> DelinquencyRecord:
    return DelinquencyRecord(
        account_id="acc_000123",
        customer_id="cus_000101",
        outstanding_balance=Money("8420.10"),
        overdue_amount=Money("770.40"),
        dpd=34,
        bucket=Bucket.DPD_30_59,
        collection_status=CollectionStatus.IN_PROGRESS,
        as_of=as_of,
        record_version=record_version,
        updated_at=_NOW,
    )


def _policy(clock: SimulatedClock) -> PolicyRuleSet:
    return load_seed_policy_v1(clock)


def test_fresh_snapshot_within_threshold_and_matching_version_is_fresh() -> None:
    """AC1: matching version, age within policy-v1's 60-minute threshold."""
    clock = SimulatedClock(_NOW)
    current_record = _current_record(record_version=7)
    policy = _policy(clock)

    result = check_freshness(
        snapshot_as_of=_NOW,
        snapshot_version=7,
        current_record=current_record,
        policy=policy,
        clock=clock,
    )

    assert result.status is Freshness.FRESH
    assert result.reason_code is None
    assert result.current_record == current_record


def test_snapshot_age_exactly_at_threshold_is_still_fresh() -> None:
    """AC1/AC2 boundary: "older than" the threshold is strict; exactly-equal age is fresh."""
    later = datetime(2026, 10, 1, 10, 0, tzinfo=UTC)  # exactly 60 minutes later
    clock = SimulatedClock(later)
    current_record = _current_record(record_version=7, as_of=_NOW)
    policy = _policy(clock)

    result = check_freshness(
        snapshot_as_of=_NOW,
        snapshot_version=7,
        current_record=current_record,
        policy=policy,
        clock=clock,
    )

    assert result.status is Freshness.FRESH
    assert result.reason_code is None


def test_snapshot_one_second_past_threshold_is_stale() -> None:
    """AC2: aged-but-version-matching snapshot -> STALE / STALE_DATA."""
    later = datetime(2026, 10, 1, 10, 0, 1, tzinfo=UTC)  # 60 minutes + 1 second later
    clock = SimulatedClock(later)
    current_record = _current_record(record_version=7, as_of=_NOW)
    policy = _policy(clock)

    result = check_freshness(
        snapshot_as_of=_NOW,
        snapshot_version=7,
        current_record=current_record,
        policy=policy,
        clock=clock,
    )

    assert result.status is Freshness.STALE
    assert result.reason_code is ReasonCode.STALE_DATA
    assert result.current_record == current_record


def test_missing_as_of_is_unknown_with_ambiguous_validation() -> None:
    """AC1/AC3: a missing as_of is never treated as fresh; it fails closed as UNKNOWN."""
    clock = SimulatedClock(_NOW)
    current_record = _current_record(record_version=7)
    policy = _policy(clock)

    result = check_freshness(
        snapshot_as_of=None,
        snapshot_version=7,
        current_record=current_record,
        policy=policy,
        clock=clock,
    )

    assert result.status is Freshness.UNKNOWN
    assert result.reason_code is ReasonCode.AMBIGUOUS_VALIDATION
    assert result.current_record == current_record


def test_version_mismatch_is_unknown_with_ambiguous_validation() -> None:
    """AC2/AC3: a version mismatch means freshness cannot be established at all,
    so it is UNKNOWN/AMBIGUOUS_VALIDATION, not STALE/STALE_DATA (see module
    docstring in rules_engine/freshness.py for the full resolution)."""
    clock = SimulatedClock(_NOW)
    current_record = _current_record(record_version=9)  # snapshot is version 7
    policy = _policy(clock)

    result = check_freshness(
        snapshot_as_of=_NOW,
        snapshot_version=7,
        current_record=current_record,
        policy=policy,
        clock=clock,
    )

    assert result.status is Freshness.UNKNOWN
    assert result.reason_code is ReasonCode.AMBIGUOUS_VALIDATION
    assert result.current_record == current_record


def test_stale_and_both_unknown_triggers_all_refuse_at_the_same_status_shape() -> None:
    """Shared assertion (AC2 + AC3): every one of the three distinct triggers
    (missing as_of, version mismatch, aged snapshot) produces a non-FRESH
    status with a non-null reason_code -- the caller can refuse uniformly."""
    clock = SimulatedClock(datetime(2026, 10, 1, 10, 0, 1, tzinfo=UTC))
    current_record_fresh_version = _current_record(record_version=7, as_of=_NOW)
    policy = _policy(clock)

    missing_as_of = check_freshness(
        snapshot_as_of=None,
        snapshot_version=7,
        current_record=current_record_fresh_version,
        policy=policy,
        clock=clock,
    )
    version_mismatch = check_freshness(
        snapshot_as_of=_NOW,
        snapshot_version=1,
        current_record=current_record_fresh_version,
        policy=policy,
        clock=clock,
    )
    aged = check_freshness(
        snapshot_as_of=_NOW,
        snapshot_version=7,
        current_record=current_record_fresh_version,
        policy=policy,
        clock=clock,
    )

    for outcome in (missing_as_of, version_mismatch, aged):
        assert outcome.status is not Freshness.FRESH
        assert outcome.reason_code is not None
