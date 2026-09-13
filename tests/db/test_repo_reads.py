"""``db/repo.py``'s reads, with no spec id (design-round5.md §16, §5.3): enabled sources,
the freshness population, prior posts, the known window, table counts, the run queries,
the freshness window and its per-source outcomes, and the three reads the invariants
consume (population floors, normalizer version, unknown enum occurrences).
"""

from __future__ import annotations

from typing import Any

import pytest

from insightminer.core.models import KNOWN_VALUES, PostRow
from insightminer.db.ownership import IngestPath
from insightminer.db.repo import (
    PostWrite,
    RunInsert,
    SweepProgress,
    all_sources_for_freshness,
    default_workspace_pk,
    due_posts,
    enabled_subreddits,
    insert_run,
    known_posts_in_window,
    last_successful_run,
    live_counts,
    live_rows_missing,
    prior_posts,
    recent_sweeping_runs,
    rows_below_normalizer_version,
    running_runs,
    source_outcomes,
    stale_candidates,
    table_counts,
    unknown_enum_occurrences,
    upsert_posts,
    upsert_run_subreddit,
)
from insightminer.db.schema import Base

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
    assert not overrides, f"unused overrides: {overrides}"
    with engine.begin() as conn:
        return insert_run(conn, run)


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
