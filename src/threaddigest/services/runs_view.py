"""The read the Runs page needs: one ``runs`` row parsed once, for every surface.

``web`` may import ``db`` for reads, but a route that calls ``json.loads`` on
``counters_json`` is a second reader of the run row's format, and the second reader is the
one that drifts. So the parsing lives here, once: :func:`line_for` turns a
:class:`db.repo.RunDisplay` into a :class:`RunLine` whose counters, invariant violations and
budget are already values, and ``services/report.py`` uses the same function rather than
parsing the row a second way (N-20's two concrete uses).

**What a `partial` run can and cannot say.** ``ok`` means zero warnings and ``partial``
means at least one, so the page must be able to name the warning that made a run amber. Two
of the three sources survive into the database: an invariant's ``WARNING`` violation is in
``runs.violations_json``, and a source's own failure is in ``run_subreddits.error`` beside
its ``stop_reason``. The third does not: ``services.runs.RunContext.warn`` records a name
and a detail in memory, and only the **count** reaches the row, in
``counters_json["warnings"]``. :attr:`RunLine.unrecorded_warnings` is that gap stated as a
number rather than hidden by it, so a page says "3 warnings, 1 named" instead of quietly
showing one. Closing it needs a column and therefore a migration; until then the count is
the honest denominator.
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
    """One entry of ``runs.violations_json``, or a complaint about the row itself."""

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
        """Warnings the run counted whose detail no column kept (see the module docstring)."""
        return max(self.counters.warnings, 0)


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


def _budget_limit_of(payload: str | None) -> int | None:
    loaded = _loads(payload)
    budget = loaded.get("budget") if isinstance(loaded, dict) else None
    limit = budget.get("limit") if isinstance(budget, dict) else None
    return int(limit) if isinstance(limit, int) else None


def line_for(run: repo.RunDisplay) -> RunLine:
    """Parse one run row. Pure: no connection, so a template never reaches the database."""
    counters, counter_problems = _counters_of(run.counters_json)
    invariants_ran, violations = _problems_of(run.violations_json)
    return RunLine(
        run=run,
        counters=counters,
        problems=counter_problems + violations,
        invariants_ran=invariants_ran,
        budget_limit=_budget_limit_of(run.options_json),
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
