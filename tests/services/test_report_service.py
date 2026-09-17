"""DG-01's service half and DB-63's service half: the digest assembled from the database,
and the parsed run view both the Runs page and the digest read.

``services/runs_view.py`` is tested here rather than in a file of its own because it is the
read half of the same slice: :func:`threaddigest.services.report.assemble_digest` parses
every run row through it, so a change that breaks one breaks the other, and one file is
where a reviewer can see that.

Every test runs against a temp database at head (``tests/services/conftest.py``) and plants
its rows through ``db/repo.py`` -- the same functions the collector writes through -- so a
row shape the production path cannot produce is never asserted on.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any

import pytest
from sqlalchemy import Engine

from threaddigest.adapters.clock import FakeClock
from threaddigest.core.digest import (
    SettingChange,
    SubredditStatus,
    render_html,
    render_markdown,
)
from threaddigest.core.models import PostRow
from threaddigest.core.retry import RunStatus
from threaddigest.db import repo
from threaddigest.db.ownership import IngestPath
from threaddigest.services import invariants, report, runs_view
from threaddigest.services.runs import Counters
from threaddigest.settings import Settings, non_secret_settings

#: 2026-09-13 06:30 and 06:41 UTC: a run inside one local day, on a date the digest's own
#: golden also uses, so a failure is easy to line up against ``tests/unit/test_digest.py``.
STARTED = int(datetime(2026, 9, 13, 6, 30, tzinfo=UTC).timestamp())
FINISHED = int(datetime(2026, 9, 13, 6, 41, tzinfo=UTC).timestamp())
REPORT_DATE = date(2026, 9, 13)

PlantPost = Callable[..., None]
PlantFinishedRun = Callable[..., repo.RunDisplay]

#: The columns a normalized post carries that this file never varies.
_POST_FIELDS: dict[str, Any] = {
    "subreddit": "premiere",
    "subreddit_id": "t5_2s9fq",
    "author": "editorguy",
    "author_fullname": "t2_abcd12",
    "author_flair_text": None,
    "author_is_bot": False,
    "selftext": "",
    "selftext_html": "",
    "url": "https://example.com/x",
    "domain": "example.com",
    "edited_utc": None,
    "score": 0,
    "upvote_ratio": 0.9,
    "num_comments": 0,
    "link_flair_text": None,
    "over_18": False,
    "spoiler": False,
    "is_self": True,
    "is_video": False,
    "is_gallery": False,
    "post_hint": None,
    "locked": False,
    "stickied": False,
    "archived": False,
    "distinguished": None,
    "crosspost_parent": None,
    "num_crossposts": 0,
    "removed_by_category": None,
    "source": "subreddit_new",
}


@pytest.fixture
def clock_at_report() -> FakeClock:
    """A clock a few minutes after the run, so ``generated_at`` is deterministic."""
    return FakeClock(start=FINISHED + 600)


@pytest.fixture
def plant_post(engine: Engine) -> PlantPost:
    """Write one live post through the collector's own upsert, never a raw ``INSERT``."""

    def _plant(reddit_id: str, *, subreddit_pk: int, **overrides: Any) -> None:
        fields: dict[str, Any] = {
            **_POST_FIELDS,
            "reddit_id": reddit_id,
            "fullname": f"t3_{reddit_id}",
            "title": f"title {reddit_id}",
            "permalink": f"/r/premiere/comments/{reddit_id}/",
            "created_utc": FINISHED - 3600,
        }
        fields.update({key: overrides.pop(key) for key in tuple(overrides) if key in fields})
        row = PostRow(**fields)
        write = repo.PostWrite(
            row=row,
            subreddit_pk=subreddit_pk,
            first_seen_at=STARTED,
            last_fetched_at=overrides.pop("last_fetched_at", STARTED + 10),
            next_check_at=STARTED + 86_400,
            check_stage=0,
            content_state="live",
            author_state="known",
            misses=0,
            raw_json="{}",
        )
        assert not overrides, f"unused overrides: {overrides}"
        with engine.begin() as conn:
            repo.upsert_posts(conn, [write], path=IngestPath.SUBREDDIT_NEW)

    return _plant


@pytest.fixture
def plant_finished_run(engine: Engine) -> PlantFinishedRun:
    """A finished ``run`` row with its counters, budget, violations and per-source outcomes."""

    def _plant(
        *,
        counters: Counters | None = None,
        outcomes: dict[int, repo.SweepProgress] | None = None,
        status: str = "ok",
        trigger: str = "schedule",
        started_at: int = STARTED,
        finished_at: int = FINISHED,
        api_requests: int = 312,
        budget_limit: int | None = 1500,
        violations_json: str | None = "[]",
        error: str | None = None,
        settings_fingerprint: str | None = "9f2c" * 4,
        settings_json: str | None = None,
        warnings_json: str | None = None,
        kind: str = "run",
    ) -> repo.RunDisplay:
        options_json = (
            None
            if budget_limit is None
            else json.dumps({"gateway": "fake", "budget": {"limit": budget_limit}})
        )
        with engine.begin() as conn:
            run_pk = repo.insert_run(
                conn,
                repo.RunInsert(
                    kind=kind,
                    trigger=trigger,
                    status="running",
                    created_at=started_at,
                    started_at=started_at,
                    pid=None,
                    stage=None,
                    options_json=options_json,
                    app_version="0.1.0",
                    praw_version=None,
                    schema_rev="0004",
                    settings_fingerprint=settings_fingerprint,
                    log_path=None,
                ),
            )
            if settings_json is not None:
                repo.record_run_settings(conn, run_pk=run_pk, settings_json=settings_json)
            for subreddit_pk, progress in (outcomes or {}).items():
                repo.upsert_run_subreddit(
                    conn, run_pk=run_pk, subreddit_pk=subreddit_pk, progress=progress
                )
            repo.finish_run(
                conn,
                run_pk=run_pk,
                status=status,
                finished_at=finished_at,
                counters_json=(counters or Counters()).to_json(),
                api_requests=api_requests,
                error=error,
                violations_json=violations_json,
                warnings_json=warnings_json,
            )
        with engine.connect() as conn:
            row = repo.run_display(conn, run_pk=run_pk)
        assert row is not None
        return row

    return _plant


def _leaf_count(mapping: dict[str, Any]) -> int:
    """Leaf values in a nested settings mapping, counted iteratively.

    Written with a stack rather than by calling the assembler's own helper: a test that
    reuses the implementation proves only that the implementation equals itself.
    """
    total = 0
    stack: list[Any] = list(mapping.values())
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            stack.extend(value.values())
        else:
            total += 1
    return total


def _swept(**overrides: Any) -> repo.SweepProgress:
    values: dict[str, Any] = {
        "pages": 3,
        "items_seen": 60,
        "new_items": 12,
        "updated_items": 40,
        "stop_reason": "exhausted",
        "error": None,
    }
    values.update(overrides)
    return repo.SweepProgress(**values)


# --- runs_view: one row parsed once ---------------------------------------------------------


def test_run_line_parses_the_counters_the_budget_and_the_violations(
    plant_finished_run: PlantFinishedRun,
) -> None:
    run = plant_finished_run(
        counters=Counters(posts_new=12, posts_updated=40, warnings=2),
        status="partial",
        violations_json=invariants.to_json(
            [
                invariants.Violation(
                    invariant="per_source_freshness",
                    severity=invariants.Severity.WARNING,
                    detail="r/editors not fetched in the last 2 sweeping runs",
                ),
                invariants.Violation(
                    invariant="counters_equal_table_deltas",
                    severity=invariants.Severity.FAILURE,
                    detail="posts delta 13 != posts_new 12",
                ),
            ]
        ),
    )

    line = runs_view.line_for(run)

    assert line.counters.posts_new == 12
    assert line.budget_limit == 1500
    assert line.duration_seconds == FINISHED - STARTED
    assert line.invariants_ran is True
    assert [p.invariant for p in line.warnings] == ["per_source_freshness"]
    assert [p.invariant for p in line.failures] == ["counters_equal_table_deltas"]


def test_run_line_says_how_many_warnings_a_row_from_before_0005_could_not_name(
    plant_finished_run: PlantFinishedRun,
) -> None:
    """``ok`` means zero warnings, so an amber run owes the page a reason. On a row written
    before revision 0005 only the count of a ``RunContext.warn`` warning reached the
    database, so the count is what is shown -- never a silent zero, and never a name the row
    does not hold."""
    run = plant_finished_run(counters=Counters(warnings=3), status="partial", warnings_json=None)

    line = runs_view.line_for(run)

    assert line.warnings == (), "no invariant complained; the three warnings are unnamed"
    assert line.unrecorded_warnings == 3


def test_run_line_names_the_warnings_the_row_recorded(
    plant_finished_run: PlantFinishedRun,
) -> None:
    """Revision 0005: a ``RunContext.warn`` warning arrives as a named problem beside the
    invariants' own, and nothing is left over for the page to report as a number."""
    run = plant_finished_run(
        counters=Counters(warnings=2),
        status="partial",
        warnings_json=json.dumps(
            [
                {"name": "budget_exhausted", "detail": "r/premiere: stopped after 3 pages"},
                {"name": "cursor_stalled", "detail": "r/editors: after did not advance"},
            ]
        ),
    )

    line = runs_view.line_for(run)

    assert [(p.invariant, p.detail) for p in line.warnings] == [
        ("budget_exhausted", "r/premiere: stopped after 3 pages"),
        ("cursor_stalled", "r/editors: after did not advance"),
    ]
    assert line.failures == ()
    assert line.unrecorded_warnings == 0


def test_run_line_reports_an_unreadable_warnings_column_instead_of_losing_it(
    plant_finished_run: PlantFinishedRun,
) -> None:
    """The same treatment ``counters_json`` and ``violations_json`` already get: a row that
    will not parse must not take the history page down, and must not read as "no warning"
    either. The count stays the honest denominator, so the page still says two are missing.
    """
    run = plant_finished_run(
        counters=Counters(warnings=2), status="partial", warnings_json="{not json"
    )

    line = runs_view.line_for(run)

    assert [p.invariant for p in line.failures] == [runs_view.UNREADABLE]
    assert line.unrecorded_warnings == 2


def test_run_line_separates_invariants_that_did_not_run_from_a_clean_verdict(
    plant_finished_run: PlantFinishedRun,
) -> None:
    """``[]`` means they ran and found nothing; NULL means they never ran (§14.1)."""
    clean = runs_view.line_for(plant_finished_run(violations_json="[]"))
    skipped = runs_view.line_for(plant_finished_run(violations_json=None))

    assert (clean.invariants_ran, clean.problems) == (True, ())
    assert (skipped.invariants_ran, skipped.problems) == (False, ())


def test_run_line_records_an_unreadable_json_column_instead_of_raising(
    engine: Engine, plant_finished_run: PlantFinishedRun
) -> None:
    """A corrupted column on one historical row must not take the history page down, and a
    zero counter would be worse than the page failing: it is recorded as a failure."""
    run = plant_finished_run()
    broken = replace(run, counters_json="{not json", violations_json="{not json")

    line = runs_view.line_for(broken)

    assert line.counters == Counters(), "nothing is invented from an unreadable column"
    assert [p.invariant for p in line.problems] == [runs_view.UNREADABLE] * 2
    assert all(p.severity == runs_view.SEVERITY_FAILURE for p in line.problems)


def test_run_line_ignores_a_budget_it_cannot_read(
    plant_finished_run: PlantFinishedRun,
) -> None:
    """A ``skipped_locked`` row has no options at all; the denominator is then absent, not 0."""
    assert runs_view.line_for(plant_finished_run(budget_limit=None)).budget_limit is None


def test_recent_pages_the_history_newest_first(
    engine: Engine, plant_finished_run: PlantFinishedRun
) -> None:
    older = plant_finished_run(started_at=STARTED - 100, finished_at=FINISHED - 100)
    newer = plant_finished_run()

    page_one = runs_view.recent(engine, limit=1)
    page_two = runs_view.recent(engine, limit=1, before_pk=page_one[0].run.pk)

    assert [line.run.pk for line in page_one] == [newer.pk]
    assert [line.run.pk for line in page_two] == [older.pk]


def test_one_returns_the_run_with_its_per_source_rows_named_and_ordered(
    engine: Engine, add_source: Any, plant_finished_run: PlantFinishedRun
) -> None:
    zeta = add_source("zeta").pk
    alpha = add_source("alpha").pk
    run = plant_finished_run(
        outcomes={zeta: _swept(new_items=1), alpha: _swept(new_items=2, stop_reason="cap")}
    )

    detail = runs_view.one(engine, run_pk=run.pk)

    assert detail is not None
    assert [source.name for source in detail.sources] == ["alpha", "zeta"]
    assert detail.sources[0].progress.stop_reason == "cap"
    assert detail.line.run.pk == run.pk


def test_one_is_none_for_a_run_that_does_not_exist(engine: Engine) -> None:
    assert runs_view.one(engine, run_pk=999_999) is None


# --- report: the digest assembled from the row ----------------------------------------------


def test_assemble_digest_takes_its_numbers_from_the_run_row(
    engine: Engine,
    settings: Settings,
    add_source: Any,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    premiere = add_source("premiere").pk
    plant_finished_run(
        counters=Counters(posts_new=12, posts_updated=40, api_requests=312),
        outcomes={premiere: _swept()},
        trigger="schedule",
        api_requests=312,
    )

    model = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    )

    summary = model.summary
    assert model.report_date == REPORT_DATE
    assert model.generated_at == FINISHED + 600
    assert summary.status is RunStatus.OK
    assert summary.trigger == "schedule"
    assert summary.duration_seconds == FINISHED - STARTED
    assert (summary.api_requests.n, summary.api_requests.of) == (312, 1500)
    assert (summary.posts_new.n, summary.posts_new.of) == (12, 60), "of = items seen this run"
    assert (summary.posts_updated.n, summary.posts_updated.of) == (40, 60)


def test_assemble_digest_counts_the_settings_the_fingerprint_covers(
    engine: Engine,
    settings: Settings,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    """The denominator of "settings changed" is the settings the fingerprint hashes, counted
    from the one mapping that defines them, so the two can never disagree."""
    plant_finished_run()

    summary = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    ).summary

    assert summary.settings_total == _leaf_count(non_secret_settings(settings))
    assert summary.settings_changes == [], "only the fingerprint is stored, never the settings"
    assert summary.previous_settings_fingerprint is None, "nothing ran before it"


#: Two runs' worth of recorded settings, differing in one key. Written as literals rather
#: than built from ``Settings``, so the test states the change it expects to be named.
_SETTINGS_BEFORE = '{"budget":{"per_run_requests":1500},"display_timezone":"UTC"}'
_SETTINGS_AFTER = '{"budget":{"per_run_requests":500},"display_timezone":"UTC"}'


def test_assemble_digest_names_the_settings_keys_that_changed(
    engine: Engine,
    settings: Settings,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    """Revision 0005: with both runs' settings on their rows, the digest names the key that
    changed and both of its values, instead of reporting that the fingerprint moved.

    The denominator is the settings the two runs between them recorded, so a key added or
    removed between runs cannot make the numerator exceed it.
    """
    plant_finished_run(
        started_at=STARTED - 3600,
        finished_at=FINISHED - 3600,
        settings_fingerprint="0a1b" * 4,
        settings_json=_SETTINGS_BEFORE,
    )
    plant_finished_run(settings_fingerprint="9f2c" * 4, settings_json=_SETTINGS_AFTER)

    summary = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    ).summary

    assert summary.settings_changes == [
        SettingChange(key="budget.per_run_requests", previous="1500", current="500")
    ]
    assert str(summary.settings_changed) == "1 of 2 non-secret settings (50%)"


def test_a_settings_key_added_or_removed_between_runs_is_named_on_both_sides(
    engine: Engine,
    settings: Settings,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    """A key only one of the two runs recorded is a change, and says which side lacked it."""
    plant_finished_run(
        started_at=STARTED - 3600,
        finished_at=FINISHED - 3600,
        settings_fingerprint="0a1b" * 4,
        settings_json='{"kept":1,"dropped":"x"}',
    )
    plant_finished_run(settings_fingerprint="9f2c" * 4, settings_json='{"added":2,"kept":1}')

    summary = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    ).summary

    assert summary.settings_changes == [
        SettingChange(key="added", previous=report.SETTING_ABSENT, current="2"),
        SettingChange(key="dropped", previous='"x"', current=report.SETTING_ABSENT),
    ]
    assert str(summary.settings_changed) == "2 of 3 non-secret settings (67%)"


def test_a_run_whose_settings_were_not_recorded_says_so_rather_than_nothing_changed(
    engine: Engine,
    settings: Settings,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    """A row written before revision 0005 has NULL settings, and "not recorded" is not
    "nothing changed": an empty list beside two different fingerprints would be a lie."""
    plant_finished_run(
        started_at=STARTED - 3600,
        finished_at=FINISHED - 3600,
        settings_fingerprint="0a1b" * 4,
        settings_json=None,
    )
    plant_finished_run(settings_fingerprint="9f2c" * 4, settings_json=_SETTINGS_AFTER)

    summary = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    ).summary

    assert summary.settings_changes is None
    assert summary.previous_settings_fingerprint == "0a1b" * 4, "the two rows still differ"


def test_assemble_digest_compares_against_the_previous_run_of_the_same_kind(
    engine: Engine,
    settings: Settings,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    plant_finished_run(
        started_at=STARTED - 3600, finished_at=FINISHED - 3600, settings_fingerprint="0a1b" * 4
    )
    plant_finished_run(
        kind="doctor", started_at=STARTED - 60, finished_at=STARTED - 30, settings_fingerprint="x"
    )
    plant_finished_run(settings_fingerprint="9f2c" * 4)

    summary = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    ).summary

    assert summary.settings_fingerprint == "9f2c" * 4
    assert summary.previous_settings_fingerprint == "0a1b" * 4, "the previous run, not the doctor"


def test_assemble_digest_names_the_run_whose_local_day_was_asked_for(
    engine: Engine,
    settings: Settings,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    """A run belongs to the day it started, in the display timezone, and the newest finished
    run of that day is the one reported."""
    plant_finished_run(started_at=STARTED - 86_400, finished_at=FINISHED - 86_400)
    morning = plant_finished_run(started_at=STARTED, finished_at=STARTED + 60)
    evening = plant_finished_run(started_at=STARTED + 3600, finished_at=FINISHED + 3600)

    model = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    )

    assert model.summary.run_id == evening.pk
    assert model.summary.run_id != morning.pk
    assert model.display_timezone == settings.static.display_timezone


def test_assemble_digest_refuses_a_date_with_no_finished_run(
    engine: Engine,
    settings: Settings,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    plant_finished_run()

    with pytest.raises(report.NoRunForDate, match="2026-09-14"):
        report.assemble_digest(
            engine, settings=settings, report_date=date(2026, 9, 14), clock=clock_at_report
        )


def test_latest_report_date_is_the_newest_finished_run_and_none_before_the_first(
    engine: Engine, settings: Settings, plant_finished_run: PlantFinishedRun
) -> None:
    assert report.latest_report_date(engine, settings=settings) is None

    plant_finished_run(started_at=STARTED - 86_400, finished_at=FINISHED - 86_400)
    plant_finished_run()

    assert report.latest_report_date(engine, settings=settings) == REPORT_DATE


def test_latest_report_date_ignores_a_run_still_in_flight(
    engine: Engine, settings: Settings, plant_run: Any, plant_finished_run: PlantFinishedRun
) -> None:
    """A run with no terminal status has no counters and no verdict; it is the Runs page's
    business, not a report's."""
    plant_finished_run()
    plant_run(status="running", created_at=FINISHED + 86_400, started_at=FINISHED + 86_400)

    assert report.latest_report_date(engine, settings=settings) == REPORT_DATE


# --- report: how an unbuilt stage is reported ------------------------------------------------


def test_every_source_in_the_freshness_population_gets_a_line(
    engine: Engine,
    settings: Settings,
    add_source: Any,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    premiere = add_source("premiere").pk
    editors = add_source("editors").pk
    plant_finished_run(
        outcomes={
            premiere: _swept(),
            editors: _swept(stop_reason="error", error="403 from Reddit", new_items=0),
        },
        counters=Counters(warnings=1),
        status="partial",
    )

    model = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    )

    lines = {line.name: line for line in model.subreddits}
    assert set(lines) == {"premiere", "editors"}
    assert lines["premiere"].healthy is True
    assert lines["editors"].healthy is False, "stop_reason=error is not healthy"
    assert lines["editors"].last_error == "403 from Reddit"
    assert (lines["premiere"].new.n, lines["premiere"].new.of) == (12, 60)
    assert lines["premiere"].new.population == "items seen"
    assert model.healthy_subreddits.of == 2, "the denominator is every source, not the swept"


def test_a_source_this_run_did_not_fetch_is_counted_stale_against_the_window(
    engine: Engine,
    settings: Settings,
    add_source: Any,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    """``runs_since_fetched`` walks back through the sweeping runs that ended at this one, so
    a digest of an older run is never handed a run that had not happened yet."""
    premiere = add_source("premiere").pk
    editors = add_source("editors").pk
    plant_finished_run(
        outcomes={premiere: _swept(), editors: _swept()},
        started_at=STARTED - 7200,
        finished_at=FINISHED - 7200,
    )
    plant_finished_run(outcomes={premiere: _swept()})

    model = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    )

    lines = {line.name: line for line in model.subreddits}
    assert lines["premiere"].runs_since_fetched == 0
    assert lines["editors"].runs_since_fetched == 1
    assert lines["editors"].stale is False, "one run is under the two-run threshold"
    assert model.stale_subreddits.of == 2


def test_an_unstaged_section_shows_a_zero_against_a_real_denominator(
    engine: Engine,
    settings: Settings,
    add_source: Any,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
    plant_post: PlantPost,
) -> None:
    """The window is real, the thresholds are printed, and the numerators are honest zeros:
    no theme is tagged and no comment is captured, so nothing qualifies."""
    premiere = add_source("premiere").pk
    for number in range(4):
        plant_post(f"p{number}", subreddit_pk=premiere, created_utc=FINISHED - 3600)
    plant_finished_run(outcomes={premiere: _swept()})

    model = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    )

    workspace = model.workspaces[0]
    assert workspace.themes == [], "no theme exists to match against"
    assert workspace.untagged.min_distinct_authors == report.MIN_DISTINCT_AUTHORS
    assert workspace.untagged.qualifying.n == 0, "no comment is captured, so nobody qualifies"
    assert workspace.untagged.qualifying.of == 4, "the window's real size is the denominator"
    assert workspace.untagged.posts == []
    assert workspace.rising_phrases.phrases == [], "the phrase extractor is M1d"
    assert workspace.rising_phrases.titles_now == 4, "its populations are counted for real"
    assert workspace.rising_phrases.titles_baseline >= 4
    assert [post.post_id for post in workspace.top_posts] == ["p0", "p1", "p2", "p3"]
    assert all(post.distinct_author_count == 0 for post in workspace.top_posts)


def test_the_backlog_and_compliance_sections_report_what_the_row_holds(
    engine: Engine,
    settings: Settings,
    add_source: Any,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
    plant_post: PlantPost,
) -> None:
    """No tree was fetched and no reconcile has completed, so the backlog is 0 of 0 -- the
    shape that says a stage did not run -- while compliance counts the stored items it can."""
    premiere = add_source("premiere").pk
    plant_post("stored", subreddit_pk=premiere, created_utc=FINISHED - 60)
    plant_finished_run(outcomes={premiere: _swept()})

    model = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    )

    assert (model.backlog.due_posts_harvested.n, model.backlog.due_posts_harvested.of) == (0, 0)
    assert (model.backlog.trees_with_more_skipped.n, model.backlog.trees_with_more_skipped.of) == (
        0,
        0,
    )
    assert model.compliance.last_reconcile_age_hours is None
    assert model.compliance.overdue is True, "never reconciled is overdue, not on time"
    assert (model.compliance.reconciled.n, model.compliance.reconciled.of) == (0, 1)
    assert (
        model.compliance.tier_max_age_hours
        == settings.static.reconcile.tier_max_age_hours.under_30d
    )


def test_every_warning_and_error_the_row_holds_reaches_the_digest(
    engine: Engine,
    settings: Settings,
    add_source: Any,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    """An invariant's warning names itself; a ``RunContext.warn`` warning survives only as a
    count, so each one is its own unnamed problem and the digest's warning count is the
    number the run recorded rather than the number it can name."""
    premiere = add_source("premiere").pk
    plant_finished_run(
        outcomes={premiere: _swept()},
        counters=Counters(warnings=2),
        status="failed",
        error="the collector lost the database",
        violations_json=invariants.to_json(
            [
                invariants.Violation(
                    invariant="per_source_freshness",
                    severity=invariants.Severity.WARNING,
                    detail="r/editors not fetched in the last 2 sweeping runs",
                ),
                invariants.Violation(
                    invariant="counters_equal_table_deltas",
                    severity=invariants.Severity.FAILURE,
                    detail="posts delta 13 != posts_new 12",
                ),
            ]
        ),
    )

    model = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    )

    assert [problem.where for problem in model.errors] == [
        "counters_equal_table_deltas",
        "run",
    ]
    assert len(model.warnings) == 3, "one named invariant warning plus the two only counted"
    assert model.warnings[0].where == "per_source_freshness"
    assert all("no column keeps" in problem.message for problem in model.warnings[1:])


def test_unknown_enum_values_are_read_back_inside_the_run_s_own_window(
    engine: Engine,
    settings: Settings,
    add_source: Any,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
    plant_post: PlantPost,
) -> None:
    """Only the total reaches ``counters_json``, so the breakdown is read from the rows the
    run wrote -- bounded at both ends, or a later run's rows would land in this report."""
    premiere = add_source("premiere").pk
    plant_post("weird", subreddit_pk=premiere, post_hint="hologram", last_fetched_at=STARTED + 10)
    plant_post(
        "later", subreddit_pk=premiere, post_hint="hologram", last_fetched_at=FINISHED + 10_000
    )
    plant_finished_run(
        outcomes={premiere: _swept()}, counters=Counters(posts_new=12, posts_updated=40)
    )

    section = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    ).unknown_enums

    assert [(v.field, v.value, v.occurrences) for v in section.values] == [
        ("post_hint", "hologram", 1)
    ]
    assert section.rows_written == 52, "new plus updated: the rows the run wrote"
    assert section.count.n == 1, "never a zero while the run counted one"


def test_the_assembled_model_renders_through_both_templates(
    engine: Engine,
    settings: Settings,
    add_source: Any,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
    plant_post: PlantPost,
) -> None:
    """``StrictUndefined``: a field the template names and the assembler forgot fails the
    render rather than printing an empty string, so this is the assembler's shape test."""
    premiere = add_source("premiere").pk
    plant_post("rendered", subreddit_pk=premiere, created_utc=FINISHED - 60)
    plant_finished_run(
        outcomes={premiere: _swept(stop_reason="cap")}, counters=Counters(warnings=1)
    )

    model = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    )
    markdown = render_markdown(model)
    html = render_html(model)

    assert "# Thread Digest for 2026-09-13" in markdown
    assert "0 of 0 posts due for a comment tree" in markdown
    assert "<h1>Thread Digest for 2026-09-13</h1>" in html


def test_an_empty_database_still_has_a_report_shape_once_a_run_has_finished(
    engine: Engine,
    settings: Settings,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    """A run that swept nothing: every count is zero over a zero population, no source line
    exists, and the digest still renders."""
    plant_finished_run(outcomes={}, api_requests=0, budget_limit=1500)

    model = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    )

    assert model.subreddits == []
    assert model.healthy_subreddits.of == 0
    assert model.workspaces[0].untagged.qualifying.of == 0
    assert render_markdown(model)


def test_a_run_row_with_no_fingerprint_says_so_rather_than_inventing_one(
    engine: Engine,
    settings: Settings,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    plant_finished_run(settings_fingerprint=None)

    summary = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    ).summary

    assert summary.settings_fingerprint == report.UNRECORDED_FINGERPRINT


def test_the_subreddit_status_vocabulary_survives_the_trip_to_the_model(
    engine: Engine,
    settings: Settings,
    add_source: Any,
    plant_finished_run: PlantFinishedRun,
    clock_at_report: FakeClock,
) -> None:
    """``subreddits.status`` is stored raw; the model's enum is the same vocabulary, so a
    forbidden source reaches the digest as ``forbidden`` and not as a crash."""
    editors = add_source("editors").pk
    with engine.begin() as conn:
        repo.record_subreddit_failure(
            conn,
            subreddit_pk=editors,
            status="forbidden",
            error="403",
            now=STARTED,
            disable_at=None,
        )
    plant_finished_run(outcomes={editors: _swept(stop_reason="error", error="403")})

    model = report.assemble_digest(
        engine, settings=settings, report_date=REPORT_DATE, clock=clock_at_report
    )

    assert model.subreddits[0].status is SubredditStatus.FORBIDDEN


def test_a_run_still_in_flight_has_no_duration_and_no_counters_yet(
    engine: Engine, plant_run: Any
) -> None:
    """The Runs page shows running rows too: nothing is written to ``counters_json`` until
    the run closes, and a duration that does not exist yet is absent rather than zero."""
    plant_run(status="running", created_at=STARTED, started_at=STARTED, stage="fetch:premiere")

    line = runs_view.recent(engine, limit=1)[0]

    assert line.run.status == "running"
    assert line.run.stage == "fetch:premiere"
    assert line.duration_seconds is None, "an unfinished run has no duration, not a zero one"
    assert line.counters == Counters()
    assert line.problems == (), "a NULL counters column is not a corrupted one"
