"""The run lifecycle: the stale sweep, the run row, the stage-aware heartbeat, the budget
sync and the status resolution every command finishes through.

Layering and cycles (design-round5 §12.5, §14.1): this module imports ``db``, ``ports``,
``core`` and ``settings``, and **never** ``services.invariants`` -- which is why
:func:`finish_run_from` takes ``violations_json`` already serialized and
:func:`resolve_status` reads violations structurally, through :class:`SeverityCarrier`,
instead of importing ``Severity``.

:class:`RunContext` is the one mutable value type in the design: counters and warnings
accumulate over a run. Everything else here is frozen.

Since revision 0005 the warnings reach the row as well as the counter: the heartbeat and
the close both carry ``warnings_json``, so what the run had named by its last beat survives
a process that never reaches T8. The settings the run resolved are written once, in the
insert's own transaction. Both are guarded by :attr:`RunContext.schema_at_head`, because
``db upgrade`` opens its run row on a file it has not migrated yet.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import ClassVar, Final, Protocol

from sqlalchemy import Connection, Engine

from threaddigest import __version__
from threaddigest.core.budget import Budget
from threaddigest.core.retry import (
    ExitCode,
    Outcome,
    RetryPolicy,
    RunStatus,
    classify,
    plan_rate_limit_wait,
)
from threaddigest.db import migrate, repo
from threaddigest.ports import Clock, GatewayError, HtmlBlocked, RateLimited, RedditGateway
from threaddigest.services import lock
from threaddigest.settings import Settings, settings_fingerprint, settings_json

__all__ = [
    "DELTA_COUNTER_FOR_TABLE",
    "DRY_RUN_PK",
    "HEARTBEAT_INTERVAL_SECONDS",
    "STALE_QUEUED_SECONDS",
    "TRACKED_TABLES",
    "Counters",
    "RunContext",
    "RunTerminalError",
    "RunWarning",
    "SeverityCarrier",
    "StaleSweep",
    "dry_context",
    "fetch_with_ladder",
    "finish_run_from",
    "heartbeat",
    "resolve_status",
    "start_run",
    "sweep_stale",
    "sync_budget",
    "warnings_to_json",
]

#: How often a repeated stage may touch the run row. A CHANGED stage always writes (§12.4).
HEARTBEAT_INTERVAL_SECONDS: Final = 5
#: Grace before a pid-less ``queued`` row counts as an orphan of a failed spawn (§12.2).
STALE_QUEUED_SECONDS: Final = 120
#: ``RunContext.run_pk`` when no run row exists, i.e. a dry run (§11.4).
DRY_RUN_PK: Final = -1

#: ``runs.error`` on a row the stale sweep condemns. One sentence per outcome, because
#: ``repo.mark_runs`` stamps one message across every row it closes.
CRASHED_ERROR: Final = (
    "the process ended without finishing this run; stamped crashed by a later run's stale sweep"
)
ORPHAN_QUEUED_ERROR: Final = (
    "queued but never claimed by a process within the grace period; stamped failed by a later run"
)

#: The severity values ``services.invariants.Severity`` carries. Spelled here as strings so
#: this module does not import ``services.invariants`` (§12.5); step 5's ``Severity`` is a
#: ``StrEnum``, so its members compare equal to these, and a step-5 test pins the vocabulary.
SEVERITY_FAILURE: Final = "failure"
SEVERITY_WARNING: Final = "warning"


@dataclass(slots=True)
class Counters:
    """The closed set of run counters. Serialized verbatim to ``runs.counters_json``.

    The tree stage's five (``comments_updated``, ``trees_fetched``, ``trees_complete``,
    ``trees_skipped_empty``, ``more_stubs``) are folded from a committed tree's own result,
    as ``comments_new`` is: ``comments_new`` is tied to the ``comments`` table's delta by
    :data:`DELTA_COUNTER_FOR_TABLE`, which is a FAILURE invariant, so a counter raised before
    its transaction commits would report the collector as broken on what is really lock
    contention (P0-2).
    """

    posts_new: int = 0
    posts_updated: int = 0
    comments_new: int = 0
    comments_updated: int = 0
    trees_fetched: int = 0
    trees_complete: int = 0
    trees_skipped_empty: int = 0
    more_stubs: int = 0
    rejects: int = 0
    unknown_enum_values: int = 0
    scrubs_pending: int = 0
    pages: int = 0
    api_requests: int = 0
    warnings: int = 0

    #: The authoritative key list. A test asserts ``set(as_dict()) == set(KEYS)``.
    KEYS: ClassVar[tuple[str, ...]] = (
        "posts_new",
        "posts_updated",
        "comments_new",
        "comments_updated",
        "trees_fetched",
        "trees_complete",
        "trees_skipped_empty",
        "more_stubs",
        "rejects",
        "unknown_enum_values",
        "scrubs_pending",
        "pages",
        "api_requests",
        "warnings",
    )

    def as_dict(self) -> dict[str, int]:
        """Every counter by name, built from :data:`KEYS` so the two cannot drift."""
        return {key: int(getattr(self, key)) for key in self.KEYS}

    def to_json(self) -> str:
        """``runs.counters_json``: stable key order, no incidental whitespace."""
        return json.dumps(self.as_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_json(cls, payload: str) -> Counters:
        """Read a ``counters_json`` payload back; keys outside :data:`KEYS` are ignored."""
        loaded = json.loads(payload)
        return cls(**{key: int(loaded[key]) for key in cls.KEYS if key in loaded})


#: Which counter each tracked table's row-count delta must equal (DB-54). Declared as data so
#: the invariant iterates it instead of hard-coding three comparisons.
DELTA_COUNTER_FOR_TABLE: Final[Mapping[str, str]] = MappingProxyType(
    {
        "posts": "posts_new",
        "comments": "comments_new",
        "raw_rejects": "rejects",
    }
)

#: Tables whose counts are snapshotted at run start. A superset of
#: :data:`DELTA_COUNTER_FOR_TABLE`: the extra tables are asserted non-decreasing only
#: (DB-55 lands at M1c).
TRACKED_TABLES: Final[tuple[str, ...]] = (
    "posts",
    "comments",
    "raw_rejects",
    "post_sources",
    "item_snapshots",
    "authors",
    "comment_more",
    "post_themes",
)


@dataclass(frozen=True, slots=True)
class RunWarning:
    """One recorded warning. Any warning makes the run ``partial``; ``ok`` means zero."""

    name: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        """The two keys ``runs.warnings_json`` carries, in the order the column names them."""
        return {"name": self.name, "detail": self.detail}


def warnings_to_json(warnings: Sequence[RunWarning]) -> str:
    """``runs.warnings_json``: always an array, ``"[]"`` when empty.

    ``"[]"`` is **not** the same as NULL, exactly as for ``violations_json``: ``[]`` means
    this run recorded its warnings and had none, NULL that it recorded nothing at all -- a
    row written before revision 0005, or one a stale sweep stamped on another process's
    behalf. The readers say "not recorded" for NULL rather than "no warning".
    """
    return json.dumps([warning.as_dict() for warning in warnings], separators=(",", ":"))


class RunTerminalError(Exception):
    """The whole run must end now with ``status`` (design-round5 §3.4).

    Raised by ``sweep.fetch_page`` and ``sweep.preflight``; caught in exactly one place,
    ``sweep.sweep_all`` (§6.8), which turns it into a ``SweepResult`` rather than letting it
    escape -- work already committed by earlier subreddits stays committed.

    Named with the ``Error`` suffix because ruff's N818 requires it and this tranche's
    suppression budget (one, spent on ``check_all``) is not spent on a name. It lives here
    rather than in ``services/sweep.py`` because ``collect`` and ``cli`` read ``status`` and
    ``exit_code`` from it without importing the sweep.
    """

    def __init__(self, status: RunStatus, *, detail: str, exit_code: int | None = None) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail
        #: None means ``core.retry.exit_code(status)`` applies; 78 is the one override (§9).
        self.exit_code = exit_code


@dataclass(frozen=True, slots=True)
class StaleSweep:
    """What :func:`sweep_stale` changed, so ``collect`` can log it and tests can assert it."""

    crashed: tuple[int, ...]
    failed_queued: tuple[int, ...]

    @property
    def total(self) -> int:
        return len(self.crashed) + len(self.failed_queued)


class SeverityCarrier(Protocol):
    """Structural stand-in for ``services.invariants.Violation`` (§12.5: no import cycle)."""

    @property
    def severity(self) -> str: ...


@dataclass(slots=True)
class RunContext:
    """Everything a service needs about the run in flight. Built by :func:`start_run` or
    :func:`dry_context`.

    One engine, not two (§3.2): read-write in a normal run, ``mode=ro`` for the whole process
    in a dry run. The gateway and the notifier are deliberately **not** here -- they are
    explicit parameters, so a function's signature says whether it can do I/O.
    """

    run_pk: int
    kind: str
    trigger: str
    workspace_pk: int
    clock: Clock
    settings: Settings
    engine: Engine
    budget: Budget
    counters: Counters
    warnings: list[RunWarning] = field(default_factory=list)
    #: ``"<reddit_id>|<field>=<value>"`` for every unknown enum occurrence observed this run.
    #: A set, so overlapping pages (SW-03) cannot count the same occurrence twice (§13.1).
    unknown_enum_keys: set[str] = field(default_factory=set)
    baseline_counts: Mapping[str, int] = field(default_factory=dict)
    started_at: int = 0
    deadline_at: int = 0
    dry_run: bool = False
    #: The database was already at head when the row was inserted, so every head-model
    #: column exists on it. False for ``db upgrade``, the one command that legitimately runs
    #: against an older file: its heartbeats must name no column that file may not have.
    schema_at_head: bool = False
    terminal_status: RunStatus | None = None
    _last_heartbeat_at: int = 0
    #: §12.4: a CHANGED stage always writes, throttle or not.
    _last_stage: str | None = None

    @property
    def persisted(self) -> bool:
        """True when a ``runs`` row backs this context; False in a dry run (§11.4)."""
        return self.run_pk > 0

    @property
    def remaining_ceiling_seconds(self) -> float:
        """Seconds left before the wall-clock ceiling; never negative (§12.3)."""
        return max(float(self.deadline_at - self.clock.now()), 0.0)

    @property
    def over_ceiling(self) -> bool:
        return self.remaining_ceiling_seconds <= 0.0

    def warn(self, name: str, detail: str) -> None:
        """Record a warning. One warning is the difference between ``ok`` and ``partial``.

        The list and the counter move together and are two spellings of one fact: the
        counter is what ``counters_json`` carries and the list is what ``warnings_json``
        carries, and a test asserts the equality on a real run, because a page that says
        "3 warnings, 1 named" is only honest while the two agree.
        """
        self.warnings.append(RunWarning(name=name, detail=detail))
        self.counters.warnings += 1

    def warnings_json(self) -> str:
        """The warnings recorded so far, for ``runs.warnings_json`` (revision 0005)."""
        return warnings_to_json(self.warnings)


def _budget_for(settings: Settings) -> Budget:
    """The configured per-run budget, clamped exactly as §11.5 clamps ``--budget``.

    ``reserve`` is clamped against the resolved limit because ``Budget`` refuses a reserve
    larger than its limit. ``cli``/``collect`` replaces ``ctx.budget`` when ``--budget N`` was
    given, which is legal because :class:`RunContext` is the design's one mutable value type.
    """
    static = settings.static.budget
    limit = min(max(static.per_run_requests, 0), static.hard_cap)
    reserve = min(static.reserve, max(limit - 1, 0))
    return Budget(limit=limit, reserve=reserve, hard_cap=static.hard_cap)


def _last_seen(row: repo.RunRow) -> int:
    """``coalesce(heartbeat_at, started_at, created_at)`` (§12.2 clause 3), exactly.

    Written as explicit ``is None`` tests rather than ``or``: a run that inserted its row and
    died before its first heartbeat has ``heartbeat_at IS NULL``, and a truthiness chain would
    also skip a genuine epoch-0 stamp.
    """
    if row.heartbeat_at is not None:
        return row.heartbeat_at
    if row.started_at is not None:
        return row.started_at
    return row.created_at


def _is_crashed(row: repo.RunRow, *, now: int, this_pid: int, stale_after_seconds: int) -> bool:
    """§12.2's four clauses for a ``running`` row that is really over.

    Clause 4 (the row carries **our own** pid) is true by construction: this process holds the
    exclusive collector flock and every mutating command takes it before ``start_run``, so a
    ``running`` row with our pid belongs to a run that has already ended. It is what makes the
    in-process e2e suite -- and a hard kill followed by an immediate rerun -- recoverable.
    """
    if row.pid is None:
        return True
    if not lock.pid_alive(row.pid):
        return True
    if row.pid == this_pid:
        return True
    return _last_seen(row) < now - stale_after_seconds


def sweep_stale(
    conn: Connection,
    *,
    now: int,
    this_pid: int,
    this_run_pk: int | None,
    stale_after_seconds: int,
    queued_grace_seconds: int = STALE_QUEUED_SECONDS,
) -> StaleSweep:
    """Close the rows a previous process left behind (T1, §12.2).

    Runs **after** this process took the collector flock and **before** :func:`start_run`, so
    ``this_run_pk`` is ``None`` there; the parameter exists so the same function is callable
    from a read-only mirror without ever skipping a row by accident.

    ``queued_grace_seconds`` -- not ``stale_after_seconds`` -- bounds the ``queued`` half:
    ``repo.stale_candidates`` returns every ``running`` row unfiltered on purpose, because
    three of the four clauses above are decided in Python against a live process table.
    """
    running, orphan_queued = repo.stale_candidates(
        conn, now=now, stale_after_seconds=queued_grace_seconds
    )
    crashed = [
        row.pk
        for row in running
        if row.pk != this_run_pk
        and _is_crashed(row, now=now, this_pid=this_pid, stale_after_seconds=stale_after_seconds)
    ]
    repo.mark_runs(conn, pks=crashed, status="crashed", finished_at=now, error=CRASHED_ERROR)
    repo.mark_runs(
        conn,
        pks=orphan_queued,
        status="failed",
        finished_at=now,
        error=ORPHAN_QUEUED_ERROR,
    )
    return StaleSweep(crashed=tuple(crashed), failed_queued=tuple(orphan_queued))


def start_run(
    engine: Engine,
    *,
    kind: str,
    trigger: str,
    clock: Clock,
    settings: Settings,
    options_json: str | None = None,
) -> RunContext:
    """Insert this run's row (T2), then read the DB-54 baselines outside it (T3).

    The row is committed on its own **before** any fetch, so a crash always leaves a
    ``running`` row for the next run to stamp ``crashed`` (§7). ``praw_version`` stays NULL in
    this tranche: no PRAW adapter exists yet, and recording a version for a library no request
    went through would be a false record. ``stage`` is written by the first
    :func:`heartbeat`, which is also how ``db upgrade`` reaches its ``upgrade:backup`` stage
    (§10.3 step 3) -- §12.5's signature takes no stage.
    """
    now = clock.now()
    run = repo.RunInsert(
        kind=kind,
        trigger=trigger,
        status="running",
        created_at=now,
        started_at=now,
        pid=os.getpid(),
        stage=None,
        options_json=options_json,
        app_version=__version__,
        praw_version=None,
        schema_rev=migrate.current_revision(engine),
        settings_fingerprint=settings_fingerprint(settings),
        log_path=None,
    )
    # The settings themselves, not only their hash (revision 0005): the digest can then name
    # the keys that changed since the run before instead of reporting that something did.
    # Both come from ``settings.settings_json``'s one serialization, so the row's
    # fingerprint is the SHA-256 of the row's own settings by construction. It is a second
    # statement inside the insert's transaction, not two more columns on ``RunInsert``,
    # because ``db upgrade`` inserts its run row against a file it has not migrated yet and
    # the insert may name no column newer than revision 0001 (``repo.insert_run``).
    schema_at_head = migrate.is_at_head(engine)
    with engine.begin() as conn:
        run_pk = repo.insert_run(conn, run)
        if schema_at_head:
            repo.record_run_settings(conn, run_pk=run_pk, settings_json=settings_json(settings))
    with engine.connect() as conn:
        workspace_pk = repo.default_workspace_pk(conn)
        baseline_counts = repo.table_counts(conn, TRACKED_TABLES)
    return RunContext(
        run_pk=run_pk,
        kind=kind,
        trigger=trigger,
        workspace_pk=workspace_pk,
        clock=clock,
        settings=settings,
        engine=engine,
        budget=_budget_for(settings),
        counters=Counters(),
        baseline_counts=baseline_counts,
        started_at=now,
        deadline_at=now + settings.static.run.wall_clock_ceiling_hours * 3600,
        schema_at_head=schema_at_head,
    )


def dry_context(
    engine: Engine, *, kind: str, trigger: str, clock: Clock, settings: Settings
) -> RunContext:
    """A context for ``run --dry-run``: no run row, no baselines, no writes at all (§11.4).

    ``engine`` is the process's one ``mode=ro`` engine, so a bug that reached a write raises
    ``OperationalError`` instead of succeeding. Only the workspace is read, because the sweep
    needs to know which sources to list.
    """
    now = clock.now()
    with engine.connect() as conn:
        workspace_pk = repo.default_workspace_pk(conn)
    return RunContext(
        run_pk=DRY_RUN_PK,
        kind=kind,
        trigger=trigger,
        workspace_pk=workspace_pk,
        clock=clock,
        settings=settings,
        engine=engine,
        budget=_budget_for(settings),
        counters=Counters(),
        started_at=now,
        deadline_at=now + settings.static.run.wall_clock_ceiling_hours * 3600,
        dry_run=True,
    )


def heartbeat(ctx: RunContext, *, stage: str | None = None) -> None:
    """Touch the run row (T4). A **changed** stage always writes; the
    :data:`HEARTBEAT_INTERVAL_SECONDS` throttle applies only to a repeated one (§12.4).

    A beat carrying ``stage=None`` never clears the stage: it re-writes the last one, so the
    row always says what the run is doing. ``doctor``'s ``lock_not_stale`` clause D2 depends
    on this: a ``rate_wait:Ns`` stage written seconds after the previous beat must reach the
    row, or a healthy 300 s pause reads as a hang.
    """
    if not ctx.persisted:
        return
    now = ctx.clock.now()
    stage_changed = stage is not None and stage != ctx._last_stage
    if not stage_changed and now - ctx._last_heartbeat_at < HEARTBEAT_INTERVAL_SECONDS:
        return
    with ctx.engine.begin() as conn:
        # The beat also flushes the warnings recorded so far (revision 0005): a run the
        # machine loses between two beats leaves behind the ones it had named by the last
        # one, rather than a counter in `counters_json` with nothing behind it. Below head
        # it flushes nothing, because `db upgrade` beats `upgrade:backup` onto its row
        # before it migrates the file, and `warnings_json` may not exist there yet.
        repo.touch_run(
            conn,
            run_pk=ctx.run_pk,
            heartbeat_at=now,
            stage=stage or ctx._last_stage,
            warnings_json=ctx.warnings_json() if ctx.schema_at_head else None,
        )
    ctx._last_heartbeat_at = now
    if stage is not None:
        ctx._last_stage = stage


def fetch_with_ladder[T](
    ctx: RunContext,
    fetch: Callable[[], T],
    *,
    gateway: RedditGateway,
    label: str,
    policy: RetryPolicy,
) -> T:
    """Call ``fetch`` with the transient ladder, the 429 rule and the budget sync around it.

    One unit of work -- a listing page, a comment tree -- retried on ``policy``'s ladder and
    given up on when the ladder is walked. ``label`` names the unit in the heartbeat stage
    (``retry:premiere:30s``, ``retry:tree:1abc2d:30s``), so a pause is never mistaken for a
    hang (D-7).

    Four outcomes leave through :class:`RunTerminalError`, i.e. end the whole run: a second
    429 on the same unit, a 429 whose window does not fit inside the wall-clock ceiling, an
    ``AuthFailed`` (exit 78, §9) and an ``HtmlBlocked``; a ``network_down`` that exhausts the
    ladder is the fifth. Everything else -- a per-source or per-post fatal, and a transient
    that exhausts the ladder -- is re-raised as itself for the caller to scope (§6.2 note 7).

    The one-retry rule for a 429 is deliberate: a second 429 on the same unit means Reddit is
    not honouring the window, and the run ends ``rate_limited`` (exit 4) rather than burning
    the wall-clock ceiling. The abort comes **first**, before the wait, so a decision already
    made does not cost up to 300 s of the ceiling (§8's error table, panel P2-1).

    It lives here rather than in ``services/sweep.py`` because the sweep and the tree stage
    are two callers of one rule, and a second copy of the ladder is a second rule: this is
    the function ``sweep.fetch_page`` was, lifted the moment M1b gave it its second use
    (N-20's two concrete uses).
    """
    attempt = 1
    rate_limited_once_already = False
    while True:
        try:
            return fetch()
        except RateLimited as exc:
            if rate_limited_once_already:
                raise RunTerminalError(RunStatus.RATE_LIMITED, detail=str(exc)) from exc
            wait = plan_rate_limit_wait(exc.retry_after, ctx.remaining_ceiling_seconds)
            if not wait.should_wait:
                raise RunTerminalError(RunStatus.RATE_LIMITED, detail=str(exc)) from exc
            heartbeat(ctx, stage=wait.stage)  # written BEFORE the sleep (§12.4)
            ctx.clock.sleep(wait.seconds)
            rate_limited_once_already = True
        except HtmlBlocked as exc:
            raise RunTerminalError(RunStatus.FAILED, detail=f"html 403: {exc}") from exc
        except GatewayError as exc:
            outcome = classify(exc)
            if outcome is Outcome.AUTH:
                raise RunTerminalError(
                    RunStatus.FAILED, detail=f"auth: {exc}", exit_code=ExitCode.CONFIG
                ) from exc
            if outcome not in {Outcome.TRANSIENT, Outcome.NETWORK_DOWN}:
                raise  # fatal for this unit of work; the caller scopes it
            delay = policy.next_delay(attempt)
            if delay is None:
                if outcome is Outcome.NETWORK_DOWN:
                    raise RunTerminalError(RunStatus.NETWORK, detail=str(exc)) from exc
                raise  # transient give-up: this unit of work only
            heartbeat(ctx, stage=f"retry:{label}:{int(delay)}s")
            ctx.clock.sleep(delay)
            attempt += 1
        finally:
            sync_budget(ctx, gateway)  # §6.6: a give-up, a 429, a 403 and a crash all pay


def sync_budget(ctx: RunContext, gateway: RedditGateway) -> int:
    """Re-sync the run's budget to the gateway's own request counter; never decreases (§6.6).

    ``max`` is what makes this correct under both regimes: with PRAW the Session hook's
    ``record`` calls and ``requests_made`` count the same round-trips, so the two agree and
    this is a no-op; the fake has no such hook, so ``used`` is a function of the counter.
    """
    ctx.budget.used = max(ctx.budget.used, gateway.requests_made)
    return ctx.budget.used


def resolve_status(
    terminal: RunStatus | None,
    violations: Sequence[SeverityCarrier],
    warnings: Sequence[RunWarning],
) -> RunStatus:
    """The run's terminal status (§12.1).

    Order, per the owner's decision on round5-findings.json's ``resolve_status_precedence``:
    a ``FAILURE`` violation **outranks** a terminal status, so a rate-limited or network run
    whose bookkeeping also disagrees with the database is reported ``failed`` (exit 1) rather
    than exit 4 or 5, which an operator reads as "Reddit was unavailable, the next interval
    will catch up". ``runs.error`` keeps the terminal message and ``violations_json`` keeps
    the violation, so both halves of the story survive. Otherwise: a terminal status wins;
    else any warning or ``WARNING`` violation makes the run ``partial``; else ``ok``.
    """
    if any(violation.severity == SEVERITY_FAILURE for violation in violations):
        return RunStatus.FAILED
    if terminal is not None:
        return terminal
    if warnings or any(violation.severity == SEVERITY_WARNING for violation in violations):
        return RunStatus.PARTIAL
    return RunStatus.OK


def finish_run_from(
    ctx: RunContext, *, status: RunStatus, violations_json: str | None, error: str | None
) -> None:
    """Close the run row (T8).

    ``violations_json`` arrives **already serialized** because this module must not import
    ``services.invariants`` (§12.5); ``collect`` holds both halves and does the rendering.
    ``api_requests`` comes from ``ctx.budget.used``, the single value §6.6 feeds to all three
    consumers, so ``budget.used == counters.api_requests == runs.api_requests`` is structural.

    Deliberately **not** guarded on ``ctx.persisted``: a dry run never reaches T8, and the
    ``mode=ro`` engine turning a bug that does into an ``OperationalError`` is the backstop
    §7 relies on.
    """
    with ctx.engine.begin() as conn:
        repo.finish_run(
            conn,
            run_pk=ctx.run_pk,
            status=status.value,
            finished_at=ctx.clock.now(),
            counters_json=ctx.counters.to_json(),
            api_requests=ctx.budget.used,
            error=error,
            violations_json=violations_json,
            warnings_json=ctx.warnings_json(),
        )
