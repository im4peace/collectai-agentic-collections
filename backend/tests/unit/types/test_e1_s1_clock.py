"""Tests for the injectable Clock abstraction (E1-S1 AC3)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

import pytest

from collectai.types.clock import Clock, SimulatedClock, SystemClock


def test_system_clock_returns_a_timezone_aware_utc_datetime() -> None:
    clock = SystemClock()
    before = datetime.now(UTC)
    now = clock.now()
    after = datetime.now(UTC)

    assert now.tzinfo is not None
    assert now.utcoffset() == timedelta(0)
    assert before <= now <= after


def test_system_clock_satisfies_the_clock_protocol() -> None:
    assert isinstance(SystemClock(), Clock)


def test_simulated_clock_satisfies_the_clock_protocol() -> None:
    assert isinstance(SimulatedClock(datetime(2026, 1, 1, tzinfo=UTC)), Clock)


def test_simulated_clock_now_returns_exactly_the_value_set() -> None:
    fixed_instant = datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
    clock = SimulatedClock(fixed_instant)

    assert clock.now() == fixed_instant
    assert clock.now() == fixed_instant  # calling again does not drift


def test_simulated_clock_advance_moves_forward_by_whole_days() -> None:
    clock = SimulatedClock(datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC))

    clock.advance(days=5)

    assert clock.now() == datetime(2026, 10, 6, 9, 0, 0, tzinfo=UTC)


def test_simulated_clock_advance_is_cumulative() -> None:
    clock = SimulatedClock(datetime(2026, 10, 1, tzinfo=UTC))

    clock.advance(days=3)
    clock.advance(days=2)

    assert clock.now() == datetime(2026, 10, 6, tzinfo=UTC)


def test_simulated_clock_set_replaces_the_current_instant() -> None:
    clock = SimulatedClock(datetime(2026, 10, 1, tzinfo=UTC))
    new_instant = datetime(2027, 1, 1, tzinfo=UTC)

    clock.set(new_instant)

    assert clock.now() == new_instant


def test_simulated_clock_rejects_naive_datetimes() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        SimulatedClock(datetime(2026, 10, 1))


def test_simulated_clock_normalizes_non_utc_timezones_to_utc() -> None:
    plus_two = timezone(timedelta(hours=2))
    clock = SimulatedClock(datetime(2026, 10, 1, 11, 0, 0, tzinfo=plus_two))

    assert clock.now() == datetime(2026, 10, 1, 9, 0, 0, tzinfo=UTC)
