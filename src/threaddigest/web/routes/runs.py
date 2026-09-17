"""The Runs pages: the history, and one run with what it did to each source.

Read-only. Nothing here writes, spawns, or takes the lock: **Run now**, Cancel and the live
panel need the process runner, a ``queued`` row, 409 handling, polling and the cancel stamp,
and they arrive together at M2 (spec rows UI-26 to UI-30). The pointer these two pages
answer already exists: the launchd wrapper links a failed run's notification to ``/runs``.

**Every read goes through ``services.runs_view``.** The layering contract would allow a
route to call ``db.repo`` directly -- ``web`` may read ``db`` -- but the run row's JSON
columns would then be parsed in two places, and the second reader is the one that drifts.
``runs_view`` parses them once for this page and for the digest.

**Which numbers carry a denominator, and why the two pages differ.** A number that is a
*share* of something is a :class:`Count` and prints with the population it came out of; a
number that is a total is a total. That is how ``core.digest.SubredditLine`` already treats
its own rows -- ``pages`` and ``items_seen`` are plain, ``new`` and ``updated`` are counts of
items seen -- and the pages follow it. The consequence is visible: the history shows no post
counters, because their population (``items seen``) lives in the per-source rows one join
away, and printing ``12 new posts`` on the history beside ``12 of 60 items seen`` on the
detail page would be two statements of one number. The detail page has the join, so it shows
both halves there.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Annotated, Final

from fastapi import APIRouter, HTTPException, Path, Query, Request
from fastapi.responses import HTMLResponse
from starlette.responses import Response

from threaddigest.core.digest import Count, Problem
from threaddigest.services import runs_view
from threaddigest.settings import Settings
from threaddigest.web.deps import EngineDep, SettingsDep, TemplatesDep

__all__ = ["PAGE_SIZE", "RunView", "router", "run_page", "runs_page"]

router = APIRouter()

#: Runs per page of history, and the page size the UI design review's feed uses. The cursor
#: is the pk of the last row shown, which ``repo.recent_runs`` treats as strictly exclusive.
PAGE_SIZE: Final = 25

#: ``runs.status`` → the word the stylesheet and the reader key on. Derived from the row,
#: never from a flag beside it (spec row UI-31's own negative control is a banner keyed on a
#: flag file). A status no one has mapped falls to :data:`UNMAPPED_VERDICT`: an unknown
#: terminal state is a problem to look at, and must never read as green.
VERDICT_FOR_STATUS: Final[Mapping[str, str]] = {
    "ok": "ok",
    "partial": "warn",
    "queued": "busy",
    "running": "busy",
    "cancelled": "muted",
    "skipped_locked": "muted",
    "failed": "error",
    "crashed": "error",
    "rate_limited": "error",
    "network": "error",
}
UNMAPPED_VERDICT: Final = "error"

#: Populations, spelled once. ``items seen`` is the digest's own wording for the same
#: denominator (``services/report.py``), so the page and the digest of one run agree.
ITEMS_SEEN: Final = "items seen"
COMMENTS_SEEN: Final = "comments seen"
BUDGETED_REQUESTS: Final = "budgeted requests"
WARNINGS_THIS_RUN: Final = "warnings this run"

_NO_DETAIL: Final = "(no detail recorded)"
_UNNAMED_INVARIANT: Final = "unnamed invariant"

#: A pk is a SQLite ``INTEGER``, so it cannot exceed a signed 64-bit value. Declared as the
#: bound of the path parameter rather than discovered by the driver: without it, a URL with
#: forty digits in it reaches the query and raises ``OverflowError`` -- a 500 where a 422 is
#: the honest answer (spec row UI-03).
_MAX_PK: Final = 2**63 - 1


@dataclass(frozen=True, slots=True)
class RunView:
    """One run as a page prints it: the parsed line, its verdict, its counts, its problems."""

    line: runs_view.RunLine
    verdict: str
    requests: Count
    warnings: Count
    problems: tuple[Problem, ...]


@dataclass(frozen=True, slots=True)
class SourceView:
    """One source's outcome in this run, counted the way the digest counts the same row.

    ``new`` and ``updated`` are shares of what the sweep saw, exactly as
    ``core.digest.SubredditLine.new`` and ``.updated`` are; ``pages`` is a total, as it is
    there. The source's own ``items_seen`` is inside both counts, so it needs no column.
    """

    name: str
    pages: int
    new: Count
    updated: Count
    stop_reason: str | None
    error: str | None


def _source_view(source: runs_view.SourceLine) -> SourceView:
    progress = source.progress
    return SourceView(
        name=source.name,
        pages=progress.pages,
        new=Count(n=progress.new_items, of=progress.items_seen, population=ITEMS_SEEN),
        updated=Count(n=progress.updated_items, of=progress.items_seen, population=ITEMS_SEEN),
        stop_reason=progress.stop_reason,
        error=progress.error,
    )


def _problems(line: runs_view.RunLine) -> tuple[Problem, ...]:
    """Everything the row can say, in words, about why a run is not green.

    Three sources, in the order a reader wants them: the invariant verdicts the run recorded,
    the warnings it counted but could not name (``services/runs_view.py`` explains why the
    name does not survive), and the error text that closed the run.
    """
    named = tuple(
        Problem(where=problem.invariant or _UNNAMED_INVARIANT, message=problem.detail or _NO_DETAIL)
        for problem in line.problems
    )
    unnamed = line.unrecorded_warnings
    counted = (
        (
            Problem(
                where="run warnings",
                message=(
                    f"{unnamed} warning(s) the run counted; no column keeps a warning's name "
                    "or detail, so they are reported as a number rather than as a silent zero"
                ),
            ),
        )
        if unnamed
        else ()
    )
    recorded = (Problem(where=line.run.kind, message=line.run.error),) if line.run.error else ()
    return named + counted + recorded


def _view(line: runs_view.RunLine) -> RunView:
    """The run-level numbers both pages print, built once."""
    named_warnings = len(line.warnings)
    return RunView(
        line=line,
        verdict=VERDICT_FOR_STATUS.get(line.run.status, UNMAPPED_VERDICT),
        requests=Count(
            n=line.run.api_requests,
            # 0 when the row recorded no budget (a run from before the flag was written, or a
            # `skipped_locked` row with no options at all): `Count` prints no percentage
            # against an empty population, which is the honest shape for "not recorded".
            of=line.budget_limit if line.budget_limit is not None else 0,
            population=BUDGETED_REQUESTS,
        ),
        # Named of counted: "1 of 3 warnings this run" says both what is on the page and how
        # much the page cannot show, instead of showing one and implying it is all of them.
        warnings=Count(
            n=named_warnings,
            of=named_warnings + line.unrecorded_warnings,
            population=WARNINGS_THIS_RUN,
        ),
        problems=_problems(line),
    )


def _context(settings: Settings, *, heading: str, **extra: object) -> dict[str, object]:
    """The keys every template needs. ``StrictUndefined`` makes a missing one an error."""
    return {"heading": heading, "zone": settings.static.display_timezone, "nav": "runs", **extra}


@router.get("/runs", name="runs_page", response_class=HTMLResponse)
def runs_page(
    request: Request,
    engine: EngineDep,
    settings: SettingsDep,
    templates: TemplatesDep,
    before: Annotated[int | None, Query(ge=1)] = None,
) -> Response:
    """The run history, newest first, paged by the pk of the last row shown."""
    # One row more than the page is read, so "is there a next page" is answered by the
    # database rather than guessed from a full page (a full last page would otherwise offer
    # a next link onto nothing).
    lines = runs_view.recent(engine, limit=PAGE_SIZE + 1, before_pk=before)
    shown = [_view(line) for line in lines[:PAGE_SIZE]]
    next_url = (
        f"{request.url_for('runs_page').path}?before={shown[-1].line.run.pk}"
        if len(lines) > PAGE_SIZE and shown
        else None
    )
    return templates.TemplateResponse(
        request,
        "runs.html",
        _context(settings, heading="Runs", runs=shown, next_url=next_url),
    )


@router.get("/runs/{run_id}", name="run_page", response_class=HTMLResponse)
def run_page(
    request: Request,
    run_id: Annotated[int, Path(ge=1, le=_MAX_PK)],
    engine: EngineDep,
    settings: SettingsDep,
    templates: TemplatesDep,
) -> Response:
    """One run: its counters against the populations it measured, and every source it swept."""
    detail = runs_view.one(engine, run_pk=run_id)
    if detail is None:
        raise HTTPException(status_code=404, detail=f"no run #{run_id} is recorded")
    view = _view(detail.line)
    counters = detail.line.counters
    items_seen = sum(source.progress.items_seen for source in detail.sources)
    shares: tuple[tuple[str, Count], ...] = (
        ("New posts", Count(n=counters.posts_new, of=items_seen, population=ITEMS_SEEN)),
        ("Updated posts", Count(n=counters.posts_updated, of=items_seen, population=ITEMS_SEEN)),
        ("Rejected items", Count(n=counters.rejects, of=items_seen, population=ITEMS_SEEN)),
        # No tree is fetched before M1b, so nothing was seen for a comment to be new out of:
        # `0 of 0` says the stage did not run, where `0 of <posts>` would imply a tree was
        # read and found empty (the same choice `services/report.py` makes).
        ("New comments", Count(n=counters.comments_new, of=0, population=COMMENTS_SEEN)),
        ("Requests", view.requests),
        ("Warnings named", view.warnings),
    )
    totals: tuple[tuple[str, int], ...] = (
        ("Pages fetched", counters.pages),
        ("Items seen", items_seen),
        ("Raw enum values stored", counters.unknown_enum_values),
        ("Scrubs pending", counters.scrubs_pending),
    )
    return templates.TemplateResponse(
        request,
        "run.html",
        _context(
            settings,
            heading=f"Run #{detail.line.run.pk}",
            view=view,
            sources=[_source_view(source) for source in detail.sources],
            shares=shares,
            totals=totals,
        ),
    )
