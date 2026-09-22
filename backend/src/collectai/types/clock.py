"""Injectable Clock abstraction.

Every timestamp written by the application comes from an injected `Clock`,
never from `datetime.now()` directly or `now()` in SQL (data-models.md
section 1). Production code uses `SystemClock`; tests and the demo's
clock-advance control use `SimulatedClock`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable


@runtime_checkable
class Clock(Protocol):
    """Anything that can report the current, timezone-aware UTC instant."""

    def now(self) -> datetime:
        """Return the current instant as a timezone-aware UTC datetime."""
        ...


class SystemClock:
    """Reads the real wall clock."""

    def now(self) -> datetime:
        return datetime.now(UTC)


class SimulatedClock:
    """A settable clock for tests and the demo's simulated time control.

    `now()` returns exactly the last value set or advanced to; it never
    drifts with the real wall clock.
    """

    def __init__(self, initial: datetime) -> None:
        self._current = _to_utc(initial)

    def now(self) -> datetime:
        return self._current

    def set(self, instant: datetime) -> None:
        """Replace the current instant."""
        self._current = _to_utc(instant)

    def advance(self, days: int) -> None:
        """Move the current instant forward by a whole number of days."""
        self._current = self._current + timedelta(days=days)


def _to_utc(instant: datetime) -> datetime:
    if instant.tzinfo is None:
        raise ValueError("SimulatedClock requires a timezone-aware datetime (UTC).")
    return instant.astimezone(UTC)
