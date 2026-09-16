"""The run's ordered body: stale sweep, run row, sweep, counters, invariants, finish.

`cli` owns the preconditions (design-round5 §11.3) and this module owns everything after
them, in **one** written order (round5-findings.json, ``P1-collect-ordering-unknown-enum``):

    sweep_stale (T1) -> start_run (T2 + T3) -> sweep_all
      -> materialize every counter the invariants read
      -> ctx.terminal_status -> InvariantContext -> check_all (T7)
      -> resolve_status -> finish_run_from (T8)
      -> checkpoint_truncate outside any transaction (DB-17)
      -> the run-level notification (§11.9)

Two orderings inside that list are load-bearing and neither is a detail:

* **Every counter is final before :class:`~threaddigest.services.invariants.InvariantContext`
  is built.** ``unknown_enum_values`` is ``len(ctx.unknown_enum_keys)`` and ``api_requests``
  is the gateway's own counter (§6.6, §13.1); materializing either *after* the invariant pass
  would make ``unknown_enum_values_are_counted`` compare the database against ``0`` on every
  run, so one unknown ``post_hint`` in the demo fixture would turn every healthy run amber
  and the GT-01 planter would pass for the wrong reason.
  ``tests/services/test_invariants.py::test_unknown_enum_counter_is_final_before_the_invariants_run``
  is the closing test.
* **``checkpoint_truncate`` runs after T8 commits and outside every transaction** (DB-17):
  inside or during one it returns ``busy == 1`` and truncates nothing.
  ``tests/e2e/test_run_happy_path.py::test_wal_is_truncated_at_end_of_run`` is its call-site
  test.

``KeyboardInterrupt`` is caught here and **only** here (§8): the handler wraps
:func:`~threaddigest.services.sweep.sweep_all` and nothing else, so a Ctrl-C during the
invariant pass or the finish is not converted into a ``cancelled`` row that hides a
half-closed run. A dry run takes the same path with none of the writes (§11.4): no stale
sweep, no run row, no invariants, no finish, no checkpoint and no notification -- and its
status still comes from the same warning ledger, so a dry run whose source 403s exits 3
(round5-findings.json, ``P1-dry-run-swallows-failures``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Final

from sqlalchemy import Engine

from threaddigest.core.budget import Budget
from threaddigest.core.models import NORMALIZER_VERSION
from threaddigest.core.retry import RunStatus, exit_code
from threaddigest.db.engine import checkpoint_truncate
from threaddigest.ports import Clock, Notifier, RedditGateway
from threaddigest.services import invariants, runs, sweep
from threaddigest.services.invariants import InvariantContext, Violation
from threaddigest.services.runs import Counters, RunContext
from threaddigest.services.sweep import SweepResult
from threaddigest.settings import Settings

__all__ = ["CANCELLED_ERROR", "NOTIFYING_STATUSES", "CollectOutcome", "collect"]

#: Final statuses that earn a run-level notification (§11.9). ``partial`` is deliberately
#: absent: an amber run is seen through the digest line, and alerting on it would train the
#: operator to ignore the alert. ``crashed`` is notified by the run that *finds* it, at
#: stale-sweep time, which is why it is not in this set either.
NOTIFYING_STATUSES: Final[frozenset[RunStatus]] = frozenset(
    {RunStatus.FAILED, RunStatus.RATE_LIMITED, RunStatus.NETWORK}
)

#: ``runs.error`` on a row this process closed because the operator pressed Ctrl-C.
CANCELLED_ERROR: Final = "interrupted: the sweep was stopped by a KeyboardInterrupt"


@dataclass(frozen=True, slots=True)
class CollectOutcome:
    """What one ``run`` did, as ``cli`` reports it (§3.3).

    ``run_pk`` is ``None`` in a dry run (there is no row) and ``sweep`` is ``None`` when the
    sweep never returned -- today only the ``KeyboardInterrupt`` path.
    """

    run_pk: int | None
    status: RunStatus
    exit_code: int
    counters: Counters
    violations: tuple[Violation, ...]
    sweep: SweepResult | None


def collect(
    engine: Engine,
    *,
    settings: Settings,
    clock: Clock,
    gateway: RedditGateway,
    notifier: Notifier,
    trigger: str = "cli",
    dry_run: bool = False,
    budget: Budget | None = None,
    options_json: str | None = None,
) -> CollectOutcome:
    """Run one collection over every enabled source and return what it did.

    ``budget`` overrides the configured one (``--budget N``, §11.5); ``None`` keeps the
    budget :func:`~threaddigest.services.runs.start_run` built from the settings.
    """
    if dry_run:
        return _collect_dry(
            engine,
            settings=settings,
            clock=clock,
            gateway=gateway,
            notifier=notifier,
            trigger=trigger,
            budget=budget,
        )
    return _collect_persisted(
        engine,
        settings=settings,
        clock=clock,
        gateway=gateway,
        notifier=notifier,
        trigger=trigger,
        budget=budget,
        options_json=options_json,
    )


def _collect_persisted(
    engine: Engine,
    *,
    settings: Settings,
    clock: Clock,
    gateway: RedditGateway,
    notifier: Notifier,
    trigger: str,
    budget: Budget | None,
    options_json: str | None,
) -> CollectOutcome:
    """The ordered body of a real run; every step is one row of §7's table."""
    _sweep_stale(engine, settings=settings, clock=clock, notifier=notifier)
    ctx = runs.start_run(
        engine,
        kind="run",
        trigger=trigger,
        clock=clock,
        settings=settings,
        options_json=options_json,
    )
    if budget is not None:
        ctx.budget = budget
    try:
        result = sweep.sweep_all(ctx, gateway=gateway, notifier=notifier)
    except KeyboardInterrupt:
        # The ONE catch site (§8). The row is closed `cancelled` with the counters gathered
        # so far and a NULL `violations_json` -- the invariants did not run, which is not the
        # same as running and finding nothing.
        return _finish_cancelled(ctx, gateway)
    _materialize_counters(ctx, gateway)
    ctx.terminal_status = result.terminal_status
    violations = _run_invariants(ctx)
    violations_json = invariants.to_json(violations)
    status = runs.resolve_status(result.terminal_status, violations, ctx.warnings)
    runs.finish_run_from(
        ctx, status=status, violations_json=violations_json, error=result.terminal_error
    )
    if not _checkpoint_or_warn(ctx):  # DB-17 after T8; KI-013: re-close the row with the warning
        status = runs.resolve_status(result.terminal_status, violations, ctx.warnings)
        runs.finish_run_from(
            ctx, status=status, violations_json=violations_json, error=result.terminal_error
        )
    _notify_outcome(
        notifier,
        run_pk=ctx.run_pk,
        status=status,
        error=result.terminal_error,
        violations=violations,
    )
    return CollectOutcome(
        run_pk=ctx.run_pk,
        status=status,
        exit_code=result.exit_code_override or exit_code(status),
        counters=ctx.counters,
        violations=tuple(violations),
        sweep=result,
    )


def _collect_dry(
    engine: Engine,
    *,
    settings: Settings,
    clock: Clock,
    gateway: RedditGateway,
    notifier: Notifier,
    trigger: str,
    budget: Budget | None,
) -> CollectOutcome:
    """The same order with every write removed (§11.4).

    The status comes from the same warning ledger a real run uses, so a source that 403s
    during a dry run still ends the command ``partial``/exit 3 rather than a silent ``ok``
    (round5-findings.json, ``P1-dry-run-swallows-failures``). ``posts_new`` and
    ``posts_updated`` are structurally 0 here, because ``write_page`` never runs and the
    counters are folded from its result -- ``cli``'s summary labels them.
    """
    ctx = runs.dry_context(engine, kind="run", trigger=trigger, clock=clock, settings=settings)
    if budget is not None:
        ctx.budget = budget
    result = sweep.sweep_all(ctx, gateway=gateway, notifier=notifier)
    _materialize_counters(ctx, gateway)
    status = runs.resolve_status(result.terminal_status, (), ctx.warnings)
    return CollectOutcome(
        run_pk=None,
        status=status,
        exit_code=result.exit_code_override or exit_code(status),
        counters=ctx.counters,
        violations=(),
        sweep=result,
    )


def _sweep_stale(
    engine: Engine, *, settings: Settings, clock: Clock, notifier: Notifier
) -> runs.StaleSweep:
    """T1, before the run row exists, with §11.9's ``crashed`` notification.

    A ``crashed`` run is announced by the run that *finds* it: the process that died could
    not announce anything, and the discovery is the first moment anyone can.
    """
    now = clock.now()
    with engine.begin() as conn:
        swept = runs.sweep_stale(
            conn,
            now=now,
            this_pid=os.getpid(),
            this_run_pk=None,
            stale_after_seconds=settings.static.run.stale_after_minutes * 60,
        )
    for run_pk in swept.crashed:
        notifier.notify("error", f"run {run_pk} was found crashed and has been closed")
    return swept


def _materialize_counters(ctx: RunContext, gateway: RedditGateway) -> None:
    """Make every counter the invariants read final (§13.1).

    Called **before** the ``InvariantContext`` is built, and again on the cancelled path so
    the row a Ctrl-C closes still reports what the run really spent.
    """
    ctx.counters.unknown_enum_values = len(ctx.unknown_enum_keys)
    ctx.counters.api_requests = runs.sync_budget(ctx, gateway)


def _run_invariants(ctx: RunContext) -> list[Violation]:
    """T7: every invariant, on one read-only connection, in ``INVARIANTS`` order."""
    with ctx.engine.connect() as conn:
        return invariants.check_all(
            InvariantContext(
                conn=conn,
                run_pk=ctx.run_pk,
                run_started_at=ctx.started_at,
                now=ctx.clock.now(),
                counters=ctx.counters,
                baseline_counts=ctx.baseline_counts,
                normalizer_version=NORMALIZER_VERSION,
                settings=ctx.settings,
                terminal_status=ctx.terminal_status,
            )
        )


#: KI-013: ``wal_checkpoint(TRUNCATE)`` cannot reset the log while a reader holds a snapshot,
#: and the web UI is a reader by design. Retry a few times, then record it on the run.
CHECKPOINT_ATTEMPTS = 3
CHECKPOINT_RETRY_SECONDS = 0.5


def _checkpoint_or_warn(ctx: RunContext) -> bool:
    """Truncate the write-ahead log after T8 (DB-17); when a reader holds it, retry briefly and
    then warn (KI-013), because the pages written this run, a scrub's included, stay in the log
    until a later checkpoint and ``secure_delete`` does not cover the log. True when truncated.
    """
    for attempt in range(CHECKPOINT_ATTEMPTS):
        busy, _log_frames, _checkpointed = checkpoint_truncate(ctx.engine)
        if not busy:
            return True
        if attempt + 1 < CHECKPOINT_ATTEMPTS:
            ctx.clock.sleep(CHECKPOINT_RETRY_SECONDS)
    ctx.warn(
        "wal_checkpoint_busy",
        "a reader held the write-ahead log at the end of the run; the pages written this run "
        "stay in it until a later checkpoint",
    )
    return False


def _finish_cancelled(ctx: RunContext, gateway: RedditGateway) -> CollectOutcome:
    """Close the row ``cancelled`` and report exit 130 (§9).

    130 is produced here rather than inherited from click: an uncaught ``KeyboardInterrupt``
    would also exit 130, and would leave the run row ``running``.
    """
    _materialize_counters(ctx, gateway)
    runs.finish_run_from(
        ctx, status=RunStatus.CANCELLED, violations_json=None, error=CANCELLED_ERROR
    )
    if not _checkpoint_or_warn(ctx):  # KI-013: the warning rides in counters_json
        runs.finish_run_from(
            ctx, status=RunStatus.CANCELLED, violations_json=None, error=CANCELLED_ERROR
        )
    return CollectOutcome(
        run_pk=ctx.run_pk,
        status=RunStatus.CANCELLED,
        exit_code=exit_code(RunStatus.CANCELLED),
        counters=ctx.counters,
        violations=(),
        sweep=None,
    )


def _notify_outcome(
    notifier: Notifier,
    *,
    run_pk: int,
    status: RunStatus,
    error: str | None,
    violations: list[Violation],
) -> None:
    """§11.9's table: the message names the run, the status and the first thing that went
    wrong -- ``runs.error``'s first line, or the first violation when ``error`` is NULL
    (which is what a run that failed purely on its invariants looks like)."""
    if status not in NOTIFYING_STATUSES:
        return
    if error:
        detail = error.splitlines()[0]
    elif violations:
        detail = f"{violations[0].invariant}: {violations[0].detail}"
    else:
        detail = "no further detail recorded"
    notifier.notify("error", f"run {run_pk} ended {status.value}: {detail}")
