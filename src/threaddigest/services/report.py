"""Assembling one :class:`core.digest.DigestModel` from the database.

The digest is a **route, not a file** (``DECISIONS.md`` § 2, row Digests): it is computed on
demand from the run row, its counters, its ``violations_json``, the ``run_subreddits`` join
and the live counts, so it can never quote a title that was deleted the next day.
``/reports/{date}`` and, at M1d, ``threaddigest report`` call :func:`assemble_digest` and
render the one model, which is what makes a number the same on both surfaces.

**How an unbuilt stage is reported.** Comment trees (M1b), theme tagging, rising phrases
(M1d) and scrub/reconcile (M1c) are not built. Their sections are neither omitted nor
invented: every count keeps a real denominator and states an honest zero, and where no
population exists yet the count is ``0 of 0``, which reads as "this stage did not run"
rather than as a finding. Concretely, today:

* no comment is captured, so every post has zero distinct authors, the ranking falls through
  to comment count and score, and no untagged post reaches the three-author threshold -- the
  threshold and the window are still printed, which is the point;
* no theme exists, so ``WorkspaceSection.themes`` is empty and every post in the window is
  untagged: the untagged denominator is the window's real size;
* no phrase extractor exists, so ``RisingPhrasesSection.phrases`` is empty while its two
  title populations are counted for real, so only the list changes when M1d lands;
* no tree is fetched and no reconcile has run, so the backlog is ``0 of 0`` and the
  compliance section reports what the run row and the live counts actually hold.

**What an older run row still cannot say.** Since revision 0005 a run records the resolved
non-secret settings and the warnings it raised, so the digest names the keys that changed
and the warnings that made the run amber. A row written before it carries only a
fingerprint and a count: the settings line then says which keys changed is not recorded --
never that nothing changed -- and each counted warning appears as its own unnamed problem
(``services/runs_view.py`` explains the gap and where it ends).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Final
from zoneinfo import ZoneInfo

from sqlalchemy import Connection, Engine

from threaddigest.adapters.clock import SystemClock
from threaddigest.core.digest import (
    STALE_AFTER_RUNS,
    Backlog,
    Compliance,
    Count,
    DigestModel,
    Problem,
    RisingPhrasesSection,
    RunSummary,
    SettingChange,
    SubredditLine,
    SubredditStatus,
    UnknownEnum,
    UnknownEnumSection,
    UntaggedSection,
    WorkspaceSection,
)
from threaddigest.core.models import KNOWN_VALUES
from threaddigest.core.retry import RunStatus
from threaddigest.db import repo
from threaddigest.ports import Clock
from threaddigest.services import runs_view
from threaddigest.services.invariants import SUCCESSFUL_STOP_REASONS
from threaddigest.settings import Settings, non_secret_settings

__all__ = [
    "BASELINE_WEEKS",
    "MIN_DISTINCT_AUTHORS",
    "TOP_POSTS",
    "WINDOW_DAYS",
    "NoRunForDate",
    "NoRunForDateError",
    "SETTING_ABSENT",
    "assemble_digest",
    "latest_report_date",
]

#: The digest's discovery window, in days: the untagged section and the top-post list both
#: cover it, so the digest has one window rather than one per section (PLAN, § From data to
#: insight: "three or more distinct people are discussing within the window").
WINDOW_DAYS: Final = 7

#: The trailing baseline the rising-phrases section compares the window against.
BASELINE_WEEKS: Final = 4

#: Distinct people talking before an untagged post is worth surfacing.
MIN_DISTINCT_AUTHORS: Final = 3

#: How many posts each ranked list shows. A digest is read, not paged.
TOP_POSTS: Final = 10

#: ``runs.settings_fingerprint`` is nullable: a row planted before the fingerprint existed,
#: or stamped by another run's stale sweep, carries none. The model requires a non-empty
#: string, so the digest says the fingerprint was not recorded instead of inventing one.
UNRECORDED_FINGERPRINT: Final = "not recorded"

#: Printed for the side of a settings change where the key did not exist at all, so a key
#: added or removed between two runs reads as what it is rather than as a value of "null".
SETTING_ABSENT: Final = "(not set)"

#: "No upper bound" for :func:`repo.run_for_window`, so "the newest finished run" is the same
#: query as "the run of one day" rather than a second spelling of the same filter. Epoch
#: seconds do not reach it.
_ANY_TIME_AFTER: Final = 1 << 62


class NoRunForDateError(Exception):
    """No finished run started on the local day a report was asked for.

    Carries the conventional suffix ruff's ``N818`` requires; the plan and the route both
    name it ``NoRunForDate``, and the alias below keeps that name importable -- the same
    shape ``settings.DataDirRefused`` uses, and not a ``noqa``, whose ceiling has no slack.
    """


NoRunForDate = NoRunForDateError


@dataclass(frozen=True, slots=True)
class _Window:
    """The one place the digest's time windows are computed, so the sections agree."""

    #: End of the run: every window is measured back from the moment the data was current,
    #: not from "now", so a digest read a week later says the same thing it said on the day.
    at: int

    @property
    def since(self) -> int:
        return self.at - WINDOW_DAYS * 86_400

    @property
    def baseline_since(self) -> int:
        return self.at - BASELINE_WEEKS * 7 * 86_400


def _local_day(report_date: date, zone_name: str) -> tuple[int, int]:
    """``[start, end)`` in epoch seconds for one local calendar day.

    "Daily" is local by decision (``DigestModel.display_timezone``), and the two ends are
    built from two local midnights rather than by adding 86,400 seconds, so a day that is
    23 or 25 hours long across a DST change is still exactly one day.
    """
    zone = ZoneInfo(zone_name)
    start = datetime.combine(report_date, time.min, tzinfo=zone)
    end = datetime.combine(report_date + timedelta(days=1), time.min, tzinfo=zone)
    return int(start.timestamp()), int(end.timestamp())


def _flatten(value: object, prefix: str = "") -> dict[str, str]:
    """A resolved settings mapping as ``dotted.key -> rendered value``.

    A nested section is not itself a setting and a list-valued setting (the revisit ladder)
    is one setting, not one per element: a leaf is anything that is not a mapping. The value
    is rendered with ``json.dumps`` rather than ``str``, so a list, a bool and a null read
    as the configuration file writes them rather than as Python spells them.
    """
    if isinstance(value, dict):
        flat: dict[str, str] = {}
        for key, item in value.items():
            flat.update(_flatten(item, f"{prefix}{key}."))
        return flat
    return {prefix.rstrip("."): json.dumps(value, sort_keys=True)}


def _leaves(value: object) -> int:
    """How many settings a resolved settings mapping holds: its leaf values."""
    return len(_flatten(value))


def _settings_changes(
    previous: str | None, current: str | None
) -> tuple[list[SettingChange] | None, int]:
    """The keys whose value differs between two runs' recorded settings, and how many
    settings the comparison covered.

    ``(None, 0)`` when either side did not record its settings -- a row written before
    revision 0005, or one a stale sweep stamped -- because "not recorded" is not "nothing
    changed", and an empty list beside two different fingerprints would be a lie the digest
    told with a straight face.

    The denominator is the keys the **two** rows between them recorded, not the count of
    today's settings: a key added or removed between the runs is a change, and counting it
    against a population it is not in would put the numerator above the denominator.
    """
    if previous is None or current is None:
        return None, 0
    try:
        before, after = json.loads(previous), json.loads(current)
    except json.JSONDecodeError:
        return None, 0
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None, 0
    flat_before, flat_after = _flatten(before), _flatten(after)
    keys = sorted(set(flat_before) | set(flat_after))
    changes = [
        SettingChange(
            key=key,
            previous=flat_before.get(key, SETTING_ABSENT),
            current=flat_after.get(key, SETTING_ABSENT),
        )
        for key in keys
        if flat_before.get(key, SETTING_ABSENT) != flat_after.get(key, SETTING_ABSENT)
    ]
    return changes, len(keys)


def latest_report_date(engine: Engine, *, settings: Settings) -> date | None:
    """The local date of the newest finished run, or ``None`` when none has finished.

    What ``/reports`` redirects to and what the CLI's ``report`` will default to at M1d.
    """
    with engine.connect() as conn:
        run = repo.run_for_window(conn, start_utc=0, end_utc=_ANY_TIME_AFTER)
    if run is None:
        return None
    started = run.started_at if run.started_at is not None else run.created_at
    return datetime.fromtimestamp(started, tz=ZoneInfo(settings.static.display_timezone)).date()


def assemble_digest(
    engine: Engine,
    *,
    settings: Settings,
    report_date: date,
    clock: Clock | None = None,
) -> DigestModel:
    """Build the digest for one local day from the database.

    ``clock`` supplies ``generated_at`` only -- the moment the reader is looking at, as
    opposed to the moment the run finished, which every window is measured from. It is a
    collaborator like any other and is injected in tests; the route passes the system clock.

    Raises :class:`NoRunForDateError` when no finished run of kind ``run`` started that day.
    """
    zone_name = settings.static.display_timezone
    start_utc, end_utc = _local_day(report_date, zone_name)
    generated_at = (clock if clock is not None else SystemClock()).now()
    with engine.connect() as conn:
        run = repo.run_for_window(conn, start_utc=start_utc, end_utc=end_utc)
        if run is None:
            msg = f"no finished run started on {report_date.isoformat()} ({zone_name})"
            raise NoRunForDateError(msg)
        return _model(
            conn,
            line=runs_view.line_for(run),
            settings=settings,
            report_date=report_date,
            generated_at=generated_at,
        )


def _model(
    conn: Connection,
    *,
    line: runs_view.RunLine,
    settings: Settings,
    report_date: date,
    generated_at: int,
) -> DigestModel:
    run = line.run
    outcomes = repo.source_outcomes(conn, run_pks=[run.pk]).get(run.pk, {})
    window = _Window(at=run.finished_at if run.finished_at is not None else run.created_at)
    return DigestModel(
        report_date=report_date,
        display_timezone=settings.static.display_timezone,
        generated_at=generated_at,
        summary=_summary(conn, line=line, settings=settings, outcomes=outcomes),
        workspaces=_workspace_sections(conn, outcomes=outcomes, window=window),
        subreddits=_subreddit_lines(conn, line=line, outcomes=outcomes),
        backlog=_backlog(),
        compliance=_compliance(conn, settings=settings),
        errors=_errors(line),
        warnings=_warnings(line),
        unknown_enums=_unknown_enums(conn, line=line),
    )


def _summary(
    conn: Connection,
    *,
    line: runs_view.RunLine,
    settings: Settings,
    outcomes: dict[int, repo.SweepProgress],
) -> RunSummary:
    """The run's own numbers, each against the population the run actually measured."""
    run = line.run
    counters = line.counters
    items_seen = sum(progress.items_seen for progress in outcomes.values())
    started_at = run.started_at if run.started_at is not None else run.created_at
    previous = repo.recent_runs(conn, limit=1, before_pk=run.pk, kind=run.kind)
    changes, changed_of = (
        _settings_changes(previous[0].settings_json, run.settings_json) if previous else ([], 0)
    )
    return RunSummary(
        run_id=run.pk,
        status=RunStatus(run.status),
        trigger=run.trigger,
        started_at=started_at,
        finished_at=run.finished_at if run.finished_at is not None else started_at,
        api_requests=Count(
            n=run.api_requests,
            of=line.budget_limit if line.budget_limit is not None else 0,
            population="budgeted requests",
        ),
        posts_new=Count(n=counters.posts_new, of=items_seen, population="items seen"),
        posts_updated=Count(n=counters.posts_updated, of=items_seen, population="items seen"),
        # No tree is fetched before M1b, so no comment was seen to be new out of: 0 of 0 says
        # the stage did not run, where "0 of <posts>" would imply a tree was read.
        comments_new=Count(n=counters.comments_new, of=0, population="comments seen"),
        settings_fingerprint=run.settings_fingerprint or UNRECORDED_FINGERPRINT,
        previous_settings_fingerprint=previous[0].settings_fingerprint if previous else None,
        # The denominator is the settings the two rows recorded where both did, and today's
        # count where they did not: on a first run there is nothing to compare with, and
        # the population the reader can still be told about is the one in force now.
        settings_total=max(changed_of or _leaves(non_secret_settings(settings)), 1),
        settings_changes=changes,
    )


def _workspace_sections(
    conn: Connection, *, outcomes: dict[int, repo.SweepProgress], window: _Window
) -> list[WorkspaceSection]:
    """One section per workspace, each with its share of the run's new posts.

    A workspace's share is summed over the sources the freshness population holds for it, so
    a source muted by hand after the run (``enabled=0`` with ``status='ok'``, the one row
    that population drops) leaves its posts in the run's total but in no workspace's share.
    That reads as ``n of m`` with ``n`` short, which is the honest shape; inventing a
    workspace for an orphaned source would not be.
    """
    run_new_total = sum(progress.new_items for progress in outcomes.values())
    sections: list[WorkspaceSection] = []
    for workspace_pk, slug, name in repo.workspaces(conn):
        here = {row.pk for row in repo.all_sources_for_freshness(conn, workspace_pk)}
        new_here = sum(progress.new_items for pk, progress in outcomes.items() if pk in here)
        sections.append(
            _workspace_section(
                conn,
                (workspace_pk, slug, name),
                new_posts=Count(n=new_here, of=run_new_total, population="new posts this run"),
                window=window,
            )
        )
    return sections


def _workspace_section(
    conn: Connection,
    workspace: tuple[int, str, str],
    *,
    new_posts: Count,
    window: _Window,
) -> WorkspaceSection:
    """One workspace's window, ranked once and measured from what the ranking returned.

    ``workspace`` is the ``(pk, slug, name)`` triple :func:`repo.workspaces` returns, passed
    whole rather than unpacked into three parameters: it is one thing, and the identity and
    its two labels cannot be mismatched at a call site if they never travel apart.

    The ranked read is sized by :func:`repo.posts_in_window` so its cap can never bind, and
    every denominator below is ``len(ranked)`` rather than the count -- the population shown
    and the population counted are then the same list, which is what "show the denominator"
    asks for.
    """
    workspace_pk, slug, name = workspace
    population = repo.posts_in_window(
        conn, workspace_pk=workspace_pk, since_created_utc=window.since
    )
    ranked = repo.ranked_posts(
        conn,
        workspace_pk=workspace_pk,
        since_created_utc=window.since,
        limit=max(population, 1),
    )
    # No theme exists, so every post in the window is untagged; when tagging lands this
    # becomes the posts no theme matched and the denominator moves with it.
    qualifying = [post for post in ranked if post.distinct_author_count >= MIN_DISTINCT_AUTHORS]
    return WorkspaceSection(
        name=name,
        slug=slug,
        window_days=WINDOW_DAYS,
        new_posts=new_posts,
        top_posts=ranked[:TOP_POSTS],
        themes=[],
        untagged=UntaggedSection(
            window_days=WINDOW_DAYS,
            min_distinct_authors=MIN_DISTINCT_AUTHORS,
            qualifying=Count(
                n=len(qualifying),
                of=len(ranked),
                population=f"untagged posts in the last {WINDOW_DAYS} days",
            ),
            posts=qualifying[:TOP_POSTS],
        ),
        rising_phrases=RisingPhrasesSection(
            window_days=WINDOW_DAYS,
            baseline_weeks=BASELINE_WEEKS,
            titles_now=len(ranked),
            titles_baseline=repo.posts_in_window(
                conn, workspace_pk=workspace_pk, since_created_utc=window.baseline_since
            ),
            # The phrase extractor is M1d; the two populations above are counted for real, so
            # only this list changes when it lands.
            phrases=[],
        ),
    )


def _subreddit_lines(
    conn: Connection, *, line: runs_view.RunLine, outcomes: dict[int, repo.SweepProgress]
) -> list[SubredditLine]:
    """Every source in the freshness population, with what this run did to it.

    The population is ``all_sources_for_freshness``, the same one the freshness invariant
    judges, so the digest's "n of m swept without error" and the run's own warning cannot
    disagree about how many sources there are.
    """
    workspace_pk = repo.default_workspace_pk(conn)
    sources = repo.all_sources_for_freshness(conn, workspace_pk)
    window = repo.recent_sweeping_runs(conn, current_run_pk=line.run.pk, limit=STALE_AFTER_RUNS + 1)
    history = repo.source_outcomes(conn, run_pks=window)
    return [
        _subreddit_line(
            source,
            progress=outcomes.get(source.pk, _NOT_SWEPT),
            runs_since_fetched=_runs_since_fetched(history, window, source.pk),
        )
        for source in sources
    ]


def _subreddit_line(
    source: repo.SubredditRow, *, progress: repo.SweepProgress, runs_since_fetched: int
) -> SubredditLine:
    """One source's row: its own health from ``subreddits``, this run's work from the join.

    ``last_error`` is **this run's** per-source error rather than the source's standing one,
    because the digest reports a run: a source that failed a fortnight ago and has been fine
    since must not carry that message into today's report.
    """
    return SubredditLine(
        name=source.display_name,
        status=SubredditStatus(source.status),
        enabled=source.enabled,
        pages=progress.pages,
        items_seen=progress.items_seen,
        new_posts=progress.new_items,
        updated_posts=progress.updated_items,
        stop_reason=progress.stop_reason,
        last_error=progress.error,
        consecutive_failures=source.consecutive_failures,
        runs_since_fetched=runs_since_fetched,
        gap_suspected_at=source.gap_suspected_at,
    )


_NOT_SWEPT: Final = repo.SweepProgress(
    pages=0, items_seen=0, new_items=0, updated_items=0, stop_reason=None, error=None
)


def _runs_since_fetched(
    history: dict[int, dict[int, repo.SweepProgress]], window: list[int], subreddit_pk: int
) -> int:
    """How many sweeping runs back the source was last fetched, counting from this one.

    ``window`` is newest first and ends at the digest's own run. "Fetched" is the invariant's
    own predicate, imported rather than restated, so a source ``per_source_freshness`` calls
    fetched can never read as never fetched in the digest of the same run. The answer is
    capped at the window's length: the digest claims "at least this stale", and the window is
    one run longer than ``STALE_AFTER_RUNS`` so it can cross the threshold.
    """
    for distance, run_pk in enumerate(window):
        progress = history.get(run_pk, {}).get(subreddit_pk)
        if progress is not None and progress.stop_reason in SUCCESSFUL_STOP_REASONS:
            return distance
    return len(window)


def _backlog() -> Backlog:
    """The comment-tree backlog, which no stage fills before M1b.

    ``0 of 0`` twice, deliberately: no tree was fetched, so no post was due *for a tree* and
    no tree could be left with unexpanded stubs. A denominator taken from the stored posts
    would imply a harvest that never ran.
    """
    return Backlog(
        due_posts_harvested=Count(n=0, of=0, population="posts due for a comment tree"),
        trees_with_more_skipped=Count(n=0, of=0, population="trees fetched this run"),
    )


def _compliance(conn: Connection, *, settings: Settings) -> Compliance:
    """The reconcile and scrub picture, which is "nothing has run yet" until M1c.

    The strictest tier is the one reported, so the section cannot read as on time by being
    measured against the most generous limit; with no reconcile ever completed the age is
    ``None`` and the model's ``overdue`` is true, which is the truth.
    """
    live = repo.live_counts(conn)
    stored = live["posts_live"] + live["comments_live"]
    return Compliance(
        last_reconcile_age_hours=None,
        reconcile_tier="items 30 days old or younger",
        tier_max_age_hours=settings.static.reconcile.tier_max_age_hours.under_30d,
        reconciled=Count(n=0, of=stored, population="stored items"),
        tier_fallback=False,
        scrubbed_posts=Count(n=0, of=0, population="posts checked this run"),
        scrubbed_comments=Count(n=0, of=0, population="comments checked this run"),
        account_deletions=Count(n=0, of=0, population="authors seen this run"),
    )


def _errors(line: runs_view.RunLine) -> list[Problem]:
    problems = [
        Problem(where=violation.invariant, message=violation.detail or "(no detail recorded)")
        for violation in line.failures
    ]
    if line.run.error:
        problems.append(Problem(where=line.run.kind, message=line.run.error))
    return problems


def _warnings(line: runs_view.RunLine) -> list[Problem]:
    """Every warning the run raised, named where the row kept its name.

    Both named sources arrive through ``line.warnings``: an invariant's ``WARNING`` verdict
    from ``violations_json`` and a ``RunContext.warn`` warning from ``warnings_json``. On a
    row written before revision 0005 the second is a count alone, and each of those appears
    as its own unnamed problem, so the digest's "N warnings this run" is still the number
    the run recorded and the missing names are visible rather than a silent zero.
    """
    problems = [
        Problem(where=violation.invariant, message=violation.detail or "(no detail recorded)")
        for violation in line.warnings
    ]
    total = line.unrecorded_warnings
    problems.extend(
        Problem(
            where=f"run warning {number} of {total}",
            message="recorded by the run; no column keeps a warning's name or detail",
        )
        for number in range(1, total + 1)
    )
    return problems


def _unknown_enums(conn: Connection, *, line: runs_view.RunLine) -> UnknownEnumSection:
    """Upstream enum values this run stored raw, counted per ``(field, value)``.

    Read back from the rows the run wrote, bounded at both ends by the run's own clock, so a
    report of an older run cannot count what a later run wrote. The run row keeps only the
    total, which is why the breakdown is read rather than taken from ``counters_json``.
    """
    run = line.run
    started_at = run.started_at if run.started_at is not None else run.created_at
    occurrences = repo.unknown_enum_occurrences(
        conn,
        since=started_at,
        until=run.finished_at,
        known={field: KNOWN_VALUES.known(field) for field in repo.UNKNOWN_ENUM_FIELDS},
    )
    counted: dict[tuple[str, str], int] = {}
    for occurrence in occurrences:
        field, _, value = occurrence.split("|", 1)[1].partition("=")
        counted[field, value] = counted.get((field, value), 0) + 1
    rows_written = line.counters.posts_new + line.counters.posts_updated
    return UnknownEnumSection(
        rows_written=rows_written,
        values=[
            UnknownEnum(field=field, value=value, occurrences=occurrences_of)
            for (field, value), occurrences_of in sorted(counted.items())
        ],
    )
