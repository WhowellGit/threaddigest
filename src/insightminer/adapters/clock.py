"""Clock adapters: the real wall clock and a fake that tests drive by hand."""

from __future__ import annotations

import time


class SystemClock:
    """Wall-clock ``Clock``: ``time.time()`` and ``time.sleep()``."""

    def now(self) -> int:
        return int(time.time())

    def sleep(self, seconds: float) -> None:
        time.sleep(seconds)


class FakeClock:
    """Deterministic ``Clock``; ``sleep`` records the call and advances time without blocking.

    ``sleeps`` holds every requested duration in order, so a test can assert the exact backoff
    sequence (``[30.0, 120.0, 300.0]``) a service produced.
    """

    def __init__(self, start: int = 1_757_721_600) -> None:
        self._now: float = float(start)
        self.sleeps: list[float] = []

    def now(self) -> int:
        return int(self._now)

    def sleep(self, seconds: float) -> None:
        if seconds < 0:
            msg = f"cannot sleep a negative duration: {seconds!r}"
            raise ValueError(msg)
        self.sleeps.append(float(seconds))
        self._now += seconds

    def advance(self, seconds: float) -> None:
        """Move the clock forward by ``seconds`` (negative values allowed for skew tests)."""
        self._now += seconds

    @property
    def total_slept(self) -> float:
        return sum(self.sleeps)


__all__ = ["FakeClock", "SystemClock"]
