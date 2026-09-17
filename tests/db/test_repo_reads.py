"""``db/repo.py``'s reads, with no spec id (design-round5.md §16, §5.3): enabled sources,
the freshness population, prior posts, the known window, table counts, the run queries,
the freshness window and its per-source outcomes, and the three reads the invariants
consume (population floors, normalizer version, unknown enum occurrences).

The display reads at the foot of the file are DB-63: the ``runs`` columns a page shows,
the run behind one local day, the workspace's post window and its denominator, and the
names a per-source row needs. They are the read half of the first web slice
(``services/runs_view.py`` and ``services/report.py``).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from threaddigest.core.models import KNOWN_VALUES, PostRow
from threaddigest.db.ownership import IngestPath
from threaddigest.db.repo import (
    REDDIT_WEB_HOST,
    PostWrite,
    RunInsert,
    SweepProgress,
    all_sources_for_freshness,
    default_workspace_pk,
    due_posts,
    enabled_subreddits,
    finish_run,
    insert_run,
    known_posts_in_window,
    last_successful_run,
    live_counts,
    live_rows_missing,
    posts_in_window,
    prior_posts,
    ranked_posts,
    recent_runs,
    recent_sweeping_runs,
    record_run_settings,
    rows_below_normalizer_version,
    run_display,
    run_for_window,
    running_runs,
    source_outcomes,
    stale_candidates,
    subreddit_names,
    table_counts,
    unknown_enum_occurrences,
    upsert_posts,
    upsert_run_subreddit,
    workspaces,
)
from threaddigest.db.schema import Base

_POST_KWARGS: dict[str, Any] = {
    "subreddit": "premiere",
    "subreddit_id": "t5_2s9fq",
    "author": "editorguy",
    "author_fullname": "t2_abcd12",
    "author_flair_text": None,
    "author_is_bot": False,
    "title": "title",
    "selftext": "",
    "selftext_html": "",
    "url": "https://example.com/x",
    "domain": "example.com",
    "permalink": "/r/premiere/comments/x/",
    "edited_utc": None,
    "score": 1,
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


def _post_write(reddit_id: str, subreddit_pk: int, created_utc: int, *, now: int) -> PostWrite:
    row = PostRow(
        **_POST_KWARGS, reddit_id=reddit_id, fullname=f"t3_{reddit_id}", created_utc=created_utc
    )
    return PostWrite(
        row=row,
        subreddit_pk=subreddit_pk,
        first_seen_at=now,
        last_fetched_at=now,
        next_check_at=now + 86_400,
        check_stage=0,
        content_state="live",
        author_state="known",
        misses=0,
        raw_json="{}",
    )


def _insert_subreddit(engine: Any, workspace_pk: int, name: str, **overrides: Any) -> int:
    subreddits = Base.metadata.tables["subreddits"]
    values = {
        "workspace_pk": workspace_pk,
        "name_lower": name,
        "display_name": name,
        "added_at": 1,
        **overrides,
    }
    with engine.begin() as conn:
        result = conn.execute(subreddits.insert().values(**values))
    return int(result.inserted_primary_key[0])


def _insert_workspace(engine: Any, slug: str) -> int:
    """A second workspace, so a workspace-scoped read can be proved to scope."""
    table = Base.metadata.tables["workspaces"]
    with engine.begin() as conn:
        result = conn.execute(table.insert().values(slug=slug, name=slug.title(), created_at=1))
    return int(result.inserted_primary_key[0])


def _insert_run(engine: Any, **overrides: Any) -> int:
    run = RunInsert(
        kind=overrides.pop("kind", "run"),
        trigger=overrides.pop("trigger", "cli"),
        status=overrides.pop("status", "running"),
        created_at=overrides.pop("created_at", 1),
        started_at=overrides.pop("started_at", None),
        pid=overrides.pop("pid", None),
        stage=overrides.pop("stage", None),
        options_json=overrides.pop("options_json", None),
        app_version=overrides.pop("app_version", None),
        praw_version=overrides.pop("praw_version", None),
        schema_rev=overrides.pop("schema_rev", None),
        settings_fingerprint=overrides.pop("settings_fingerprint", None),
        log_path=overrides.pop("log_path", None),
    )
    settings_json = overrides.pop("settings_json", None)
    assert not overrides, f"unused overrides: {overrides}"
    with engine.begin() as conn:
        run_pk = insert_run(conn, run)
        # The production shape: the settings are a second statement inside the insert's own
        # transaction, because `insert_run` may meet a database below head (repo docstring).
        if settings_json is not None:
            record_run_settings(conn, run_pk=run_pk, settings_json=settings_json)
    return run_pk


def test_default_workspace_pk_returns_the_seeded_workspace(engine: Any, workspace_pk: int) -> None:
    with engine.connect() as conn:
        assert default_workspace_pk(conn) == workspace_pk


def test_enabled_subreddits_orders_by_name_lower_and_excludes_disabled(
    engine: Any, workspace_pk: int
) -> None:
    _insert_subreddit(engine, workspace_pk, "zeta", enabled=True)
    _insert_subreddit(engine, workspace_pk, "alpha", enabled=True)
    _insert_subreddit(engine, workspace_pk, "muted", enabled=False)

    with engine.connect() as conn:
        rows = enabled_subreddits(conn, workspace_pk)

    names = [r.name_lower for r in rows]
    assert names == sorted(names)
    assert "alpha" in names
    assert "zeta" in names
    assert "muted" not in names


def test_all_sources_for_freshness_includes_error_status_sources(
    engine: Any, workspace_pk: int
) -> None:
    """§5.3: a disabled-by-error source stays in the freshness population (ingest B8)."""
    _insert_subreddit(engine, workspace_pk, "healthy", enabled=True, status="ok")
    _insert_subreddit(engine, workspace_pk, "disabled", enabled=False, status="redirect")
    _insert_subreddit(engine, workspace_pk, "muted_but_ok", enabled=False, status="ok")

    with engine.connect() as conn:
        rows = all_sources_for_freshness(conn, workspace_pk)

    names = {r.name_lower for r in rows}
    assert "healthy" in names
    assert "disabled" in names, "disabled by an error status must not leave the population"
    assert "muted_but_ok" not in names, "manually disabled with status=ok is not a source failure"


def test_prior_posts_returns_only_matching_reddit_ids(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    with engine.begin() as conn:
        upsert_posts(
            conn,
            [
                _post_write("known1", subreddit_pk, now - 3600, now=now),
                _post_write("known2", subreddit_pk, now - 3600, now=now),
            ],
            path=IngestPath.SUBREDDIT_NEW,
        )

    with engine.connect() as conn:
        found = prior_posts(conn, ["known1", "does-not-exist"])

    assert set(found) == {"known1"}
    assert found["known1"].first_seen_at == now


def test_known_posts_in_window_filters_by_subreddit_and_created_utc(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    with engine.begin() as conn:
        upsert_posts(
            conn,
            [
                _post_write("old", subreddit_pk, now - 1_000_000, now=now),
                _post_write("recent", subreddit_pk, now, now=now),
            ],
            path=IngestPath.SUBREDDIT_NEW,
        )

    with engine.connect() as conn:
        rows = known_posts_in_window(conn, subreddit_pk=subreddit_pk, since_created_utc=now - 100)

    ids = {r.reddit_id for r in rows}
    assert "recent" in ids
    assert "old" not in ids


def test_table_counts_reads_row_counts_for_named_tables(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    with engine.begin() as conn:
        upsert_posts(
            conn,
            [_post_write("counted", subreddit_pk, now, now=now)],
            path=IngestPath.SUBREDDIT_NEW,
        )

    with engine.connect() as conn:
        counts = table_counts(conn, ["posts", "comments"])

    assert counts["posts"] == 1
    assert counts["comments"] == 0


def test_running_runs_excludes_the_given_pk(engine: Any) -> None:
    this_pk = _insert_run(engine, status="running")
    other_pk = _insert_run(engine, status="running")

    with engine.connect() as conn:
        rows = running_runs(conn, exclude_pk=this_pk)

    pks = {r.pk for r in rows}
    assert other_pk in pks
    assert this_pk not in pks


def test_stale_candidates_splits_running_and_orphan_queued(engine: Any, now: int) -> None:
    running_pk = _insert_run(engine, status="running", pid=2**31 - 1, created_at=now - 10_000)
    orphan_queued_pk = _insert_run(engine, status="queued", pid=None, created_at=now - 10_000)

    with engine.connect() as conn:
        running_rows, orphan_pks = stale_candidates(conn, now=now, stale_after_seconds=180)

    assert running_pk in {r.pk for r in running_rows}
    assert orphan_queued_pk in orphan_pks


def test_last_successful_run_returns_the_most_recent_ok_run(engine: Any, now: int) -> None:
    _insert_run(engine, status="failed", created_at=now - 10)
    ok_pk = _insert_run(engine, status="ok", created_at=now - 5)

    with engine.connect() as conn:
        row = last_successful_run(conn, kind="run")

    assert row is not None
    assert row.pk == ok_pk
    assert row.status == "ok"


# --- the rest of db/repo.py's reads (design-round5.md §5.3) ---------------------------------


def test_reads_that_take_a_list_are_empty_in_empty_out(engine: Any) -> None:
    with engine.connect() as conn:
        assert prior_posts(conn, []) == {}
        assert source_outcomes(conn, run_pks=[]) == {}


def test_last_successful_run_is_none_when_no_run_of_that_kind_succeeded(
    engine: Any, now: int
) -> None:
    _insert_run(engine, status="failed", created_at=now)
    with engine.connect() as conn:
        assert last_successful_run(conn) is None


def test_due_posts_returns_only_posts_whose_next_check_at_has_passed(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    with engine.begin() as conn:
        upsert_posts(
            conn,
            [
                _post_write("duesoon", subreddit_pk, now, now=now),
                _post_write("duelater", subreddit_pk, now, now=now),
            ],
            path=IngestPath.SUBREDDIT_NEW,
        )
    posts = Base.metadata.tables["posts"]
    with engine.begin() as conn:
        conn.execute(
            posts.update().where(posts.c.reddit_id == "duesoon").values(next_check_at=now - 1)
        )

    with engine.connect() as conn:
        due = due_posts(conn, now=now, limit=10)
    assert [reddit_id for _pk, reddit_id in due] == ["duesoon"]


def test_recent_sweeping_runs_excludes_runs_that_swept_nothing(
    engine: Any, workspace_pk: int, now: int
) -> None:
    """The ``EXISTS`` clause is the population rule: a run with no ``run_subreddits`` child
    never enters the freshness window, whatever its status (design-round5.md §14.2).
    """
    source_pk = _insert_subreddit(engine, workspace_pk, "freshness")
    swept_ok = _insert_run(engine, status="ok", created_at=now - 30)
    _swept_but_locked = _insert_run(engine, status="skipped_locked", created_at=now - 20)
    _never_swept = _insert_run(engine, status="ok", created_at=now - 10)
    current = _insert_run(engine, status="running", created_at=now)

    run_subreddits = Base.metadata.tables["run_subreddits"]
    with engine.begin() as conn:
        for run_pk in (swept_ok, _swept_but_locked, current):
            conn.execute(
                run_subreddits.insert().values(
                    run_pk=run_pk, subreddit_pk=source_pk, stop_reason="exhausted"
                )
            )

    with engine.connect() as conn:
        window = recent_sweeping_runs(conn, current_run_pk=current, limit=2)

    assert window == [current, swept_ok], (
        "newest first; `skipped_locked` is not a freshness status and a run with no child "
        "row is excluded by the EXISTS clause"
    )
    assert _never_swept not in window


def test_source_outcomes_maps_run_and_subreddit_to_progress(
    engine: Any, workspace_pk: int, now: int
) -> None:
    source_pk = _insert_subreddit(engine, workspace_pk, "outcomes")
    run_pk = _insert_run(engine, status="ok", created_at=now)
    with engine.begin() as conn:
        upsert_run_subreddit(
            conn,
            run_pk=run_pk,
            subreddit_pk=source_pk,
            progress=SweepProgress(
                pages=3,
                items_seen=75,
                new_items=70,
                updated_items=5,
                stop_reason="cap",
                error=None,
            ),
        )

    with engine.connect() as conn:
        outcomes = source_outcomes(conn, run_pks=[run_pk])

    assert outcomes[run_pk][source_pk] == SweepProgress(
        pages=3, items_seen=75, new_items=70, updated_items=5, stop_reason="cap", error=None
    )


def test_live_rows_missing_counts_nulls_in_the_named_column(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    with engine.begin() as conn:
        upsert_posts(
            conn,
            [
                _post_write("hasperma", subreddit_pk, now, now=now),
                _post_write("noperma", subreddit_pk, now, now=now),
            ],
            path=IngestPath.SUBREDDIT_NEW,
        )
    posts = Base.metadata.tables["posts"]
    with engine.begin() as conn:
        conn.execute(posts.update().where(posts.c.reddit_id == "noperma").values(permalink=None))

    with engine.connect() as conn:
        assert live_rows_missing(conn, column="permalink", since=now, normalizer_version=1) == 1
        assert (
            live_rows_missing(conn, column="permalink", since=now + 1, normalizer_version=1) == 0
        ), "rows written before the run started are out of the population"
        assert live_rows_missing(conn, column="permalink", since=now, normalizer_version=99) == 0, (
            "the floor is scoped by normalizer_version"
        )


def test_live_rows_missing_scopes_selftext_html_to_non_empty_self_posts(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    """An empty body renders to NULL by design, so it must not count as a missing value."""
    with engine.begin() as conn:
        upsert_posts(
            conn,
            [_post_write("emptybody", subreddit_pk, now, now=now)],
            path=IngestPath.SUBREDDIT_NEW,
        )
    posts = Base.metadata.tables["posts"]
    with engine.begin() as conn:
        conn.execute(
            posts.update()
            .where(posts.c.reddit_id == "emptybody")
            .values(is_self=True, selftext="", selftext_html=None)
        )

    with engine.connect() as conn:
        assert live_rows_missing(conn, column="selftext_html", since=now, normalizer_version=1) == 0

    with engine.begin() as conn:
        conn.execute(
            posts.update().where(posts.c.reddit_id == "emptybody").values(selftext="a body")
        )
    with engine.connect() as conn:
        assert live_rows_missing(conn, column="selftext_html", since=now, normalizer_version=1) == 1


def test_live_rows_missing_refuses_a_name_that_is_not_a_posts_column(engine: Any) -> None:
    """The column name is validated against the model, so it can never carry caller text
    into the statement.
    """
    with engine.connect() as conn, pytest.raises(ValueError, match="not a column of posts"):
        live_rows_missing(conn, column="permalink; DROP TABLE posts", since=0, normalizer_version=1)


def test_rows_below_normalizer_version_counts_rows_written_this_run(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    with engine.begin() as conn:
        upsert_posts(
            conn,
            [_post_write("stale", subreddit_pk, now, now=now)],
            path=IngestPath.SUBREDDIT_NEW,
        )

    with engine.connect() as conn:
        assert rows_below_normalizer_version(conn, table="posts", since=now, version=2) == 1
        assert rows_below_normalizer_version(conn, table="posts", since=now, version=1) == 0
        assert rows_below_normalizer_version(conn, table="comments", since=now, version=2) == 0


def test_rows_below_normalizer_version_refuses_a_table_without_the_column(engine: Any) -> None:
    with engine.connect() as conn, pytest.raises(ValueError, match="carries no normalizer_version"):
        rows_below_normalizer_version(conn, table="runs", since=0, version=1)


def test_unknown_enum_occurrences_names_the_row_the_field_and_the_value(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    """One entry per ``(reddit_id, field, value)`` triple, over the two scanned fields --
    and ``None`` is never unknown (design-round5.md §13.1).
    """
    with engine.begin() as conn:
        upsert_posts(
            conn,
            [
                _post_write("weird", subreddit_pk, now, now=now),
                _post_write("ordinary", subreddit_pk, now, now=now),
            ],
            path=IngestPath.SUBREDDIT_NEW,
        )
    posts = Base.metadata.tables["posts"]
    with engine.begin() as conn:
        conn.execute(
            posts.update()
            .where(posts.c.reddit_id == "weird")
            .values(post_hint="hologram", removed_by_category="martians")
        )
        conn.execute(
            posts.update().where(posts.c.reddit_id == "ordinary").values(post_hint="image")
        )

    known = {
        "post_hint": KNOWN_VALUES.known("post_hint"),
        "removed_by_category": KNOWN_VALUES.known("removed_by_category"),
    }
    with engine.connect() as conn:
        found = unknown_enum_occurrences(conn, since=now, known=known)

    assert sorted(found) == ["weird|post_hint=hologram", "weird|removed_by_category=martians"]


def test_live_counts_counts_only_live_rows(engine: Any, subreddit_pk: int, now: int) -> None:
    with engine.begin() as conn:
        upsert_posts(
            conn,
            [
                _post_write("alive", subreddit_pk, now, now=now),
                _post_write("gone", subreddit_pk, now, now=now),
            ],
            path=IngestPath.SUBREDDIT_NEW,
        )
    posts = Base.metadata.tables["posts"]
    with engine.begin() as conn:
        conn.execute(posts.update().where(posts.c.reddit_id == "gone").values(content_state="gone"))

    with engine.connect() as conn:
        assert live_counts(conn) == {"posts_live": 1, "comments_live": 0}


# --- DB-63: the display reads behind the Runs page and the digest -------------------------


def _finish(engine: Any, run_pk: int, **overrides: Any) -> None:
    """Close a planted run through ``repo.finish_run``, never a raw ``UPDATE`` (§2.3)."""
    with engine.begin() as conn:
        finish_run(
            conn,
            run_pk=run_pk,
            status=overrides.pop("status", "ok"),
            finished_at=overrides.pop("finished_at", 2),
            counters_json=overrides.pop("counters_json", None),
            api_requests=overrides.pop("api_requests", 0),
            error=overrides.pop("error", None),
            violations_json=overrides.pop("violations_json", None),
            warnings_json=overrides.pop("warnings_json", None),
        )
    assert not overrides, f"unused overrides: {overrides}"


def test_run_display_carries_every_column_a_page_shows(engine: Any) -> None:
    """``RunRow`` stops at the lifecycle columns; a page also needs the trigger, the
    counters, the budget the run was given, the request count and the violations."""
    pk = _insert_run(
        engine,
        status="running",
        trigger="schedule",
        started_at=1,
        options_json='{"budget":{"limit":1500}}',
        settings_fingerprint="f" * 8,
        settings_json='{"budget":{"per_run_requests":1500}}',
        app_version="0.1.0",
        schema_rev="0005",
    )
    _finish(
        engine,
        pk,
        status="partial",
        counters_json='{"posts_new":7}',
        api_requests=42,
        violations_json='[{"invariant":"per_source_freshness","severity":"warning","detail":"x"}]',
        warnings_json='[{"name":"budget_exhausted","detail":"r/premiere: stopped after 3 pages"}]',
    )

    with engine.connect() as conn:
        row = run_display(conn, run_pk=pk)

    assert row is not None
    assert (row.pk, row.kind, row.trigger, row.status) == (pk, "run", "schedule", "partial")
    assert row.counters_json == '{"posts_new":7}'
    assert row.api_requests == 42
    assert row.options_json == '{"budget":{"limit":1500}}'
    assert row.violations_json is not None
    assert (row.settings_fingerprint, row.app_version, row.schema_rev) == ("f" * 8, "0.1.0", "0005")
    # Revision 0005's two columns: the settings the run resolved, so the digest can name the
    # keys that changed, and the warnings it recorded, so a page can name what made it amber.
    assert row.settings_json == '{"budget":{"per_run_requests":1500}}'
    assert row.warnings_json == (
        '[{"name":"budget_exhausted","detail":"r/premiere: stopped after 3 pages"}]'
    )


def test_run_display_is_none_for_an_unknown_pk(engine: Any) -> None:
    with engine.connect() as conn:
        assert run_display(conn, run_pk=999_999) is None


def test_recent_runs_pages_newest_first_and_filters_by_kind(engine: Any) -> None:
    """``before_pk`` is the page cursor: strictly older rows, so a page never repeats a row."""
    first = _insert_run(engine, kind="run", created_at=1)
    second = _insert_run(engine, kind="run", created_at=2)
    doctoring = _insert_run(engine, kind="doctor", created_at=3)
    third = _insert_run(engine, kind="run", created_at=4)

    with engine.connect() as conn:
        page_one = recent_runs(conn, limit=2)
        page_two = recent_runs(conn, limit=2, before_pk=page_one[-1].pk)
        only_runs = recent_runs(conn, limit=10, kind="run")

    assert [r.pk for r in page_one] == [third, doctoring]
    assert [r.pk for r in page_two] == [second, first]
    assert [r.pk for r in only_runs] == [third, second, first]
    assert doctoring not in {r.pk for r in only_runs}


def test_run_for_window_returns_the_newest_finished_run_anchored_on_its_start(
    engine: Any,
) -> None:
    """A run belongs to the day it started, and only a finished run has a digest: a run still
    in flight is the Runs page's business, not a report's."""
    before = _insert_run(engine, created_at=50, started_at=50)
    inside_early = _insert_run(engine, created_at=150, started_at=150)
    inside_late = _insert_run(engine, created_at=180, started_at=180)
    unfinished = _insert_run(engine, created_at=190, started_at=190)
    other_kind = _insert_run(engine, kind="reconcile", created_at=195, started_at=195)
    after = _insert_run(engine, created_at=250, started_at=250)
    for pk in (before, inside_early, inside_late, other_kind, after):
        _finish(engine, pk, finished_at=pk + 1000)

    with engine.connect() as conn:
        found = run_for_window(conn, start_utc=100, end_utc=200)
        empty = run_for_window(conn, start_utc=1000, end_utc=2000)
        reconcile = run_for_window(conn, start_utc=100, end_utc=200, kind="reconcile")

    assert found is not None
    assert found.pk == inside_late, "the newest finished run whose start falls in the window"
    assert unfinished != found.pk
    assert empty is None
    assert reconcile is not None
    assert reconcile.pk == other_kind


def test_run_for_window_is_half_open_on_its_end(engine: Any) -> None:
    """Local days tile without overlapping: ``[start, end)``, so midnight belongs to one day."""
    at_start = _insert_run(engine, created_at=100, started_at=100)
    at_end = _insert_run(engine, created_at=200, started_at=200)
    _finish(engine, at_start, finished_at=101)
    _finish(engine, at_end, finished_at=201)

    with engine.connect() as conn:
        found = run_for_window(conn, start_utc=100, end_utc=200)

    assert found is not None
    assert found.pk == at_start


def test_subreddit_names_maps_pks_to_display_names(engine: Any, workspace_pk: int) -> None:
    premiere = _insert_subreddit(engine, workspace_pk, "premiere", display_name="Premiere")
    editors = _insert_subreddit(engine, workspace_pk, "editors", display_name="editors")

    with engine.connect() as conn:
        names = subreddit_names(conn, pks=[premiere, editors, 999_999])
        assert subreddit_names(conn, pks=[]) == {}

    assert names == {premiere: "Premiere", editors: "editors"}


def test_workspaces_lists_pk_slug_and_name(engine: Any, workspace_pk: int) -> None:
    with engine.connect() as conn:
        rows = workspaces(conn)

    assert (workspace_pk, "premiere") == (rows[0][0], rows[0][1])
    assert rows[0][2], "a workspace always has a display name"


def _rank_fixture(engine: Any, workspace_pk: int, now: int) -> tuple[int, int]:
    """Two sources in the workspace and four posts: three live in the window, one older."""
    premiere = _insert_subreddit(engine, workspace_pk, "premiere", display_name="Premiere")
    editors = _insert_subreddit(engine, workspace_pk, "editors", display_name="editors")
    with engine.begin() as conn:
        upsert_posts(
            conn,
            [
                _post_write("lowscore", premiere, now, now=now),
                _post_write("highscore", premiere, now, now=now),
                _post_write("midscore", editors, now, now=now),
                _post_write("tooold", premiere, now - 100_000, now=now),
            ],
            path=IngestPath.SUBREDDIT_NEW,
        )
    posts = Base.metadata.tables["posts"]
    with engine.begin() as conn:
        for reddit_id, score, num_comments in (
            ("lowscore", 1, 0),
            ("highscore", 99, 0),
            ("midscore", 50, 0),
        ):
            conn.execute(
                posts.update()
                .where(posts.c.reddit_id == reddit_id)
                .values(score=score, num_comments=num_comments)
            )
    return premiere, editors


def test_ranked_posts_orders_by_rank_posts_and_not_by_the_database(
    engine: Any, workspace_pk: int, now: int
) -> None:
    """D-09: one ranking function everywhere. With no comments captured every post has zero
    distinct authors and zero comments, so the order falls through to score, then post id."""
    _rank_fixture(engine, workspace_pk, now)

    with engine.connect() as conn:
        top = ranked_posts(conn, workspace_pk=workspace_pk, since_created_utc=now - 10, limit=10)

    assert [p.post_id for p in top] == ["highscore", "midscore", "lowscore"]
    assert all(p.distinct_author_count == 0 for p in top), "no comment is captured before M1b"
    assert top[0].subreddit == "Premiere"
    assert top[1].subreddit == "editors"


def test_ranked_posts_hands_the_digest_a_link_that_opens_on_reddit(
    engine: Any, workspace_pk: int, now: int
) -> None:
    """KI-036. ``posts.permalink`` holds Reddit's own site-relative path, which is what the API
    returns and what a scrub clears; rendered unchanged it resolves against whatever server
    served the page, so every link in the digest pointed back at this one. The host is joined
    on here, on the way out, and the stored column keeps the path it was given: the digest's
    link is an address, and the row is still the row the collector wrote.
    """
    _rank_fixture(engine, workspace_pk, now)

    posts = Base.metadata.tables["posts"]
    with engine.connect() as conn:
        top = ranked_posts(conn, workspace_pk=workspace_pk, since_created_utc=now - 10, limit=10)
        stored = conn.execute(select(posts.c.permalink)).scalars().all()

    assert top, "the fixture planted no post in the window"
    for post in top:
        assert post.permalink.startswith(f"{REDDIT_WEB_HOST}/r/"), post.permalink
    assert all(path is not None and path.startswith("/r/") for path in stored), stored


def test_ranked_posts_limits_after_ranking_and_counts_its_own_window(
    engine: Any, workspace_pk: int, now: int
) -> None:
    """The limit is the top-N cap, applied after the ranking; the window is the only filter
    the database applies, and :func:`posts_in_window` counts exactly that window."""
    _rank_fixture(engine, workspace_pk, now)

    with engine.connect() as conn:
        top = ranked_posts(conn, workspace_pk=workspace_pk, since_created_utc=now - 10, limit=1)
        population = posts_in_window(conn, workspace_pk=workspace_pk, since_created_utc=now - 10)
        everything = posts_in_window(conn, workspace_pk=workspace_pk, since_created_utc=0)

    assert [p.post_id for p in top] == ["highscore"], "the highest ranked, not the first row"
    assert population == 3, "the denominator counts the window, not the page"
    assert everything == 4


def test_ranked_posts_excludes_other_workspaces_and_unlinkable_or_dead_posts(
    engine: Any, workspace_pk: int, now: int
) -> None:
    """A scrubbed post has no permalink and no title, so it can be neither linked nor named;
    it leaves the ranked population and its denominator together."""
    premiere, _editors = _rank_fixture(engine, workspace_pk, now)
    other_workspace = _insert_workspace(engine, "photo")
    elsewhere = _insert_subreddit(engine, other_workspace, "photography")
    with engine.begin() as conn:
        upsert_posts(
            conn,
            [
                _post_write("elsewhere", elsewhere, now, now=now),
                _post_write("scrubbed", premiere, now, now=now),
            ],
            path=IngestPath.SUBREDDIT_NEW,
        )
    posts = Base.metadata.tables["posts"]
    with engine.begin() as conn:
        conn.execute(
            posts.update()
            .where(posts.c.reddit_id == "scrubbed")
            .values(content_state="deleted_by_author", permalink=None, title=None)
        )

    with engine.connect() as conn:
        top = ranked_posts(conn, workspace_pk=workspace_pk, since_created_utc=now - 10, limit=10)
        population = posts_in_window(conn, workspace_pk=workspace_pk, since_created_utc=now - 10)

    ids = {p.post_id for p in top}
    assert "elsewhere" not in ids, "a workspace scopes every view"
    assert "scrubbed" not in ids
    assert population == len(top) == 3


def test_ranked_posts_counts_distinct_live_comment_authors(
    engine: Any, workspace_pk: int, now: int, insert_comment: Any
) -> None:
    """The ranking's first key, once trees are captured: distinct ``author_fullname`` over the
    live comments, NULL identities excluded rather than collapsed into one bucket (D-09)."""
    premiere, _editors = _rank_fixture(engine, workspace_pk, now)
    posts = Base.metadata.tables["posts"]
    with engine.connect() as conn:
        lowscore_pk = int(
            conn.execute(select(posts.c.pk).where(posts.c.reddit_id == "lowscore")).scalar_one()
        )
    insert_comment("c1", lowscore_pk, author_fullname="t2_one")
    insert_comment("c2", lowscore_pk, author_fullname="t2_two")
    insert_comment("c3", lowscore_pk, author_fullname="t2_two")
    insert_comment("c4", lowscore_pk, author_fullname=None)
    insert_comment("c5", lowscore_pk, author_fullname="t2_three", content_state="deleted_by_author")

    with engine.connect() as conn:
        top = ranked_posts(conn, workspace_pk=workspace_pk, since_created_utc=now - 10, limit=10)

    assert top[0].post_id == "lowscore", "two distinct authors outrank any score (D-09)"
    assert top[0].distinct_author_count == 2


def test_unknown_enum_occurrences_can_be_bounded_at_both_ends(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    """``until`` is what makes a digest of an older run truthful: without an upper bound the
    rows a *later* run wrote would be counted into the older run's report."""
    with engine.begin() as conn:
        upsert_posts(
            conn,
            [
                _post_write("early", subreddit_pk, now, now=now),
                _post_write("late", subreddit_pk, now, now=now),
            ],
            path=IngestPath.SUBREDDIT_NEW,
        )
    posts = Base.metadata.tables["posts"]
    with engine.begin() as conn:
        conn.execute(
            posts.update()
            .where(posts.c.reddit_id == "early")
            .values(post_hint="hologram", last_fetched_at=now)
        )
        conn.execute(
            posts.update()
            .where(posts.c.reddit_id == "late")
            .values(post_hint="hologram", last_fetched_at=now + 500)
        )

    known = {
        "post_hint": KNOWN_VALUES.known("post_hint"),
        "removed_by_category": KNOWN_VALUES.known("removed_by_category"),
    }
    with engine.connect() as conn:
        unbounded = unknown_enum_occurrences(conn, since=now, known=known)
        bounded = unknown_enum_occurrences(conn, since=now, until=now + 10, known=known)

    assert sorted(unbounded) == ["early|post_hint=hologram", "late|post_hint=hologram"]
    assert bounded == ["early|post_hint=hologram"]


def test_recent_sweeping_runs_never_looks_past_the_run_it_anchors_on(
    engine: Any, workspace_pk: int, now: int
) -> None:
    """The freshness window ends at ``current_run_pk``. At run time that is the newest row, so
    the invariant's behaviour is unchanged; a digest assembled for an older run would
    otherwise be handed runs that had not happened yet."""
    source_pk = _insert_subreddit(engine, workspace_pk, "anchored")
    older = _insert_run(engine, status="ok", created_at=now - 30)
    anchor = _insert_run(engine, status="ok", created_at=now - 20)
    newer = _insert_run(engine, status="ok", created_at=now - 10)

    run_subreddits = Base.metadata.tables["run_subreddits"]
    with engine.begin() as conn:
        for run_pk in (older, anchor, newer):
            conn.execute(
                run_subreddits.insert().values(
                    run_pk=run_pk, subreddit_pk=source_pk, stop_reason="exhausted"
                )
            )

    with engine.connect() as conn:
        window = recent_sweeping_runs(conn, current_run_pk=anchor, limit=2)
        newest = recent_sweeping_runs(conn, current_run_pk=newer, limit=2)

    assert window == [anchor, older]
    assert newest == [newer, anchor], "anchored on the newest row the window is unchanged"
