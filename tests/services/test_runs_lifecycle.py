"""RL-03: ``services/runs.py``'s run lifecycle -- ``sweep_stale``'s stale rules, the
stage-aware heartbeat, ``resolve_status`` and the ``cancelled`` finish
(design-round5.md §12.1, §12.2, §12.4, §12.5).

The RL-03 rows come first. The sections after them carry no spec id and are named here so a
reviewer can object (§16's closing note): they pin the rest of the module's declared surface
-- T2/T3's row and baselines, the heartbeat throttle, ``dry_context``, ``Counters`` (§13.1's
round-trip), ``sync_budget`` (§6.6) and the wall-clock ceiling (§12.3) -- which nothing else
in this tranche reaches until steps 4-7.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, select

from insightminer import __version__
from insightminer.adapters.reddit_fake import FakeRedditGateway
from insightminer.core.retry import RunStatus
from insightminer.db import migrate, repo
from insightminer.db.engine import engine_for
from insightminer.db.schema import Base
from insightminer.services import runs
from insightminer.settings import Settings, settings_fingerprint

STALE_AFTER_SECONDS = 180  # settings.static.run.stale_after_minutes (3) * 60, config/settings.yaml
QUEUED_GRACE_SECONDS = runs.STALE_QUEUED_SECONDS


def _run_row(engine: Engine, pk: int) -> dict[str, Any]:
    """Read one ``runs`` row by pk (``tests/db/sqlhelp.read_run`` only reads the newest)."""
    runs_table = Base.metadata.tables["runs"]
    with engine.connect() as conn:
        row = conn.execute(select(runs_table).where(runs_table.c.pk == pk)).mappings().one()
    return dict(row)


# --- sweep_stale: the four `running` clauses and the `queued` grace (§12.2) ------------------


def test_stale_running_row_is_marked_crashed(engine: Engine, plant_run: Any, now: int) -> None:
    """Clause 3: a heartbeat older than the stale window crashes the row, even a live pid."""
    pk = plant_run(status="running", pid=1, heartbeat_at=now - STALE_AFTER_SECONDS - 1)

    with engine.begin() as conn:
        result = runs.sweep_stale(
            conn,
            now=now,
            this_pid=os.getpid(),
            this_run_pk=None,
            stale_after_seconds=STALE_AFTER_SECONDS,
        )

    assert pk in result.crashed
    assert result.failed_queued == ()
    assert result.total == 1
    row = _run_row(engine, pk)
    assert row["status"] == "crashed"
    assert row["finished_at"] is not None
    assert row["error"] is not None


def test_hard_crash_then_immediate_rerun_marks_the_row_crashed(
    engine: Engine, plant_run: Any, clock: Any, settings: Any, now: int
) -> None:
    """Clauses 1/2: a dead pid crashes the row, and a following run recovers cleanly."""
    dead_pid = 2**31 - 1
    pk = plant_run(status="running", pid=dead_pid, heartbeat_at=now)

    with engine.begin() as conn:
        result = runs.sweep_stale(
            conn,
            now=now,
            this_pid=os.getpid(),
            this_run_pk=None,
            stale_after_seconds=STALE_AFTER_SECONDS,
        )
    assert pk in result.crashed
    assert _run_row(engine, pk)["status"] == "crashed"

    # The next run does not trip over the now-crashed row: it starts cleanly and is the
    # only `running` row in the database.
    ctx = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)
    assert ctx.run_pk != pk
    with engine.connect() as conn:
        others = repo.running_runs(conn, exclude_pk=ctx.run_pk)
    assert others == []


def test_a_running_row_with_our_own_pid_is_crashed(
    engine: Engine, plant_run: Any, now: int
) -> None:
    """Clause 4: OUR OWN pid on a `running` row can only be a run already over (§12.2)."""
    ours = plant_run(status="running", pid=os.getpid(), heartbeat_at=now)
    someone_elses = plant_run(status="running", pid=1, heartbeat_at=now)

    with engine.begin() as conn:
        result = runs.sweep_stale(
            conn,
            now=now,
            this_pid=os.getpid(),
            this_run_pk=None,
            stale_after_seconds=STALE_AFTER_SECONDS,
        )

    assert ours in result.crashed
    assert someone_elses not in result.crashed
    assert _run_row(engine, ours)["status"] == "crashed"
    assert _run_row(engine, someone_elses)["status"] == "running"


def test_a_running_row_with_no_pid_is_crashed(engine: Engine, plant_run: Any, now: int) -> None:
    """Clause 1: a `running` row that never recorded a pid cannot be alive (§12.2)."""
    pk = plant_run(status="running", pid=None, heartbeat_at=now)

    with engine.begin() as conn:
        result = runs.sweep_stale(
            conn,
            now=now,
            this_pid=os.getpid(),
            this_run_pk=None,
            stale_after_seconds=STALE_AFTER_SECONDS,
        )

    assert pk in result.crashed
    assert _run_row(engine, pk)["status"] == "crashed"


def test_a_running_row_that_never_beat_falls_back_to_its_start_stamps(
    engine: Engine, plant_run: Any, now: int
) -> None:
    """Clause 3 coalesces: a run that died before its first heartbeat is judged on
    ``started_at``, and one that never started on ``created_at`` (§12.2)."""
    never_started = plant_run(
        status="running", pid=1, started_at=None, created_at=now - STALE_AFTER_SECONDS - 1
    )
    died_before_beating = plant_run(
        status="running", pid=1, started_at=now - STALE_AFTER_SECONDS - 1
    )
    just_started = plant_run(status="running", pid=1, started_at=now)

    with engine.begin() as conn:
        result = runs.sweep_stale(
            conn,
            now=now,
            this_pid=os.getpid(),
            this_run_pk=None,
            stale_after_seconds=STALE_AFTER_SECONDS,
        )

    assert set(result.crashed) == {never_started, died_before_beating}
    assert _run_row(engine, just_started)["status"] == "running"


def test_fresh_heartbeat_with_a_live_pid_survives(engine: Engine, plant_run: Any, now: int) -> None:
    """A `running` row with a fresh heartbeat and a live, non-our pid is left alone."""
    pk = plant_run(status="running", pid=1, heartbeat_at=now)

    with engine.begin() as conn:
        result = runs.sweep_stale(
            conn,
            now=now,
            this_pid=os.getpid(),
            this_run_pk=None,
            stale_after_seconds=STALE_AFTER_SECONDS,
        )

    assert result.total == 0
    assert _run_row(engine, pk)["status"] == "running"


def test_orphan_queued_row_older_than_two_minutes_fails(
    engine: Engine, plant_run: Any, now: int
) -> None:
    """A pid-less `queued` row past the grace period is a Popen failure, not a live request."""
    orphan = plant_run(
        status="queued", pid=None, started_at=None, created_at=now - QUEUED_GRACE_SECONDS - 1
    )
    fresh = plant_run(status="queued", pid=None, started_at=None, created_at=now - 1)

    with engine.begin() as conn:
        result = runs.sweep_stale(
            conn,
            now=now,
            this_pid=os.getpid(),
            this_run_pk=None,
            stale_after_seconds=STALE_AFTER_SECONDS,
        )

    assert orphan in result.failed_queued
    assert fresh not in result.failed_queued
    assert _run_row(engine, orphan)["status"] == "failed"
    assert _run_row(engine, fresh)["status"] == "queued"


# --- the stage-aware heartbeat (§12.4) --------------------------------------------------------


def test_rate_wait_stage_is_written_before_the_sleep(
    run_context: Any, engine: Engine, clock: Any
) -> None:
    """The stage lands on the row as its own statement, independent of the sleep that follows."""
    runs.heartbeat(run_context, stage="rate_wait:37s")
    assert _run_row(engine, run_context.run_pk)["stage"] == "rate_wait:37s"

    clock.sleep(37.0)  # the wait itself, simulated after the write already landed

    assert clock.sleeps == [37.0]
    assert _run_row(engine, run_context.run_pk)["stage"] == "rate_wait:37s"


def test_two_different_stages_in_one_second_both_reach_the_row(
    run_context: Any, engine: Engine, clock: Any
) -> None:
    """A changed stage always writes; the 5 s throttle only drops a REPEATED stage (§12.4)."""
    started_at = clock.now()

    runs.heartbeat(run_context, stage="sweep:premiere:p1")
    assert _run_row(engine, run_context.run_pk)["stage"] == "sweep:premiere:p1"

    runs.heartbeat(run_context, stage="retry:premiere:30s")
    assert _run_row(engine, run_context.run_pk)["stage"] == "retry:premiere:30s"

    # The clock never moved: both beats really did land inside the same second.
    assert clock.now() == started_at


# --- resolve_status (§12.1, amended by round5-findings.json's resolve_status_precedence) -----


@dataclass(frozen=True, slots=True)
class _StubViolation:
    """A minimal stand-in for ``services.invariants.Violation``, not declared until step 5.

    ``resolve_status`` is documented to read only ``.severity``; ``Severity`` is a
    ``StrEnum`` so a plain string compares equal to it, and this stub keeps the test
    independent of a module this step does not create.
    """

    severity: str


def test_a_failure_violation_outranks_a_terminal_status() -> None:
    """Owner decision (round5-findings.json, ``resolve_status_precedence``): a FAILURE
    violation wins over a terminal status, so a rate-limited run whose invariants also
    catch a bookkeeping mismatch is reported `failed` (exit 1), not `rate_limited` -- the
    amber-vs-red distinction §14.1 argues for is not silently discarded by clause order."""
    failure = _StubViolation(severity="failure")
    warning = _StubViolation(severity="warning")

    assert runs.resolve_status(RunStatus.RATE_LIMITED, (failure,), ()) is RunStatus.FAILED
    assert runs.resolve_status(RunStatus.NETWORK, (failure,), ()) is RunStatus.FAILED
    # A WARNING violation does not override a terminal status; only FAILURE does.
    assert runs.resolve_status(RunStatus.RATE_LIMITED, (warning,), ()) is RunStatus.RATE_LIMITED
    # With no terminal status the ordinary ladder applies.
    assert runs.resolve_status(None, (), ()) is RunStatus.OK
    assert runs.resolve_status(None, (warning,), ()) is RunStatus.PARTIAL
    assert runs.resolve_status(None, (failure,), ()) is RunStatus.FAILED


# --- KeyboardInterrupt: the cancelled finish (§9, §12.1) --------------------------------------


def _interrupted_sweep() -> None:
    """Stands in for a `sweep.sweep_all` that Ctrl-C lands inside, mid-page (§12.1)."""
    raise KeyboardInterrupt


def test_keyboard_interrupt_finishes_the_run_cancelled(run_context: Any, engine: Engine) -> None:
    """``runs.finish_run_from`` closes the row `cancelled` with the counters gathered so far
    and a NULL ``violations_json`` -- the building block ``collect``'s single
    ``KeyboardInterrupt`` catch site (§12.1, step 7) calls before re-raising nothing."""
    run_context.counters.posts_new = 5

    with pytest.raises(KeyboardInterrupt):
        try:
            _interrupted_sweep()
        except KeyboardInterrupt:
            runs.finish_run_from(
                run_context, status=RunStatus.CANCELLED, violations_json=None, error=None
            )
            raise

    row = _run_row(engine, run_context.run_pk)
    assert row["status"] == "cancelled"
    assert row["finished_at"] is not None
    assert row["violations_json"] is None
    assert json.loads(row["counters_json"])["posts_new"] == 5


# --- T2/T3: the row start_run commits and the baselines it reads after it (§7, §13.2) --------


def test_start_run_commits_a_running_row_with_versions_fingerprint_and_baselines(
    engine: Engine, clock: Any, settings: Settings, now: int
) -> None:
    """T2 commits the row on its own before any fetch; T3 reads the DB-54 baselines after it.

    ``praw_version`` stays NULL in tranche A: no PRAW adapter exists, so a version here would
    claim a library the run never called (§2.1).
    """
    ctx = runs.start_run(
        engine,
        kind="run",
        trigger="cli",
        clock=clock,
        settings=settings,
        options_json='{"no_comments":true}',
    )

    row = _run_row(engine, ctx.run_pk)
    assert row["status"] == "running"
    assert row["kind"] == "run"
    assert row["trigger"] == "cli"
    assert row["pid"] == os.getpid()
    assert row["created_at"] == now
    assert row["started_at"] == now
    assert row["finished_at"] is None
    assert row["stage"] is None
    assert row["options_json"] == '{"no_comments":true}'
    assert row["app_version"] == __version__
    assert row["praw_version"] is None
    assert row["schema_rev"] == migrate.head_revision()
    assert row["settings_fingerprint"] == settings_fingerprint(settings)

    assert ctx.persisted is True
    assert ctx.dry_run is False
    assert ctx.terminal_status is None
    assert ctx.workspace_pk > 0
    assert ctx.counters.as_dict() == dict.fromkeys(runs.Counters.KEYS, 0)
    assert ctx.baseline_counts == dict.fromkeys(runs.TRACKED_TABLES, 0)


# --- the heartbeat throttle, and a beat that carries no stage (§12.4) ------------------------


def test_a_repeated_stage_inside_the_throttle_does_not_touch_the_row(
    run_context: Any, engine: Engine, clock: Any
) -> None:
    """The 5 s throttle drops a REPEATED stage: that is the half §12.4 keeps."""
    runs.heartbeat(run_context, stage="sweep:premiere:p1")
    first_beat = _run_row(engine, run_context.run_pk)["heartbeat_at"]

    clock.advance(runs.HEARTBEAT_INTERVAL_SECONDS - 1)
    runs.heartbeat(run_context, stage="sweep:premiere:p1")

    assert _run_row(engine, run_context.run_pk)["heartbeat_at"] == first_beat


def test_a_beat_with_no_stage_rewrites_the_last_stage(
    run_context: Any, engine: Engine, clock: Any
) -> None:
    """A stage-less beat never clears the stage: the row always says what the run is doing."""
    runs.heartbeat(run_context, stage="sweep:premiere:p1")
    first_beat = _run_row(engine, run_context.run_pk)["heartbeat_at"]

    clock.advance(runs.HEARTBEAT_INTERVAL_SECONDS)
    runs.heartbeat(run_context)

    row = _run_row(engine, run_context.run_pk)
    assert row["heartbeat_at"] == first_beat + runs.HEARTBEAT_INTERVAL_SECONDS
    assert row["stage"] == "sweep:premiere:p1"


# --- dry_context: no run row, no writes, no heartbeat (§11.4) --------------------------------


def test_a_dry_context_writes_nothing_and_never_heartbeats(
    engine: Engine, db_path: Path, clock: Any, settings: Settings
) -> None:
    """The dry path's context carries ``DRY_RUN_PK`` and is not persisted, so ``heartbeat``
    returns immediately -- proven against a ``mode=ro`` engine, on which any write raises."""
    read_only = engine_for(db_path, read_only=True)
    try:
        ctx = runs.dry_context(read_only, kind="run", trigger="cli", clock=clock, settings=settings)
        assert ctx.run_pk == runs.DRY_RUN_PK
        assert ctx.persisted is False
        assert ctx.dry_run is True
        assert ctx.workspace_pk > 0
        assert ctx.baseline_counts == {}
        runs.heartbeat(ctx, stage="sweep:premiere:p1")
    finally:
        read_only.dispose()

    with engine.connect() as conn:
        assert repo.table_counts(conn, ("runs",)) == {"runs": 0}


# --- Counters, sync_budget and the wall-clock ceiling (§13.1, §6.6, §12.3) -------------------


def test_counters_keys_are_the_closed_set_and_round_trip_through_the_row(
    run_context: Any, engine: Engine
) -> None:
    """§13.1: ``as_dict`` is built from ``KEYS``, and ``runs.counters_json`` round-trips."""
    assert set(runs.Counters().as_dict()) == set(runs.Counters.KEYS)

    run_context.counters.posts_new = 7
    run_context.counters.rejects = 2
    run_context.warn("budget_exhausted", "stopped at the configured limit")
    runs.finish_run_from(run_context, status=RunStatus.PARTIAL, violations_json=None, error=None)

    row = _run_row(engine, run_context.run_pk)
    assert runs.Counters.from_json(row["counters_json"]) == run_context.counters
    assert row["status"] == "partial"


def test_warn_records_the_warning_and_bumps_the_counter(run_context: Any) -> None:
    """One warning is the whole difference between ``ok`` and ``partial`` (§3.1)."""
    run_context.warn("wall_clock_ceiling", "3 h reached with 2 sources left")

    assert run_context.warnings == [
        runs.RunWarning(name="wall_clock_ceiling", detail="3 h reached with 2 sources left")
    ]
    assert run_context.counters.warnings == 1


def test_sync_budget_follows_the_gateway_and_never_decreases(run_context: Any) -> None:
    """§6.6: ``used`` is ``max(used, gateway.requests_made)``, so it is monotone under both
    regimes -- the fake's counter, and PRAW's Session hook, which agree by construction."""
    gateway = FakeRedditGateway()
    gateway.add_subreddit("premiere")
    gateway.about("premiere")

    assert runs.sync_budget(run_context, gateway) == 1
    assert run_context.budget.used == 1

    run_context.budget.used = 5
    assert runs.sync_budget(run_context, gateway) == 5


def test_the_wall_clock_ceiling_counts_down_and_then_expires(
    run_context: Any, clock: Any, settings: Settings
) -> None:
    """§12.3: ``deadline_at`` is ``started_at`` plus the configured ceiling, and the remaining
    seconds -- what ``plan_rate_limit_wait`` is handed -- never go negative."""
    ceiling = settings.static.run.wall_clock_ceiling_hours * 3600
    assert run_context.deadline_at == run_context.started_at + ceiling
    assert run_context.remaining_ceiling_seconds == float(ceiling)
    assert run_context.over_ceiling is False

    clock.advance(ceiling)

    assert run_context.remaining_ceiling_seconds == 0.0
    assert run_context.over_ceiling is True
