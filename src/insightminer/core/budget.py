"""Per-run request accounting.

Pure: no I/O. The adapter's Session hook calls ``record`` for EVERY HTTP response
(``auth.limits`` is not consulted), so ``used`` is the ground truth the run row
reports as ``api_requests``. ``reserve`` keeps a tail of the budget out of reach of
planned work so an unplanned response (a retry, a redirect) does not push the run
past its limit; ``hard_cap`` bounds ``--budget N`` and the configured limit alike.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

DEFAULT_HARD_CAP: Final = 5000


def tree_cost(more_limit: int) -> int:
    """Worst-case requests for one comment tree: the submission fetch plus one per
    ``replace_more`` expansion allowed."""
    if more_limit < 0:
        msg = f"more_limit must be >= 0, got {more_limit}"
        raise ValueError(msg)
    return 1 + more_limit


@dataclass(slots=True)
class Budget:
    """Request budget for one run. ``limit`` is clamped to ``hard_cap`` on construction."""

    limit: int
    reserve: int = 0
    hard_cap: int = DEFAULT_HARD_CAP
    used: int = 0

    def __post_init__(self) -> None:
        for name in ("limit", "reserve", "used"):
            value: int = getattr(self, name)
            if value < 0:
                msg = f"{name} must be >= 0, got {value}"
                raise ValueError(msg)
        if self.hard_cap < 1:
            msg = f"hard_cap must be >= 1, got {self.hard_cap}"
            raise ValueError(msg)
        self.limit = self.clamp(self.limit)
        if self.reserve > self.limit:
            msg = (
                f"reserve ({self.reserve}) exceeds the limit ({self.limit}); "
                "nothing could ever be afforded"
            )
            raise ValueError(msg)

    def clamp(self, requested: int) -> int:
        """Bound a requested limit to ``[0, hard_cap]``."""
        return min(max(requested, 0), self.hard_cap)

    def can_afford(self, cost: int) -> bool:
        """True when ``cost`` more responses would still leave the reserve untouched."""
        if cost < 0:
            msg = f"cost must be >= 0, got {cost}"
            raise ValueError(msg)
        return self.used + cost <= self.limit - self.reserve

    def record(self, n: int = 1) -> int:
        """Count ``n`` responses (even past the limit) and return the running total."""
        if n < 0:
            msg = f"cannot record a negative number of responses: {n}"
            raise ValueError(msg)
        self.used += n
        return self.used

    @property
    def remaining(self) -> int:
        """Responses left under the limit, ignoring the reserve; never negative."""
        return max(self.limit - self.used, 0)

    @property
    def spendable(self) -> int:
        """Responses left for planned work, i.e. above the reserve; never negative."""
        return max(self.limit - self.reserve - self.used, 0)

    @property
    def overspent(self) -> int:
        """How far ``used`` went past the limit; zero while within it."""
        return max(self.used - self.limit, 0)

    @property
    def exhausted(self) -> bool:
        """True once not even one more planned response fits above the reserve."""
        return not self.can_afford(1)
