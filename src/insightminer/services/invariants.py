"""The post-run invariants: the contract, the M1a list, and the runner ``collect`` calls
(design-round5.md §14, §13.2, §12.1, §19.1).

Four rules shape this module:

* **The function's ``__name__`` is the recorded name.** Every invariant is a plain named
  function and every :class:`Violation` is built through :func:`_violation`, which reads
  ``__name__`` off the function object -- so a rename cannot drift from the ledger the
  operator reads in ``runs.violations_json`` (§14.1).
* **Severity is the whole status story.** ``WARNING`` makes the run ``partial``, ``FAILURE``
  makes it ``failed``, and ``ok`` requires zero of both (§19.1, Wes's ruling on
  TEST_STRATEGY line 259). ``services.runs.resolve_status`` reads only ``.severity``, which
  is why :class:`Severity` is a ``StrEnum``.
* **Every invariant is a read.** Nothing here opens a transaction (T7): ``check_all`` is
  handed one ``Connection`` and returns a list. A crash inside one invariant is caught *per
  invariant* so the violation names the invariant that blew up and the run is still closed
  through the ordinary ``finish_run`` path, never left ``running`` (§14.1, §7, §8).
* **``services.runs`` never imports this module** (§12.5). The dependency runs one way:
  this module reads ``Counters``/``TRACKED_TABLES``/``DELTA_COUNTER_FOR_TABLE`` from
  ``runs``, and ``collect`` (step 7) is the only thing that holds both halves.

The broad catch in :func:`check_all` is the one place in the tranche that catches
``Exception``. It logs the traceback through ``logger.exception`` and records the crash as a
``FAILURE`` violation, which is the shape ruff's ``BLE001`` accepts without a suppression;
§14.1 wrote it as ``except Exception as exc:  # noqa: BLE001`` instead, but the suppression
ratchet's ``noqa`` ceiling has zero slack and can only be raised by ``make ratchet-loosen``,
which needs the owner's approval. The reason §14.1 requires in writing is the comment on the
handler: *an invariant crash must still close the run row*.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Final

from sqlalchemy import Connection

from insightminer.core.models import KNOWN_VALUES
from insightminer.core.retry import RunStatus
from insightminer.db import fts, repo
from insightminer.services import runs
from insightminer.settings import Settings

__all__ = [
    "FLOOR_COLUMNS",
    "FRESHNESS_STATUSES",
    "FRESHNESS_WINDOW",
    "INVARIANTS",
    "SUCCESSFUL_STOP_REASONS",
    "Invariant",
    "InvariantContext",
    "Severity",
    "Violation",
    "check_all",
    "counters_equal_table_deltas",
    "fts_membership_equals_live",
    "no_other_running_rows",
    "per_source_freshness",
    "population_floors_hold",
    "render",
    "rows_carry_current_normalizer_version",
    "to_json",
    "unknown_enum_values_are_counted",
]

logger = logging.getLogger("insightminer.invariants")

#: How many sweeping runs the freshness window spans, the current run included (§14.2).
FRESHNESS_WINDOW: Final = 2

#: Run statuses that count as "this run swept something". Re-exported from ``db.repo``,
#: which owns the query that consumes it, so the two cannot drift (§14.2).
FRESHNESS_STATUSES: Final[frozenset[str]] = repo.FRESHNESS_STATUSES

#: ``run_subreddits.stop_reason`` values that mean the source was fetched successfully in
#: that run -- the same predicate §6.5 uses to clear a source's error trio, so the freshness
#: window and the source's own status can never disagree (§14.2).
SUCCESSFUL_STOP_REASONS: Final[frozenset[str]] = frozenset({"exhausted", "cap"})

#: ``posts`` columns the population floor covers (DB-50/DB-51/NM-03a). ``selftext_html`` is
#: additionally scoped to non-empty self posts inside ``repo.live_rows_missing``.
FLOOR_COLUMNS: Final[tuple[str, ...]] = ("permalink", "author_fullname", "selftext_html")

#: Tables carrying both an FTS index and a ``normalizer_version``. ``comments`` stays empty
#: through tranche A; naming it here is what makes M1b's first comment write covered.
INDEXED_TABLES: Final[tuple[str, ...]] = ("posts", "comments")


class Severity(StrEnum):
    """A violation's consequence for ``runs.status`` (§19.1)."""

    WARNING = "warning"
    """The run ends ``partial`` (amber): the floors, freshness, FTS membership, DB-48."""

    FAILURE = "failure"
    """The run ends ``failed`` (red): DB-54's counter deltas, a second ``running`` row."""


@dataclass(frozen=True, slots=True)
class Violation:
    """One invariant's complaint, as it is written to ``runs.violations_json``."""

    invariant: str
    severity: Severity
    detail: str

    def as_dict(self) -> dict[str, str]:
        """The three keys ``violations_json`` carries, in the order §14.1 lists them."""
        return {
            "invariant": self.invariant,
            "severity": self.severity.value,
            "detail": self.detail,
        }


@dataclass(frozen=True, slots=True)
class InvariantContext:
    """Everything the invariants read. Built by ``collect`` after the sweep returns (§3.3).

    ``terminal_status`` comes from ``SweepResult.terminal_status``, so
    :func:`per_source_freshness`'s stand-down is data rather than a flag someone has to
    remember to pass (§14.2).
    """

    conn: Connection
    run_pk: int
    run_started_at: int
    now: int
    counters: runs.Counters
    baseline_counts: Mapping[str, int]
    normalizer_version: int
    settings: Settings
    terminal_status: RunStatus | None


type Invariant = Callable[[InvariantContext], Violation | None]


def _violation(invariant: Invariant, severity: Severity, detail: str) -> Violation:
    """Build a violation whose name is the invariant's ``__name__`` (§14.1)."""
    return Violation(invariant=invariant.__name__, severity=severity, detail=detail)


# --- the list (§14.2) -----------------------------------------------------------------------


def counters_equal_table_deltas(ctx: InvariantContext) -> Violation | None:
    """DB-54: every counted write shows up in the table it claims to have written.

    ``DELTA_COUNTER_FOR_TABLE``'s three tables must match their counter exactly; every other
    tracked table must merely not *decrease*, since nothing in tranche A deletes rows and
    ``runs.purge_counts_json`` becomes the exemption at M1c (DB-55, §13.2 step 4).

    The baselines were read in memory right after ``start_run`` committed (T3), which is
    correct: the invariant only runs in the process that completed the run.
    """
    after = repo.table_counts(ctx.conn, runs.TRACKED_TABLES)
    for table, counter in runs.DELTA_COUNTER_FOR_TABLE.items():
        delta = after[table] - ctx.baseline_counts.get(table, 0)
        counted = int(getattr(ctx.counters, counter))
        if delta != counted:
            return _violation(
                counters_equal_table_deltas,
                Severity.FAILURE,
                f"{table}: delta {delta} != counters.{counter} {counted}",
            )
    for table in runs.TRACKED_TABLES:
        if table in runs.DELTA_COUNTER_FOR_TABLE:
            continue
        delta = after[table] - ctx.baseline_counts.get(table, 0)
        if delta < 0:
            return _violation(
                counters_equal_table_deltas,
                Severity.FAILURE,
                f"{table}: delta {delta} with no recorded purge",
            )
    return None


def no_other_running_rows(ctx: InvariantContext) -> Violation | None:
    """A second ``running`` row means two collectors, i.e. the flock did not hold.

    The stale sweep (§12.2) has already condemned every row it could judge before this run
    started, so anything still ``running`` here is genuinely concurrent.
    """
    others = repo.running_runs(ctx.conn, exclude_pk=ctx.run_pk)
    if not others:
        return None
    detail = "; ".join(
        f"run {row.pk} is also running (pid {row.pid}, heartbeat {_age(ctx.now, row.heartbeat_at)})"
        for row in others
    )
    return _violation(no_other_running_rows, Severity.FAILURE, detail)


def fts_membership_equals_live(ctx: InvariantContext) -> Violation | None:
    """DB-26: the search index holds exactly the live rows, and each indexed entry matches its
    content row.

    Two checks, because a count is not enough (KI-022, external round one): membership from the
    ``_docsize`` shadow table catches a missing or extra entry, but a delete-then-insert that
    swaps one row's tokens for another's leaves the count unchanged while search returns the
    wrong document. FTS5's ``integrity-check`` in the ``rank = 1`` form (``db.fts``) compares
    the index against the content view and catches exactly that substitution. Membership comes
    from ``_docsize``, never ``count(*)`` on the FTS table itself: on an external-content table
    that reads the content source and can never disagree.
    """
    live = repo.live_counts(ctx.conn)
    for table in INDEXED_TABLES:
        fts_table = f"{table}_fts"
        membership = fts.fts_membership_count(ctx.conn, fts_table)
        live_rows = live[f"{table}_live"]
        if membership != live_rows:
            return _violation(
                fts_membership_equals_live,
                Severity.WARNING,
                f"{table}: fts membership {membership} != {table}_live {live_rows}",
            )
        if not fts.integrity_check(ctx.conn, fts_table):
            return _violation(
                fts_membership_equals_live,
                Severity.WARNING,
                f"{table}: fts index does not match its content rows (integrity-check failed)",
            )
    return None


def rows_carry_current_normalizer_version(ctx: InvariantContext) -> Violation | None:
    """DB-48: nothing written this run was rendered by an older normalizer.

    "Written this run" is ``last_fetched_at >= ctx.run_started_at``: there is no ``run_pk``
    on ``posts``, and the only failure mode -- a second run starting inside the same second
    -- is documented rather than defended against (§14.2).
    """
    for table in INDEXED_TABLES:
        stale = repo.rows_below_normalizer_version(
            ctx.conn, table=table, since=ctx.run_started_at, version=ctx.normalizer_version
        )
        if stale:
            return _violation(
                rows_carry_current_normalizer_version,
                Severity.WARNING,
                f"{table}: {stale} row(s) written this run carry normalizer_version below "
                f"{ctx.normalizer_version}",
            )
    return None


def unknown_enum_values_are_counted(ctx: InvariantContext) -> Violation | None:
    """DB-25/NM-02: every unknown enum value in the database was counted by the sweep.

    Both sides are sets over the distinct posts written this run and over the same two
    fields (``post_hint``, ``removed_by_category``), so the only way the sizes can differ is
    a writer that is not the sweep -- which is precisely what the planted control is (§14.2).

    The detail names the DB side by key and the counter by number. §14.2 asks for the
    symmetric difference in both directions; :class:`InvariantContext` carries
    ``counters.unknown_enum_values`` (a count) and not the run's ``unknown_enum_keys`` set
    (§3.3), so the counted side can only be named as a number without widening the context.
    """
    known = {field: KNOWN_VALUES.known(field) for field in repo.UNKNOWN_ENUM_FIELDS}
    found = repo.unknown_enum_occurrences(ctx.conn, since=ctx.run_started_at, known=known)
    observed = sorted(set(found))
    counted = int(ctx.counters.unknown_enum_values)
    if len(observed) == counted:
        return None
    return _violation(
        unknown_enum_values_are_counted,
        Severity.WARNING,
        f"the DB holds {len(observed)} unknown enum occurrence(s) "
        f"[{', '.join(observed) or 'none'}] but counters.unknown_enum_values is {counted}",
    )


def population_floors_hold(ctx: InvariantContext) -> Violation | None:
    """DB-50/DB-51/NM-03a: the floored columns are non-NULL over a population that exists.

    Clause (a) is the floor itself; clause (b) is DB-51's "empty population fails" -- a floor
    that silently evaluates over zero rows is inert, so an empty qualifying population while
    the counters say posts were written is itself the violation. A legitimate zero-new run
    writes no posts, so clause (b) cannot fire on it (§14.2).
    """
    for column in FLOOR_COLUMNS:
        missing = repo.live_rows_missing(
            ctx.conn,
            column=column,
            since=ctx.run_started_at,
            normalizer_version=ctx.normalizer_version,
        )
        if missing:
            return _violation(
                population_floors_hold,
                Severity.WARNING,
                f"posts.{column}: {missing} live row(s) written this run carry NULL",
            )
    written = int(ctx.counters.posts_new) + int(ctx.counters.posts_updated)
    if written > 0 and _floor_population(ctx) == 0:
        return _violation(
            population_floors_hold,
            Severity.WARNING,
            f"the floored population is empty while counters recorded {written} post "
            f"write(s) (posts_new {ctx.counters.posts_new}, "
            f"posts_updated {ctx.counters.posts_updated})",
        )
    return None


def per_source_freshness(ctx: InvariantContext) -> Violation | None:
    """FR-01: every source was fetched successfully at least once in the freshness window.

    The window is the newest :data:`FRESHNESS_WINDOW` runs that actually swept something;
    the current run is inside it, so the invariant becomes informative on the second
    sweeping run rather than the third. Fewer than two such runs means there is nothing to
    say yet (§14.2).
    """
    if ctx.terminal_status is not None:
        # The run stopped before it could reach the remaining sources (auth, HTML 403,
        # network, a second 429). Reporting them as unfetched would add noise to
        # runs.violations_json on exactly the runs an operator reads most carefully, and
        # would say nothing the terminal cause does not already say (§14.2, round-4 P2).
        return None
    window = repo.recent_sweeping_runs(ctx.conn, current_run_pk=ctx.run_pk, limit=FRESHNESS_WINDOW)
    if len(window) < FRESHNESS_WINDOW:
        return None
    outcomes = repo.source_outcomes(ctx.conn, run_pks=window)
    sources = repo.all_sources_for_freshness(ctx.conn, repo.default_workspace_pk(ctx.conn))
    stale = [
        source
        for source in sources
        if not any(_fetched_successfully(outcomes.get(pk, {}).get(source.pk)) for pk in window)
    ]
    if not stale:
        return None
    detail = "; ".join(
        f"r/{source.display_name} not fetched in the last {len(window)} sweeping runs"
        for source in stale
    )
    return _violation(per_source_freshness, Severity.WARNING, detail)


#: The production list, in the order ``check_all`` runs and reports them (§14.1). The gate
#: in ``tests/gates/test_invariants_planted.py`` is parametrized over this tuple, so an
#: invariant added without a positive control is a ``KeyError``, not a silent gap.
INVARIANTS: Final[tuple[Invariant, ...]] = (
    counters_equal_table_deltas,
    no_other_running_rows,
    fts_membership_equals_live,
    rows_carry_current_normalizer_version,
    unknown_enum_values_are_counted,
    population_floors_hold,
    per_source_freshness,
)


# --- the runner and its two renderings (§14.1) ----------------------------------------------


def check_all(ctx: InvariantContext) -> list[Violation]:
    """Run every invariant and return the violations in :data:`INVARIANTS` order.

    The catch is here, **per invariant**, rather than around the call in ``collect``: that
    is what lets the violation name the invariant that crashed (a broad catch in ``collect``
    could only say "something in check_all blew up"), and it keeps ``collect`` free of any
    broad handler. The run is then finished ``failed`` through the ordinary ``finish_run``
    path, so the row is never left ``running`` on this code path (§14.1, §7 T7, §8).
    """
    violations: list[Violation] = []
    for invariant in INVARIANTS:
        try:
            found = invariant(ctx)
        except Exception as exc:
            # An invariant crash must still close the run row: the crash becomes a FAILURE
            # violation naming this invariant, and the pass continues with the next one.
            # The traceback goes to the log because the violation keeps only the class and
            # the message (ruff BLE001 accepts a blind catch that logs the exception).
            logger.exception("invariant %s crashed", invariant.__name__)
            violations.append(
                Violation(
                    invariant=invariant.__name__,
                    severity=Severity.FAILURE,
                    detail=f"invariant crashed: {type(exc).__name__}: {exc}",
                )
            )
            continue
        if found is not None:
            violations.append(found)
    return violations


def render(violations: Sequence[Violation]) -> str:
    """The one-line summary for the CLI's stdout and M1d's digest line.

    Not what goes in the database: ``runs.violations_json`` takes :func:`to_json`, which
    GT-01 asserts on structurally rather than by matching a substring of this string
    (§14.1, Wes's Q2).
    """
    noun = "violation" if len(violations) == 1 else "violations"
    body = "; ".join(f"{v.invariant}: {v.detail}" for v in violations)
    return f"{len(violations)} invariant {noun}: {body}"


def to_json(violations: Sequence[Violation]) -> str:
    """``runs.violations_json``: always an array, ``"[]"`` when empty.

    ``"[]"`` is **not** the same as NULL: ``[]`` means the invariants ran and found nothing,
    NULL means they did not run (a dry run, a ``cancelled`` run, a row someone else stamped
    ``crashed``) -- so ``collect`` passes NULL rather than this on those paths (§14.1).
    """
    return json.dumps([v.as_dict() for v in violations], separators=(",", ":"))


# --- small helpers ---------------------------------------------------------------------------


def _age(now: int, at: int | None) -> str:
    """How long ago ``at`` was, for a violation detail; ``"never"`` when it is NULL.

    Deliberately not ``runs._last_seen``'s ``coalesce(heartbeat_at, started_at, created_at)``:
    that function decides whether a row is *stale* and every fallback is load-bearing, while
    this one only prints a number an operator reads next to the pid. A row with no heartbeat
    at all is the honest "never", not a silently substituted ``started_at``.
    """
    return "never" if at is None else f"{now - at}s ago"


def _floor_population(ctx: InvariantContext) -> int:
    """How many rows the floors evaluate over: live, known-author posts written this run at
    the current normalizer version -- ``repo.live_rows_missing``'s predicate without the
    NULL clause. Read only when the counters say posts were written, because it answers
    clause (b) and nothing else (§14.2)."""
    return repo.floor_population(
        ctx.conn, since=ctx.run_started_at, normalizer_version=ctx.normalizer_version
    )


def _fetched_successfully(progress: repo.SweepProgress | None) -> bool:
    """Did one run fetch one source successfully? (§14.2's freshness predicate.)"""
    return (
        progress is not None
        and progress.stop_reason in SUCCESSFUL_STOP_REASONS
        and progress.error is None
    )
