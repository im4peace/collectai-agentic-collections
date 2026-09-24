"""In-process sliding-window rate limiter (E6-S1 AC6; api-contracts.md 1.2:
"In-process sliding window per session token ... Single-instance demo; a
shared store would be needed for multiple instances.").

Pure, framework-agnostic state: `SlidingWindowRateLimiter` never imports
FastAPI, so it is trivially unit-testable and reusable from any dependency
that needs it. `api/routers/chat.py` is the one caller in this story (the
`chat:use` message endpoint, keyed by session token per api-contracts.md);
it owns turning a `RateLimitDecision(allowed=False, ...)` into the typed
`RateLimitedError` (`api/middleware/error_types.py`) that
`api/middleware/errors.py`'s handler maps to 429.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta

_WINDOW = timedelta(minutes=1)


@dataclass(frozen=True, slots=True)
class RateLimitDecision:
    allowed: bool
    retry_after_seconds: int


class SlidingWindowRateLimiter:
    """Keyed sliding-window request counter. One instance per API process
    (a module-level singleton, mirroring `api/deps.py`'s own
    `_demo_session_repository` pattern) -- state is intentionally shared
    across every request the process handles, never reset between calls."""

    def __init__(self) -> None:
        self._hits: dict[str, deque[datetime]] = {}

    def check(self, key: str, now: datetime, limit_per_minute: int) -> RateLimitDecision:
        """Record one request for `key` at `now` and report whether it is
        within `limit_per_minute` over the trailing 60 seconds. A rejected
        request (`allowed=False`) is not counted against the window -- only
        requests that were actually allowed through occupy a slot."""
        bucket = self._hits.setdefault(key, deque())
        _prune(bucket, now)
        if len(bucket) >= limit_per_minute:
            retry_after = _retry_after_seconds(bucket[0], now)
            return RateLimitDecision(allowed=False, retry_after_seconds=retry_after)
        bucket.append(now)
        return RateLimitDecision(allowed=True, retry_after_seconds=0)


def _prune(bucket: deque[datetime], now: datetime) -> None:
    cutoff = now - _WINDOW
    while bucket and bucket[0] <= cutoff:
        bucket.popleft()


def _retry_after_seconds(oldest_in_window: datetime, now: datetime) -> int:
    remaining = (oldest_in_window + _WINDOW - now).total_seconds()
    return max(1, int(remaining) + 1)
