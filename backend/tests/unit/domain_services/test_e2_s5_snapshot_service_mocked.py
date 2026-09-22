"""Tests for `refresh_and_check` (E2-S5 AC5) against a mocked repository.

`domain_services.snapshot_service` treats `persistence` as its one external
boundary (code-gen skill: "only mock external boundaries: databases"), so
these tests replace `DelinquencyRecordRepository` with a fake in-memory
double rather than hitting a real database. `tests/db/test_e2_s5_snapshot_service.py`
covers the same function against a real, migrated Postgres database to prove
the wiring (ORM mapping, real repository query) actually works end to end.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from collectai.config.policy.loader import load_seed_policy_v1
from collectai.config.policy.provider import PolicyProvider
from collectai.domain_services import snapshot_service
from collectai.persistence.orm.delinquency import DelinquencyRecordOrm
from collectai.types.clock import SimulatedClock
from collectai.types.money import Money
from collectai.types.reason_codes import ReasonCode

_NOW = datetime(2026, 10, 1, 9, 0, tzinfo=UTC)
_ACCOUNT_ID = "acc_000123"
_CUSTOMER_ID = "cus_000101"
_OVERDUE_AMOUNT = Money("770.40")
_OUTSTANDING_BALANCE = Money("8420.10")


class _FakeDelinquencyRecordRepository:
    """In-memory double for `DelinquencyRecordRepository.get_by_account`."""

    def __init__(self, current_record: DelinquencyRecordOrm | None) -> None:
        self._current_record = current_record

    async def get_by_account(
        self, session: object, account_id: str, customer_id: str
    ) -> DelinquencyRecordOrm | None:
        return self._current_record


def _orm_record(
    *,
    record_version: int = 7,
    dpd: int = 34,
    bucket: str = "DPD_30_59",
    overdue_amount: Money = _OVERDUE_AMOUNT,
    outstanding_balance: Money = _OUTSTANDING_BALANCE,
) -> DelinquencyRecordOrm:
    return DelinquencyRecordOrm(
        account_id=_ACCOUNT_ID,
        customer_id=_CUSTOMER_ID,
        outstanding_balance=outstanding_balance,
        overdue_amount=overdue_amount,
        dpd=dpd,
        bucket=bucket,
        collection_status="IN_PROGRESS",
        as_of=_NOW,
        record_version=record_version,
        updated_at=_NOW,
    )


def _active_policy_provider(clock: SimulatedClock) -> PolicyProvider:
    provider = PolicyProvider()
    provider.register(load_seed_policy_v1(clock))
    provider.activate("policy-v1", clock)
    return provider


def _patch_repository(
    monkeypatch: pytest.MonkeyPatch, current_record: DelinquencyRecordOrm | None
) -> None:
    monkeypatch.setattr(
        snapshot_service,
        "DelinquencyRecordRepository",
        lambda: _FakeDelinquencyRecordRepository(current_record),
    )


@pytest.mark.asyncio
async def test_fresh_and_consistent_snapshot_returns_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC5: a fresh, consistent record yields a success result carrying both
    check outcomes and the current record."""
    clock = SimulatedClock(_NOW)
    _patch_repository(monkeypatch, _orm_record())

    result = await snapshot_service.refresh_and_check(
        session=object(),  # type: ignore[arg-type]
        account_id=_ACCOUNT_ID,
        customer_id=_CUSTOMER_ID,
        snapshot_as_of=_NOW,
        snapshot_version=7,
        policy_provider=_active_policy_provider(clock),
        clock=clock,
    )

    assert result.ok
    assert result.value is not None
    assert result.value.freshness.status.value == "FRESH"
    assert result.value.consistency.consistent is True
    assert result.value.current_record.record_version == 7


@pytest.mark.asyncio
async def test_stale_snapshot_returns_failure_never_a_success_value(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2/AC5: a stale snapshot refuses the action -- failure only, no
    eligibility/option/score-shaped success value."""
    later = datetime(2026, 10, 1, 10, 30, tzinfo=UTC)  # 90 minutes later, threshold is 60
    clock = SimulatedClock(later)
    _patch_repository(monkeypatch, _orm_record())

    result = await snapshot_service.refresh_and_check(
        session=object(),  # type: ignore[arg-type]
        account_id=_ACCOUNT_ID,
        customer_id=_CUSTOMER_ID,
        snapshot_as_of=_NOW,
        snapshot_version=7,
        policy_provider=_active_policy_provider(clock),
        clock=clock,
    )

    assert not result.ok
    assert result.value is None
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.STALE_DATA


@pytest.mark.asyncio
async def test_missing_as_of_returns_failure_with_ambiguous_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC3: freshness cannot be established -> fails closed, no state change."""
    clock = SimulatedClock(_NOW)
    _patch_repository(monkeypatch, _orm_record())

    result = await snapshot_service.refresh_and_check(
        session=object(),  # type: ignore[arg-type]
        account_id=_ACCOUNT_ID,
        customer_id=_CUSTOMER_ID,
        snapshot_as_of=None,
        snapshot_version=7,
        policy_provider=_active_policy_provider(clock),
        clock=clock,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.AMBIGUOUS_VALIDATION


@pytest.mark.asyncio
async def test_version_mismatch_returns_failure_with_ambiguous_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC2/AC3: version mismatch -> UNKNOWN/AMBIGUOUS_VALIDATION (see
    rules_engine/freshness.py module docstring for the full resolution)."""
    clock = SimulatedClock(_NOW)
    _patch_repository(monkeypatch, _orm_record(record_version=9))

    result = await snapshot_service.refresh_and_check(
        session=object(),  # type: ignore[arg-type]
        account_id=_ACCOUNT_ID,
        customer_id=_CUSTOMER_ID,
        snapshot_as_of=_NOW,
        snapshot_version=7,
        policy_provider=_active_policy_provider(clock),
        clock=clock,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.AMBIGUOUS_VALIDATION


@pytest.mark.asyncio
async def test_inconsistent_record_returns_failure_even_when_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """AC4/AC5: a fresh but internally inconsistent record is still refused."""
    clock = SimulatedClock(_NOW)
    _patch_repository(monkeypatch, _orm_record(dpd=34, bucket="CURRENT"))

    result = await snapshot_service.refresh_and_check(
        session=object(),  # type: ignore[arg-type]
        account_id=_ACCOUNT_ID,
        customer_id=_CUSTOMER_ID,
        snapshot_as_of=_NOW,
        snapshot_version=7,
        policy_provider=_active_policy_provider(clock),
        clock=clock,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.INCONSISTENT_RECORD


@pytest.mark.asyncio
async def test_missing_delinquency_record_returns_failure_not_a_crash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The account has no delinquency record at all -- a distinct failure,
    not an unhandled exception."""
    clock = SimulatedClock(_NOW)
    _patch_repository(monkeypatch, None)

    result = await snapshot_service.refresh_and_check(
        session=object(),  # type: ignore[arg-type]
        account_id=_ACCOUNT_ID,
        customer_id=_CUSTOMER_ID,
        snapshot_as_of=_NOW,
        snapshot_version=7,
        policy_provider=_active_policy_provider(clock),
        clock=clock,
    )

    assert not result.ok
    assert result.value is None
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.AMBIGUOUS_VALIDATION


@pytest.mark.asyncio
async def test_policy_unavailable_returns_failure_before_touching_the_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail-closed: no active PolicyRuleSet -> failure, independent of the record."""
    clock = SimulatedClock(_NOW)
    _patch_repository(monkeypatch, _orm_record())
    provider = PolicyProvider()  # never registered/activated

    result = await snapshot_service.refresh_and_check(
        session=object(),  # type: ignore[arg-type]
        account_id=_ACCOUNT_ID,
        customer_id=_CUSTOMER_ID,
        snapshot_as_of=_NOW,
        snapshot_version=7,
        policy_provider=provider,
        clock=clock,
    )

    assert not result.ok
    assert result.failure is not None
    assert result.failure.reason_code == ReasonCode.POLICY_UNAVAILABLE
