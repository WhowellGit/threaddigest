"""``db/repo.py``'s writes, with no spec id (design-round5.md §16, §5.2).

Upsert semantics first -- insert vs update classification, pk / first_seen_at
immutability, in-page duplicates, snapshots, authors, post_sources provenance -- then the
rest of the write surface the services call: rejects, the two-grain ``run_subreddits``
row, the per-source status machine, the two coverage writers, the run row's lifecycle
columns and the ``backups`` rows.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from threaddigest.core.models import PostRow, Reject
from threaddigest.db.ownership import IngestPath
from threaddigest.db.repo import (
    AuthorWrite,
    BackupInsert,
    PostWrite,
    RunInsert,
    SnapshotWrite,
    SweepProgress,
    UpsertOutcome,
    advance_watermark,
    backups_of_kind,
    clear_subreddit_error,
    delete_backups,
    finish_run,
    insert_backup,
    insert_item_snapshots,
    insert_post_sources,
    insert_rejects,
    insert_run,
    mark_runs,
    record_subreddit_failure,
    recount_authors,
    seed_subreddits,
    set_gap_suspected,
    set_subreddit_identity,
    stamp_complete_poll,
    table_counts,
    touch_run,
    upsert_authors,
    upsert_posts,
    upsert_run_subreddit,
)
from threaddigest.db.schema import Base

POST_KWARGS: dict[str, Any] = {
    "subreddit": "premiere",
    "subreddit_id": "t5_2s9fq",
    "author": "editorguy",
    "author_fullname": "t2_abcd12",
    "author_flair_text": None,
    "author_is_bot": False,
    "title": "original title",
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


def _post_row(reddit_id: str, created_utc: int, **overrides: Any) -> PostRow:
    kwargs = {
        **POST_KWARGS,
        "reddit_id": reddit_id,
        "fullname": f"t3_{reddit_id}",
        "created_utc": created_utc,
        **overrides,
    }
    return PostRow(**kwargs)


def _post_write(reddit_id: str, subreddit_pk: int, now: int, **overrides: Any) -> PostWrite:
    row_overrides = {k: v for k, v in overrides.items() if k in PostRow.model_fields}
    row = _post_row(reddit_id, now - 3600, **row_overrides)
    return PostWrite(
        row=row,
        subreddit_pk=subreddit_pk,
        first_seen_at=overrides.get("first_seen_at", now),
        last_fetched_at=overrides.get("last_fetched_at", now),
        next_check_at=overrides.get("next_check_at", now + 86_400),
        check_stage=overrides.get("check_stage", 0),
        content_state=overrides.get("content_state", "live"),
        author_state=overrides.get("author_state", "known"),
        misses=overrides.get("misses", 0),
        raw_json=overrides.get("raw_json", "{}"),
    )


def test_upsert_posts_classifies_new_and_updated(engine: Any, subreddit_pk: int, now: int) -> None:
    with engine.begin() as conn:
        first = upsert_posts(
            conn,
            [_post_write("p1", subreddit_pk, now), _post_write("p2", subreddit_pk, now)],
            path=IngestPath.SUBREDDIT_NEW,
        )
    assert set(first.new_ids) == {"p1", "p2"}
    assert first.updated_ids == ()
    assert set(first.pks) == {"p1", "p2"}

    with engine.begin() as conn:
        second = upsert_posts(
            conn,
            [
                _post_write("p1", subreddit_pk, now + 60, score=5),
                _post_write("p3", subreddit_pk, now + 60),
            ],
            path=IngestPath.SUBREDDIT_NEW,
        )
    assert second.new_ids == ("p3",)
    assert second.updated_ids == ("p1",)
    assert second.pks["p1"] == first.pks["p1"], "an update must keep the original pk"


def test_upsert_posts_never_moves_pk_or_first_seen_at(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    with engine.begin() as conn:
        outcome = upsert_posts(
            conn, [_post_write("immut", subreddit_pk, now)], path=IngestPath.SUBREDDIT_NEW
        )
    original_pk = outcome.pks["immut"]

    with engine.begin() as conn:
        upsert_posts(
            conn,
            [_post_write("immut", subreddit_pk, now + 3600, first_seen_at=now + 3600, score=9)],
            path=IngestPath.SUBREDDIT_NEW,
        )

    posts = Base.metadata.tables["posts"]
    with engine.connect() as conn:
        row = conn.execute(select(posts).where(posts.c.pk == original_pk)).mappings().one()
    assert row["pk"] == original_pk
    assert row["first_seen_at"] == now, (
        "first_seen_at is never_update: a later write must not move it"
    )
    assert row["score"] == 9, "score is an ordinary update_column and must move"


def test_upsert_posts_collapses_duplicate_reddit_ids_last_write_wins(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    """SW-03: Reddit returns the same post twice when items shift between pages; the
    collapse (last write wins) is what makes ``posts_new + posts_updated ==
    len(distinct ids)`` hold.
    """
    writes = [
        _post_write("dup", subreddit_pk, now, title="first copy"),
        _post_write("dup", subreddit_pk, now, title="second copy"),
    ]
    with engine.begin() as conn:
        outcome = upsert_posts(conn, writes, path=IngestPath.SUBREDDIT_NEW)
    assert outcome.new_ids == ("dup",)
    assert outcome.updated_ids == ()

    posts = Base.metadata.tables["posts"]
    with engine.connect() as conn:
        title = conn.execute(select(posts.c.title).where(posts.c.reddit_id == "dup")).scalar_one()
    assert title == "second copy"


def test_insert_post_sources_dedupes_and_preserves_first_seen_at(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    with engine.begin() as conn:
        outcome = upsert_posts(
            conn, [_post_write("sourced", subreddit_pk, now)], path=IngestPath.SUBREDDIT_NEW
        )
    post_pk = outcome.pks["sourced"]

    with engine.begin() as conn:
        added_first = insert_post_sources(
            conn, post_pks=[post_pk], source_type="subreddit", source_pk=subreddit_pk, now=now
        )
    with engine.begin() as conn:
        added_second = insert_post_sources(
            conn,
            post_pks=[post_pk],
            source_type="subreddit",
            source_pk=subreddit_pk,
            now=now + 999,
        )

    assert added_first == 1
    assert added_second == 0, "the same (post, source_type, source_pk) is DO NOTHING"

    post_sources = Base.metadata.tables["post_sources"]
    with engine.connect() as conn:
        first_seen_at = conn.execute(
            select(post_sources.c.first_seen_at).where(post_sources.c.post_pk == post_pk)
        ).scalar_one()
    assert first_seen_at == now, "the second call must not move first_seen_at"


def test_insert_item_snapshots_inserts_rows(engine: Any, subreddit_pk: int, now: int) -> None:
    with engine.begin() as conn:
        outcome = upsert_posts(
            conn, [_post_write("snapped", subreddit_pk, now)], path=IngestPath.SUBREDDIT_NEW
        )
    post_pk = outcome.pks["snapped"]

    with engine.begin() as conn:
        inserted = insert_item_snapshots(
            conn,
            [
                SnapshotWrite(
                    item_pk=post_pk,
                    kind="post",
                    fetched_at=now,
                    score=10,
                    num_comments=2,
                    upvote_ratio=0.75,
                )
            ],
        )
    assert inserted == 1

    snapshots = Base.metadata.tables["item_snapshots"]
    with engine.connect() as conn:
        row = conn.execute(select(snapshots).where(snapshots.c.item_pk == post_pk)).mappings().one()
    assert row["kind"] == "post"
    assert row["score"] == 10


def test_upsert_authors_last_seen_at_is_monotonic(engine: Any, now: int) -> None:
    with engine.begin() as conn:
        upsert_authors(
            conn,
            [AuthorWrite(author_fullname="t2_late", name="first-name", seen_at=now + 1_000)],
        )
    with engine.begin() as conn:
        upsert_authors(
            conn,
            [AuthorWrite(author_fullname="t2_late", name="second-name", seen_at=now)],
        )

    authors = Base.metadata.tables["authors"]
    with engine.connect() as conn:
        row = (
            conn.execute(select(authors).where(authors.c.author_fullname == "t2_late"))
            .mappings()
            .one()
        )
    assert row["name"] == "second-name", "name is a plain update_column: it moves"
    assert row["last_seen_at"] == now + 1_000, "an out-of-order write must not move it backward"
    assert row["first_seen_at"] == now + 1_000, "first_seen_at is insert-only"


# --- the rest of db/repo.py's writes (design-round5.md §5.2) --------------------------------


def _run_insert(now: int, **overrides: Any) -> RunInsert:
    fields: dict[str, Any] = {
        "kind": "run",
        "trigger": "cli",
        "status": "running",
        "created_at": now,
        "started_at": now,
        "pid": None,
        "stage": None,
        "options_json": None,
        "app_version": None,
        "praw_version": None,
        "schema_rev": None,
        "settings_fingerprint": None,
        "log_path": None,
    }
    fields.update(overrides)
    return RunInsert(**fields)


def _subreddit(engine: Any, pk: int) -> Any:
    subreddits = Base.metadata.tables["subreddits"]
    with engine.connect() as conn:
        return conn.execute(subreddits.select().where(subreddits.c.pk == pk)).mappings().one()


def test_every_write_helper_is_a_no_op_on_empty_input(
    engine: Any, workspace_pk: int, subreddit_pk: int, now: int
) -> None:
    """Empty input writes nothing and issues no statement -- the page that saw no accepted
    rows, no authors or no rejects is the common case, not an error.
    """
    with engine.begin() as conn:
        outcome = upsert_posts(conn, [], path=IngestPath.SUBREDDIT_NEW)
        assert outcome == UpsertOutcome(new_ids=(), updated_ids=(), pks={})
        assert (
            insert_post_sources(
                conn, post_pks=[], source_type="subreddit", source_pk=subreddit_pk, now=now
            )
            == 0
        )
        assert insert_item_snapshots(conn, []) == 0
        assert insert_rejects(conn, run_pk=1, rejects=[], now=now) == 0
        assert seed_subreddits(conn, workspace_pk=workspace_pk, names=[], now=now) == 0
        assert upsert_authors(conn, []) is None
        assert recount_authors(conn, []) is None
        assert mark_runs(conn, pks=[], status="crashed", finished_at=now, error="x") is None
        assert delete_backups(conn, []) is None

    with engine.connect() as conn:
        assert table_counts(conn, ["posts", "authors", "raw_rejects", "post_sources"]) == {
            "posts": 0,
            "authors": 0,
            "raw_rejects": 0,
            "post_sources": 0,
        }


def test_insert_rejects_stores_the_raw_item_and_the_reason(engine: Any, now: int) -> None:
    run_pk = _insert_run_row(engine, now)
    with engine.begin() as conn:
        stored = insert_rejects(
            conn,
            run_pk=run_pk,
            rejects=[Reject(raw={"id": None, "b": 1}, error="missing id")],
            now=now,
        )
    assert stored == 1

    raw_rejects = Base.metadata.tables["raw_rejects"]
    with engine.connect() as conn:
        row = conn.execute(select(raw_rejects)).mappings().one()
    assert row["run_pk"] == run_pk
    assert row["error"] == "missing id"
    assert json.loads(row["raw_json"]) == {"id": None, "b": 1}


def _insert_run_row(engine: Any, now: int, **overrides: Any) -> int:
    with engine.begin() as conn:
        return insert_run(conn, _run_insert(now, **overrides))


def test_upsert_run_subreddit_writes_one_row_at_both_grains(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    """The per-page progress row and the terminal row are the same row: the upsert on
    ``(run_pk, subreddit_pk)`` is what makes the two grains agree (design-round5.md §6.3).
    """
    run_pk = _insert_run_row(engine, now)
    with engine.begin() as conn:
        upsert_run_subreddit(
            conn,
            run_pk=run_pk,
            subreddit_pk=subreddit_pk,
            progress=SweepProgress(
                pages=1, items_seen=25, new_items=25, updated_items=0, stop_reason=None, error=None
            ),
        )
    with engine.begin() as conn:
        upsert_run_subreddit(
            conn,
            run_pk=run_pk,
            subreddit_pk=subreddit_pk,
            progress=SweepProgress(
                pages=2,
                items_seen=40,
                new_items=30,
                updated_items=10,
                stop_reason="exhausted",
                error=None,
            ),
        )

    run_subreddits = Base.metadata.tables["run_subreddits"]
    with engine.connect() as conn:
        rows = conn.execute(select(run_subreddits)).mappings().all()
    assert len(rows) == 1
    assert rows[0]["pages"] == 2
    assert rows[0]["stop_reason"] == "exhausted"


def test_record_subreddit_failure_counts_up_and_never_disables_without_a_threshold(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    for expected in (1, 2, 3):
        with engine.begin() as conn:
            failures, disabled = record_subreddit_failure(
                conn,
                subreddit_pk=subreddit_pk,
                status="forbidden",
                error="403 private",
                now=now,
                disable_at=None,
            )
        assert (failures, disabled) == (expected, False)

    row = _subreddit(engine, subreddit_pk)
    assert row["status"] == "forbidden"
    assert row["last_error"] == "403 private"
    assert row["enabled"] is True


def test_record_subreddit_failure_disables_at_the_threshold_and_stays_disabled(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    """The same statement counts and decides, so the caller cannot race itself. The trace
    the spec verified is (1, False), (2, False), (3, True), (4, True) at threshold 3.
    """
    seen: list[tuple[int, bool]] = []
    for _ in range(4):
        with engine.begin() as conn:
            seen.append(
                record_subreddit_failure(
                    conn,
                    subreddit_pk=subreddit_pk,
                    status="redirect",
                    error="moved",
                    now=now,
                    disable_at=3,
                )
            )
    assert seen == [(1, False), (2, False), (3, True), (4, True)]
    assert _subreddit(engine, subreddit_pk)["enabled"] is False


def test_clear_subreddit_error_resets_the_trio_and_leaves_the_coverage_columns_alone(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    with engine.begin() as conn:
        record_subreddit_failure(
            conn,
            subreddit_pk=subreddit_pk,
            status="error",
            error="boom",
            now=now,
            disable_at=None,
        )
        advance_watermark(conn, subreddit_pk=subreddit_pk, seen_max_created_utc=now)
        stamp_complete_poll(conn, subreddit_pk=subreddit_pk, at=now)
        set_gap_suspected(conn, subreddit_pk=subreddit_pk, at=now)

    with engine.begin() as conn:
        clear_subreddit_error(conn, subreddit_pk=subreddit_pk, now=now)

    row = _subreddit(engine, subreddit_pk)
    assert (row["status"], row["consecutive_failures"], row["last_error"]) == ("ok", 0, None)
    assert row["watermark_created_utc"] == now, "clearing the error must not touch coverage"
    assert row["last_complete_poll_at"] == now
    assert row["gap_suspected_at"] == now


def test_advance_watermark_moves_forward_only_and_is_a_no_op_on_none(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    with engine.begin() as conn:
        advance_watermark(conn, subreddit_pk=subreddit_pk, seen_max_created_utc=now)
    with engine.begin() as conn:
        advance_watermark(conn, subreddit_pk=subreddit_pk, seen_max_created_utc=now - 5_000)
    assert _subreddit(engine, subreddit_pk)["watermark_created_utc"] == now

    with engine.begin() as conn:
        advance_watermark(conn, subreddit_pk=subreddit_pk, seen_max_created_utc=None)
    assert _subreddit(engine, subreddit_pk)["watermark_created_utc"] == now, (
        "an empty or sticky-only sweep must leave a prior watermark intact"
    )

    with engine.begin() as conn:
        advance_watermark(conn, subreddit_pk=subreddit_pk, seen_max_created_utc=now + 10)
    assert _subreddit(engine, subreddit_pk)["watermark_created_utc"] == now + 10


def test_set_gap_suspected_clears_the_latch_with_none(
    engine: Any, subreddit_pk: int, now: int
) -> None:
    with engine.begin() as conn:
        set_gap_suspected(conn, subreddit_pk=subreddit_pk, at=now)
    assert _subreddit(engine, subreddit_pk)["gap_suspected_at"] == now
    with engine.begin() as conn:
        set_gap_suspected(conn, subreddit_pk=subreddit_pk, at=None)
    assert _subreddit(engine, subreddit_pk)["gap_suspected_at"] is None


def test_set_subreddit_identity_adopts_the_listing_id(engine: Any, subreddit_pk: int) -> None:
    assert _subreddit(engine, subreddit_pk)["subreddit_id"] is None
    with engine.begin() as conn:
        set_subreddit_identity(conn, subreddit_pk=subreddit_pk, subreddit_id="t5_2s9fq")
    assert _subreddit(engine, subreddit_pk)["subreddit_id"] == "t5_2s9fq"


def test_seed_subreddits_is_idempotent_and_lower_cases_names(
    engine: Any, workspace_pk: int, now: int
) -> None:
    with engine.begin() as conn:
        added = seed_subreddits(
            conn, workspace_pk=workspace_pk, names=["Premiere", "VideoEditing"], now=now
        )
    assert added == 2
    with engine.begin() as conn:
        again = seed_subreddits(
            conn, workspace_pk=workspace_pk, names=["premiere", "adobe"], now=now + 1
        )
    assert again == 1, "only the source that was not already there is added"

    subreddits = Base.metadata.tables["subreddits"]
    with engine.connect() as conn:
        names = set(
            conn.execute(
                select(subreddits.c.name_lower).where(subreddits.c.workspace_pk == workspace_pk)
            ).scalars()
        )
    assert {"premiere", "videoediting", "adobe"} <= names


def test_touch_run_writes_the_heartbeat_and_the_stage(engine: Any, now: int) -> None:
    run_pk = _insert_run_row(engine, now)
    with engine.begin() as conn:
        touch_run(conn, run_pk=run_pk, heartbeat_at=now + 5, stage="sweep:premiere")

    runs = Base.metadata.tables["runs"]
    with engine.connect() as conn:
        row = conn.execute(select(runs).where(runs.c.pk == run_pk)).mappings().one()
    assert row["heartbeat_at"] == now + 5
    assert row["stage"] == "sweep:premiere"


def test_finish_run_closes_the_row_with_counters_and_violations(engine: Any, now: int) -> None:
    run_pk = _insert_run_row(engine, now)
    with engine.begin() as conn:
        finish_run(
            conn,
            run_pk=run_pk,
            status="partial",
            finished_at=now + 60,
            counters_json='{"pages":3}',
            api_requests=7,
            error=None,
            violations_json='[{"invariant":"per_source_freshness"}]',
        )

    runs = Base.metadata.tables["runs"]
    with engine.connect() as conn:
        row = conn.execute(select(runs).where(runs.c.pk == run_pk)).mappings().one()
    assert row["status"] == "partial"
    assert row["finished_at"] == now + 60
    assert row["counters_json"] == '{"pages":3}'
    assert row["api_requests"] == 7
    assert row["violations_json"] == '[{"invariant":"per_source_freshness"}]'


def test_mark_runs_stamps_a_terminal_status_on_the_named_rows(engine: Any, now: int) -> None:
    condemned = _insert_run_row(engine, now)
    survivor = _insert_run_row(engine, now)
    with engine.begin() as conn:
        mark_runs(
            conn,
            pks=[condemned],
            status="crashed",
            finished_at=now + 1,
            error="no heartbeat",
        )

    runs = Base.metadata.tables["runs"]
    with engine.connect() as conn:
        statuses = dict(conn.execute(select(runs.c.pk, runs.c.status)).all())
    assert statuses[condemned] == "crashed"
    assert statuses[survivor] == "running"


def test_backup_rows_round_trip_newest_first_and_delete_by_pk(engine: Any, now: int) -> None:
    def _row(name: str, created_at: int) -> BackupInsert:
        return BackupInsert(
            path=f"/backups/{name}.db",
            sha256="0" * 64,
            size_bytes=10,
            integrity="ok",
            kind="pre-migrate",
            created_at=created_at,
            schema_rev="0001",
            table_counts_json='{"posts":0}',
        )

    with engine.begin() as conn:
        older = insert_backup(conn, _row("older", now - 10))
        newer = insert_backup(conn, _row("newer", now))
        insert_backup(
            conn,
            BackupInsert(
                path="/backups/daily.db",
                sha256="1" * 64,
                size_bytes=10,
                integrity="ok",
                kind="daily",
                created_at=now,
                schema_rev=None,
                table_counts_json=None,
            ),
        )

    with engine.connect() as conn:
        rows = backups_of_kind(conn, "pre-migrate")
    assert [pk for pk, _path, _created in rows] == [newer, older], "newest first"
    assert rows[0][1] == "/backups/newer.db"

    with engine.begin() as conn:
        delete_backups(conn, [older])
    with engine.connect() as conn:
        assert [pk for pk, _p, _c in backups_of_kind(conn, "pre-migrate")] == [newer]
        assert len(backups_of_kind(conn, "daily")) == 1
