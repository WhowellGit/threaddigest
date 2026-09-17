"""The digest page: one run's report, assembled on the way out and never written down.

**The digest is a route, not a file** (``DECISIONS.md`` § 2, row Digests). Nothing here writes
a copy and no page offers a download: a persisted digest could quote the title of a post its
author deleted the next day, and the compliance obligation attaches to every stored copy, not
only to the database. The model is built by ``services.report.assemble_digest`` at the moment
the page is opened, from the run row, its counters, its ``violations_json``, the
``run_subreddits`` join and the live counts, and it is the same model ``threaddigest report``
will render at M1d -- one assembler, so a number cannot differ between the page and the file
a reader asks for later.

**Three routes, two of them addresses rather than pages.** ``/`` is the front door and sends a
reader to the run history, which is the page that is fully itself today. ``/reports`` resolves
"the digest" to the newest finished run's local date and sends the reader there, so the header
link needs no date in it and cannot go stale; with no finished run it is a 404 saying so,
which is the truth rather than an empty page. ``/reports/{date}`` is the page.

**What a thin section looks like.** Comment trees (M1b), reconcile and scrub (M1c), themes and
rising phrases (M1d) are not built, and the sections that depend on them are neither hidden nor
filled with invented numbers: each renders its real denominator -- often ``0 of 0``, which says
"this stage did not run" where ``0 of <posts>`` would claim a stage ran and found nothing -- and
carries a one-line note naming what has not been collected. Every note is derived from the model
rather than typed as a milestone, so each one disappears by itself on the day its stage lands.

**One status vocabulary.** The verdict word behind the pill is read from
``routes/runs.py``'s map rather than spelled again here: two maps would eventually disagree
about what ``partial`` looks like, and the map's completeness against the ``runs.status``
CHECK constraint is already proven once (``tests/web/test_runs_page.py``). An unmapped status
falls to the same problem-coloured default there and here, never to green.

**Why this template and not ``core.digest.render_html``.** That renderer produces a whole
standalone document for a file or an email; this page is the same model in the site's own
chrome, beside the Runs pages. Both print every number through ``Count.__str__``, so the two
renderings can differ in layout but not in what they say.
"""

from __future__ import annotations

from datetime import date
from typing import Final

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.responses import Response

from threaddigest.core.digest import STALE_AFTER_RUNS
from threaddigest.services.report import NoRunForDateError, assemble_digest, latest_report_date
from threaddigest.web.deps import EngineDep, SettingsDep, TemplatesDep
from threaddigest.web.routes.runs import UNMAPPED_VERDICT, VERDICT_FOR_STATUS

__all__ = ["SEE_OTHER", "home", "report_page", "reports_index", "router"]

router = APIRouter()

#: 303, not 302: the redirect answers "where the thing you asked for lives" rather than moving
#: the resource, and a 303 is the one code that is defined to be followed with a GET.
SEE_OTHER: Final = 303


@router.get("/", name="home", include_in_schema=False)
def home(request: Request) -> Response:
    """The front door. The run history is the page that is complete today, so it is the landing.

    The target is written as a path rather than the absolute URL ``url_for`` builds, so a
    reader who opened the server as ``localhost`` is not bounced onto ``127.0.0.1`` -- the same
    rule every link in ``base.html`` follows.
    """
    return RedirectResponse(request.url_for("runs_page").path, status_code=SEE_OTHER)


@router.get("/reports", name="reports_index", include_in_schema=False)
def reports_index(request: Request, engine: EngineDep, settings: SettingsDep) -> Response:
    """The digest, resolved to the newest finished run's local date.

    The header link points here rather than at a date, so it cannot go stale and no page has to
    carry tomorrow's date in its markup.
    """
    newest = latest_report_date(engine, settings=settings)
    if newest is None:
        raise HTTPException(
            status_code=404,
            detail=(
                "no run has finished yet, so there is no digest to show; the first scheduled "
                "or manual run writes one"
            ),
        )
    return RedirectResponse(
        request.url_for("report_page", report_date=newest.isoformat()).path,
        status_code=SEE_OTHER,
    )


@router.get("/reports/{report_date}", name="report_page", response_class=HTMLResponse)
def report_page(
    request: Request,
    report_date: date,
    engine: EngineDep,
    settings: SettingsDep,
    templates: TemplatesDep,
) -> Response:
    """The digest for one local day.

    ``report_date`` is declared as a ``date``, so an unparseable path segment is refused as a
    422 before any query runs (spec row UI-03); a well-formed date with no finished run behind
    it is a 404 carrying one sentence, because a reader who mistyped a day needs to be told
    that, not shown an empty report that reads as a quiet week.
    """
    try:
        model = assemble_digest(engine, settings=settings, report_date=report_date)
    except NoRunForDateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "heading": f"Digest for {report_date.isoformat()}",
            "zone": model.display_timezone,
            "nav": "report",
            "model": model,
            "verdict": VERDICT_FOR_STATUS.get(model.summary.status.value, UNMAPPED_VERDICT),
            "run_url": request.url_for("run_page", run_id=model.summary.run_id).path,
            # The staleness threshold the freshness invariant judges by, passed in rather than
            # written into the page: one constant, so the sentence and the verdict agree.
            "stale_after_runs": STALE_AFTER_RUNS,
        },
    )
