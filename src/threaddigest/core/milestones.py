"""Revisit ladder: when a post's comment tree is re-fetched next.

Pure: no I/O and no clock. Every result is derived from ``created_utc`` (Reddit's
clock) so the schedule never depends on when the collector happens to run, and
``next_check_at`` is never ``None`` and never a far-future sentinel: past the last
rung the ladder keeps climbing in multiples of the last rung.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

DAY_SECONDS: Final = 86_400

#: Days after ``created_utc`` at which the tree is re-fetched (docs/PLAN.md, step 3,
#: with the 365-day stage added by the adversarial review).
DEFAULT_LADDER_DAYS: Final[tuple[int, ...]] = (1, 3, 7, 30, 365)


def next_check(
    created_utc: int,
    stage: int,
    ladder_days: Sequence[int] = DEFAULT_LADDER_DAYS,
) -> tuple[int, int]:
    """Return ``(next_check_at, next_stage)`` for the check at ladder index ``stage``.

    ``stage`` is the index of the check being scheduled: ``0`` at discovery schedules
    the first rung (``created_utc + 1 day`` with the default ladder), and the
    returned ``next_stage == stage + 1`` is what to pass back in once that check has
    run. Beyond the last rung the schedule continues at ``created_utc +
    last_days * k`` days with ``k = stage - len(ladder_days) + 2``, so the result is
    always an integer strictly greater than ``created_utc`` and strictly increasing
    in ``stage``.

    ``ladder_days`` must be a non-empty, strictly increasing sequence of positive
    day counts.
    """
    if stage < 0:
        msg = f"stage must be >= 0, got {stage}"
        raise ValueError(msg)
    _validate_ladder(ladder_days)
    rungs = len(ladder_days)
    if stage < rungs:
        days = ladder_days[stage]
    else:
        days = ladder_days[-1] * (stage - rungs + 2)
    return created_utc + days * DAY_SECONDS, stage + 1


def _validate_ladder(ladder_days: Sequence[int]) -> None:
    if not ladder_days:
        msg = "ladder_days must not be empty"
        raise ValueError(msg)
    if ladder_days[0] < 1:
        msg = f"ladder_days must be positive, got {list(ladder_days)}"
        raise ValueError(msg)
    for earlier, later in zip(ladder_days, ladder_days[1:], strict=False):
        if later <= earlier:
            msg = f"ladder_days must be strictly increasing, got {list(ladder_days)}"
            raise ValueError(msg)
