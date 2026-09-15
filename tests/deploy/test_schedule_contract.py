"""The twice-weekly schedule and staleness contract (D-30), enforced without macOS tooling.

``tests/deploy/test_launchd.py`` runs the real artefacts (``plutil``, ``launchd``, the wrapper)
and is macOS-only, so it is deselected on the Linux CI matrix. The test-methodology seat (external
round one panel, 2026-09-15) found that this left the substance of D-30 -- the Monday/Thursday
06:30 schedule and the ``--alert-if-stale 5d`` staleness -- checked only by a local ``make check``
on the Mac. This module reads the plist template and the wrapper as text (``plistlib`` is stdlib,
cross-platform; no ``plutil``, no ``launchd``), so the same contract is enforced on every platform.
"""

from __future__ import annotations

import plistlib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
LAUNCHD = REPO_ROOT / "deploy" / "launchd"


def _rendered_plist(label: str) -> dict[str, object]:
    text = (LAUNCHD / f"{label}.plist").read_text(encoding="utf-8")
    assert "__ROOT__" in text, f"{label}.plist has no __ROOT__ placeholder"
    return plistlib.loads(text.replace("__ROOT__", str(REPO_ROOT)).encode("utf-8"))


def test_run_job_is_scheduled_monday_and_thursday_at_0630() -> None:
    """D-30: Weekday 1 (Monday) and 4 (Thursday), 06:30, and the run's 3h ExitTimeOut."""
    data = _rendered_plist("com.wesmax.insightminer.run")
    schedule = data["StartCalendarInterval"]
    assert isinstance(schedule, list)
    assert [(e["Weekday"], e["Hour"], e["Minute"]) for e in schedule] == [(1, 6, 30), (4, 6, 30)]
    assert data["ExitTimeOut"] == 10800
    assert data["RunAtLoad"] is False


def test_doctor_job_is_hourly_off_the_run_minute() -> None:
    data = _rendered_plist("com.wesmax.insightminer.doctor")
    schedule = data["StartCalendarInterval"]
    assert isinstance(schedule, dict) and set(schedule) == {"Minute"}
    assert schedule["Minute"] != 30  # never starts together with the run job


def test_wrapper_uses_the_five_day_staleness_threshold() -> None:
    """D-30: the longest healthy gap (Thursday to Monday) is four days, so the dead-man alarm
    fires at five days -- quiet when healthy, red once a run is genuinely overdue."""
    run_sh = (LAUNCHD / "run.sh").read_text(encoding="utf-8")
    assert "--alert-if-stale 5d" in run_sh
    assert "--alert-if-stale 36h" not in run_sh  # the old daily-cadence value is gone
