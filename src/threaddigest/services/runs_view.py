"""The read the Runs page needs: one ``runs`` row parsed once, for every surface.

``web`` may import ``db`` for reads, but a route that calls ``json.loads`` on
``counters_json`` is a second reader of the run row's format, and the second reader is the
one that drifts. So the parsing lives here, once: :func:`line_for` turns a
:class:`db.repo.RunDisplay` into a :class:`RunLine` whose counters, invariant violations and
budget are already values, and ``services/report.py`` uses the same function rather than
parsing the row a second way (N-20's two concrete uses).

**What a `partial` run can and cannot say.** ``ok`` means zero warnings and ``partial``
means at least one, so the page must be able to name the warning that made a run amber. All
three sources now survive into the database: an invariant's ``WARNING`` violation is in
``runs.violations_json``, a source's own failure is in ``run_subreddits.error`` beside its
``stop_reason``, and a warning recorded by ``services.runs.RunContext.warn`` is in
``runs.warnings_json`` since revision 0005. Both JSON columns are parsed into the same
:class:`RunProblem`, so a reader treats a named warning the same way whichever of the two
raised it.

A row written **before** that revision still carries a count and nothing else, and
:attr:`RunLine.unrecorded_warnings` is that gap stated as a number rather than hidden by
it: the count the row kept, less the ones it named. It is zero for every run since, and a
page that says "3 warnings, 1 named" is reading an old row rather than losing two.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Final

from sqlalchemy import Engine

from threaddigest.db import repo
from threaddigest.services.runs import Counters

__all__ = [
    "RunDetail",
    "RunLine",
    "RunProblem",
    "SourceLine",
    "line_for",
    "one",
    "recent",
]

#: ``services.invariants.Severity`` spelled as strings, so this module does not import the
#: invariants to read a row they wrote (the same one-way dependency ``services.runs`` keeps).
SEVERITY_FAILURE: Final = "failure"
SEVERITY_WARNING: Final = "warning"

#: ``invariant`` on the violation this module records when a JSON column will not parse.
#: Written rather than raised: a corrupted counter on one historical row must not take the
#: whole history page down, and a silent zero would be worse than either.
UNREADABLE: Final = "unreadable_run_row"


@dataclass(frozen=True, slots=True)
class RunProblem:
    """One entry of ``runs.violations_json`` or ``runs.warnings_json``, or a complaint about
    the row itself.

    ``invariant`` carries the invariant's name for a verdict and the warning's name for a
    recorded warning -- one field, because every reader asks the same question of it ("what
    is this called"), and a page that had to know which column a problem came from would be
    a second reader of the row's format.
    """

    invariant: str
    severity: str
    detail: str


@dataclass(frozen=True, slots=True)
class SourceLine:
    """One ``run_subreddits`` row with the source's display name attached."""

    subreddit_pk: int
    name: str
    progress: repo.SweepProgress


@dataclass(frozen=True, slots=True)
class RunLine:
    """One run, display-ready: the row plus its parsed counters, violations and budget."""

    run: repo.RunDisplay
    counters: Counters
    problems: tuple[RunProblem, ...]
    #: ``violations_json`` was NULL: the invariants did not run (a dry run, a cancelled run,
    #: a row a later run stamped ``crashed``). Not the same as ``[]``, which means they ran
    #: and found nothing.
    invariants_ran: bool
    #: ``options_json['budget']['limit']``: the budget this run was actually allowed, which
    #: is not today's configured budget and is the only honest denominator for its requests.
    budget_limit: int | None
    #: How many warnings ``warnings_json`` named. NULL on the column means none were
    #: recorded (a row from before revision 0005), which is not the same as ``[]``.
    recorded_warnings: int

    @property
    def duration_seconds(self) -> int | None:
        """Wall-clock seconds from start to finish; ``None`` while a run is unfinished."""
        if self.run.started_at is None or self.run.finished_at is None:
            return None
        return self.run.finished_at - self.run.started_at

    @property
    def failures(self) -> tuple[RunProblem, ...]:
        return tuple(p for p in self.problems if p.severity == SEVERITY_FAILURE)

    @property
    def warnings(self) -> tuple[RunProblem, ...]:
        return tuple(p for p in self.problems if p.severity == SEVERITY_WARNING)

    @property
    def unrecorded_warnings(self) -> int:
        """Warnings the run counted whose name no column kept (see the module docstring).

        Zero for every run since revision 0005, where the counter and the list are written
        together and a test asserts they are the same length. It stays honest for the rows
        written before it: those carry the count alone, and the page shows it as a number
        rather than as a silent zero.
        """
        return max(self.counters.warnings - self.recorded_warnings, 0)


def _loads(payload: str | None) -> Any | None:
    """``json.loads`` that answers ``None`` for a NULL column and for an unreadable one."""
    if payload is None:
        return None
    try:
        return json.loads(payload)
    except json.JSONDecodeError:
        return None


def _counters_of(payload: str | None) -> tuple[Counters, tuple[RunProblem, ...]]:
    if payload is None:
        return Counters(), ()
    loaded = _loads(payload)
    if not isinstance(loaded, dict):
        return Counters(), (
            RunProblem(
                invariant=UNREADABLE,
                severity=SEVERITY_FAILURE,
                detail="counters_json is not a readable JSON object; its counters are lost",
            ),
        )
    return Counters(**{key: int(loaded[key]) for key in Counters.KEYS if key in loaded}), ()


def _problems_of(payload: str | None) -> tuple[bool, tuple[RunProblem, ...]]:
    if payload is None:
        return False, ()
    loaded = _loads(payload)
    if not isinstance(loaded, list):
        return True, (
            RunProblem(
                invariant=UNREADABLE,
                severity=SEVERITY_FAILURE,
                detail="violations_json is not a readable JSON array; its verdicts are lost",
            ),
        )
    return True, tuple(
        RunProblem(
            invariant=str(entry.get("invariant", UNREADABLE)),
            severity=str(entry.get("severity", SEVERITY_FAILURE)),
            detail=str(entry.get("detail", "")),
        )
        for entry in loaded
        if isinstance(entry, dict)
    )


def _warnings_of(payload: str | None) -> tuple[RunProblem, ...]:
    """``runs.warnings_json`` as problems: a warning's name in ``invariant``, its detail
    beside it, severity ``warning`` because that is what a ``RunContext.warn`` warning is --
    the one thing that turns an ``ok`` run ``partial``."""
    loaded = _loads(payload)
    if payload is not None and not isinstance(loaded, list):
        return (
            RunProblem(
                invariant=UNREADABLE,
                severity=SEVERITY_FAILURE,
                detail="warnings_json is not a readable JSON array; its warnings are lost",
            ),
        )
    if not isinstance(loaded, list):
        return ()
    return tuple(
        RunProblem(
            invariant=str(entry.get("name", UNREADABLE)),
            severity=SEVERITY_WARNING,
            detail=str(entry.get("detail", "")),
        )
        for entry in loaded
        if isinstance(entry, dict)
    )


def _budget_limit_of(payload: str | None) -> int | None:
    loaded = _loads(payload)
    budget = loaded.get("budget") if isinstance(loaded, dict) else None
    limit = budget.get("limit") if isinstance(budget, dict) else None
    return int(limit) if isinstance(limit, int) else None


def line_for(run: repo.RunDisplay) -> RunLine:
    """Parse one run row. Pure: no connection, so a template never reaches the database."""
    counters, counter_problems = _counters_of(run.counters_json)
    invariants_ran, violations = _problems_of(run.violations_json)
    recorded = _warnings_of(run.warnings_json)
    return RunLine(
        run=run,
        counters=counters,
        # The run's own warnings last: an invariant's verdict is about the whole run and a
        # `warn` is about one moment in it, and a reader wants the general before the local.
        problems=counter_problems + violations + recorded,
        invariants_ran=invariants_ran,
        budget_limit=_budget_limit_of(run.options_json),
        recorded_warnings=sum(1 for problem in recorded if problem.invariant != UNREADABLE),
    )


def recent(engine: Engine, *, limit: int, before_pk: int | None = None) -> list[RunLine]:
    """One page of history, newest first; ``before_pk`` is the cursor of the next page."""
    with engine.connect() as conn:
        rows = repo.recent_runs(conn, limit=limit, before_pk=before_pk)
    return [line_for(row) for row in rows]


@dataclass(frozen=True, slots=True)
class RunDetail:
    """One run and what it did to each source."""

    line: RunLine
    sources: tuple[SourceLine, ...]


def one(engine: Engine, *, run_pk: int) -> RunDetail | None:
    """One run with its per-source outcomes, or ``None`` -- which the route turns into 404.

    The source rows are ordered by name rather than by pk, because the pk order is the order
    the sources were added and means nothing to a reader.
    """
    with engine.connect() as conn:
        row = repo.run_display(conn, run_pk=run_pk)
        if row is None:
            return None
        outcomes = repo.source_outcomes(conn, run_pks=[run_pk]).get(run_pk, {})
        names = repo.subreddit_names(conn, pks=sorted(outcomes))
    sources = sorted(
        (
            SourceLine(subreddit_pk=pk, name=names.get(pk, f"subreddit #{pk}"), progress=progress)
            for pk, progress in outcomes.items()
        ),
        key=lambda source: (source.name.lower(), source.subreddit_pk),
    )
    return RunDetail(line=line_for(row), sources=tuple(sources))
