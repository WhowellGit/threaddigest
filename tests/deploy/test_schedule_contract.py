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
    data = _rendered_plist("io.github.whowellgit.threaddigest.run")
    schedule = data["StartCalendarInterval"]
    assert isinstance(schedule, list)
    assert [(e["Weekday"], e["Hour"], e["Minute"]) for e in schedule] == [(1, 6, 30), (4, 6, 30)]
    assert data["ExitTimeOut"] == 10800
    assert data["RunAtLoad"] is False


def test_doctor_job_is_hourly_off_the_run_minute() -> None:
    data = _rendered_plist("io.github.whowellgit.threaddigest.doctor")
    schedule = data["StartCalendarInterval"]
    assert isinstance(schedule, dict) and set(schedule) == {"Minute"}
    assert schedule["Minute"] != 30  # never starts together with the run job


def test_wrapper_uses_the_five_day_staleness_threshold() -> None:
    """D-30: the longest healthy gap (Thursday to Monday) is four days, so the dead-man alarm
    fires at five days -- quiet when healthy, red once a run is genuinely overdue."""
    run_sh = (LAUNCHD / "run.sh").read_text(encoding="utf-8")
    assert "--alert-if-stale 5d" in run_sh
    assert "--alert-if-stale 36h" not in run_sh  # the old daily-cadence value is gone


def _longest_gap_seconds(schedule: list[dict[str, int]]) -> int:
    """The longest interval between consecutive weekly slots, wrapping round the week."""
    weekdays = sorted(entry["Weekday"] for entry in schedule)
    gaps = [b - a for a, b in zip(weekdays, weekdays[1:], strict=False)]
    gaps.append(7 - weekdays[-1] + weekdays[0])
    return max(gaps) * 86400


def test_reconcile_bounds_fit_the_schedule() -> None:
    """KI-026: the shipped reconcile-age bound for items under thirty days was the daily-era
    figure (sixty hours), shorter than the Thursday-to-Monday gap, so the M1c invariant it
    drives could never hold after one missed run. The bounds are bound to the schedule: a full
    sweep is due on every scheduled run, and the freshest tier's age bound outlasts the longest
    gap plus a run's wall-clock ceiling."""
    import yaml

    schedule = _rendered_plist("io.github.whowellgit.threaddigest.run")["StartCalendarInterval"]
    assert isinstance(schedule, list)
    weekdays = sorted(entry["Weekday"] for entry in schedule)
    gaps_days = [b - a for a, b in zip(weekdays, weekdays[1:], strict=False)]
    gaps_days.append(7 - weekdays[-1] + weekdays[0])
    settings = yaml.safe_load((REPO_ROOT / "config" / "settings.yaml").read_text(encoding="utf-8"))
    reconcile = settings["reconcile"]
    assert reconcile["full_sweep_every_hours"] <= min(gaps_days) * 24, (
        "every scheduled run must be a full sweep while it fits the budget"
    )
    ceiling = settings["run"]["wall_clock_ceiling_hours"]
    assert reconcile["tier_max_age_hours"]["under_30d"] >= max(gaps_days) * 24 + ceiling, (
        "the freshest tier's age bound must outlast the longest gap plus a run"
    )


def test_doctor_default_threshold_outlasts_the_longest_gap_and_matches_the_wrapper() -> None:
    """KI-024: the cadence sweep moved the wrapper to ``5d`` while the CLI option and the
    service parameter kept the daily-cadence default of thirty-six hours, so a bare
    ``threaddigest doctor`` alarmed on every normal Thursday-to-Monday gap. One constant is
    the home of the default; both entry points use it; it outlasts the schedule's longest gap;
    and the wrapper passes the same value, so the three can never disagree again."""
    import inspect

    from threaddigest import cli
    from threaddigest.services import doctor

    data = _rendered_plist("io.github.whowellgit.threaddigest.run")
    schedule = data["StartCalendarInterval"]
    assert isinstance(schedule, list)
    default = doctor.DEFAULT_ALERT_IF_STALE
    assert doctor.parse_duration(default) > _longest_gap_seconds(schedule)
    assert inspect.signature(doctor.run_checks).parameters["alert_if_stale"].default == default
    option = inspect.signature(cli.doctor).parameters["alert_if_stale"].default
    assert option.default == default, "the CLI option must default to the shared constant"
    run_sh = (LAUNCHD / "run.sh").read_text(encoding="utf-8")
    assert f"--alert-if-stale {default}" in run_sh
