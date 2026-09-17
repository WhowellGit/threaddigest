"""FTS5 behaviour: live-gated triggers, scrub removes the entry, rebuild indexes live only.

The database panel's three empirical findings are each pinned here: the naive
``count(*) FROM posts_fts`` is not a membership count, ``rebuild`` over the live view skips
tombstones, and ``integrity-check`` goes red when the index holds a row the view does not.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, text

from threaddigest.db.engine import checkpoint_truncate
from threaddigest.db.fts import fts_membership_count, integrity_check, optimize, rebuild
from threaddigest.db.migrate import current_revision, downgrade_one

PostInserter = Callable[..., int]

CANARY = "zxqcanaryword"


def _downgrade_to(engine: Engine, revision: str) -> None:
    """Step back one revision at a time until the database is at ``revision``.

    The target is **named**, never counted from head: a control that took two steps back
    from head meant revision 0002 while 0004 was head and revision 0003 once 0005 was, and
    the revision it lands on is the whole point of a control that must go red. A revision
    that cannot be reached raises rather than looping.
    """
    seen: set[str] = set()
    while (current := current_revision(engine)) != revision:
        if current is None or current in seen:
            msg = f"cannot reach revision {revision}: stopped at {current}"
            raise AssertionError(msg)
        seen.add(current)
        downgrade_one(engine)


def _matches(conn: Connection, table: str, term: str) -> int:
    return int(
        conn.execute(
            text(f"SELECT count(*) FROM {table} WHERE {table} MATCH :term"), {"term": term}
        ).scalar_one()
    )


def _naive_count(conn: Connection, table: str) -> int:
    return int(conn.execute(text(f"SELECT count(*) FROM {table}")).scalar_one())


def test_live_post_is_indexed(engine: Engine, insert_post: PostInserter) -> None:
    insert_post("p1", title=f"Premiere crashes {CANARY} on export")
    with engine.connect() as conn:
        assert _matches(conn, "posts_fts", CANARY) == 1
        assert fts_membership_count(conn, "posts_fts") == 1
        assert integrity_check(conn, "posts_fts")


def test_tombstone_insert_is_not_indexed(
    engine: Engine, insert_post: PostInserter, now: int
) -> None:
    insert_post("p1", title=f"live {CANARY}")
    insert_post(
        "p2",
        title=None,
        selftext=None,
        author=None,
        author_fullname=None,
        content_state="deleted_by_author",
        scrubbed_at=now,
    )
    with engine.connect() as conn:
        assert fts_membership_count(conn, "posts_fts") == 1
        assert _matches(conn, "posts_fts", CANARY) == 1


def test_naive_count_is_the_content_count_not_membership(
    engine: Engine, insert_post: PostInserter
) -> None:
    """Documented trap: count(*) FROM posts_fts reads the content view, so it cannot go red."""
    insert_post("p1")
    insert_post("p2", content_state="gone", title=None, selftext=None)
    with engine.connect() as conn:
        naive = _naive_count(conn, "posts_fts")
        live_rows = conn.execute(text("SELECT count(*) FROM posts_live")).scalar_one()
        assert naive == live_rows == 1
        # Plant a stale entry the way a broken trigger would; the naive count does not move.
        conn.execute(
            text(
                "INSERT INTO posts_fts(rowid, title, selftext, author) VALUES (999, 'x', 'y', 'z')"
            )
        )
        assert _naive_count(conn, "posts_fts") == 1
        assert fts_membership_count(conn, "posts_fts") == 2
        assert not integrity_check(conn, "posts_fts")
        conn.rollback()


def test_scrub_removes_the_entry(engine: Engine, insert_post: PostInserter, now: int) -> None:
    pk = insert_post("p1", title=f"about {CANARY}", selftext=f"and {CANARY} again")
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE posts SET title = NULL, selftext = NULL, selftext_html = NULL, "
                "author = NULL, author_fullname = NULL, url = NULL, permalink = NULL, "
                "content_state = 'deleted_by_author', scrubbed_at = :now, "
                "raw_json = '{\"tombstone\": true}' WHERE pk = :pk"
            ),
            {"now": now, "pk": pk},
        )
    with engine.connect() as conn:
        assert _matches(conn, "posts_fts", CANARY) == 0
        assert fts_membership_count(conn, "posts_fts") == 0
        assert integrity_check(conn, "posts_fts")


def test_edit_reindexes_and_score_refresh_does_not_churn(
    engine: Engine, insert_post: PostInserter
) -> None:
    pk = insert_post("p1", title="before-word")
    with engine.begin() as conn:
        conn.execute(text("UPDATE posts SET score = 42 WHERE pk = :pk"), {"pk": pk})
        conn.execute(text("UPDATE posts SET title = 'after-word' WHERE pk = :pk"), {"pk": pk})
    with engine.connect() as conn:
        assert _matches(conn, "posts_fts", "before") == 0
        assert _matches(conn, "posts_fts", "after") == 1
        assert fts_membership_count(conn, "posts_fts") == 1
        assert integrity_check(conn, "posts_fts")


def test_delete_of_live_row_removes_the_entry(engine: Engine, insert_post: PostInserter) -> None:
    pk = insert_post("p1", title=CANARY)
    with engine.begin() as conn:
        conn.execute(text("DELETE FROM posts WHERE pk = :pk"), {"pk": pk})
    with engine.connect() as conn:
        assert fts_membership_count(conn, "posts_fts") == 0
        assert integrity_check(conn, "posts_fts")


def test_rebuild_indexes_live_rows_only_and_passes_integrity_check(
    engine: Engine, insert_post: PostInserter
) -> None:
    insert_post("p1", title=f"one {CANARY}")
    insert_post("p2", title=f"two {CANARY}")
    insert_post("p3", title=None, selftext=None, content_state="removed_by_moderator")
    with engine.begin() as conn:
        # Corrupt the index on purpose (a stale tombstone entry), then prove rebuild repairs it.
        conn.execute(
            text("INSERT INTO posts_fts(rowid, title, selftext, author) VALUES (3, 'x', 'y', 'z')")
        )
        assert fts_membership_count(conn, "posts_fts") == 3
        assert not integrity_check(conn, "posts_fts")
        rebuild(conn, "posts_fts")
        assert fts_membership_count(conn, "posts_fts") == 2
        assert _matches(conn, "posts_fts", CANARY) == 2
        assert integrity_check(conn, "posts_fts")


def test_comments_fts_mirrors_posts(
    engine: Engine, insert_post: PostInserter, insert_comment: PostInserter, now: int
) -> None:
    post_pk = insert_post("p1")
    live = insert_comment("c1", post_pk, body=f"reply {CANARY}")
    insert_comment("c2", post_pk, body=None, author=None, content_state="deleted_by_author")
    with engine.connect() as conn:
        assert _matches(conn, "comments_fts", CANARY) == 1
        assert fts_membership_count(conn, "comments_fts") == 1
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE comments SET body = NULL, body_html = NULL, author = NULL, "
                "author_fullname = NULL, content_state = 'deleted_by_author', "
                "scrubbed_at = :now WHERE pk = :pk"
            ),
            {"now": now, "pk": live},
        )
    with engine.connect() as conn:
        assert _matches(conn, "comments_fts", CANARY) == 0
        assert fts_membership_count(conn, "comments_fts") == 0
        rebuild(conn, "comments_fts")
        assert fts_membership_count(conn, "comments_fts") == 0
        assert integrity_check(conn, "comments_fts")


def test_helpers_reject_unknown_tables(engine: Engine) -> None:
    with engine.connect() as conn, pytest.raises(ValueError, match="unknown FTS table"):
        fts_membership_count(conn, "posts")


def test_fts_definition_shape(engine: Engine) -> None:
    """External content on the live views, keyed on pk, porter unicode61, columnsize on."""
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name, type, sql FROM sqlite_master WHERE name LIKE '%\\_fts' ESCAPE '\\'")
        ).all()
        views = set(
            conn.execute(text("SELECT name FROM sqlite_master WHERE type = 'view'")).scalars()
        )
        shadows = set(
            conn.execute(
                text("SELECT name FROM sqlite_master WHERE name LIKE '%docsize'")
            ).scalars()
        )
    definitions = {name: sql for name, _type, sql in rows}
    assert set(definitions) == {"posts_fts", "comments_fts"}
    for name, content in (("posts_fts", "posts_live"), ("comments_fts", "comments_live")):
        sql = definitions[name]
        assert f"content='{content}'" in sql
        assert "content_rowid='pk'" in sql
        assert "tokenize='porter unicode61'" in sql
        assert "columnsize=0" not in sql.replace(" ", "")
        assert content in views
        assert f"{name}_docsize" in shadows


def test_author_scrub_reindexes_without_author(engine: Engine, insert_post: PostInserter) -> None:
    """account_deleted keeps the content live but the author must leave the index (DB-29)."""
    pk = insert_post("p1", author="canaryuser", author_fullname="t2_canary", selftext=CANARY)
    with engine.connect() as conn:
        assert _matches(conn, "posts_fts", "canaryuser") == 1
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE posts SET author = NULL, author_fullname = NULL, author_flair_text = NULL, "
                "author_state = 'account_deleted' WHERE pk = :pk"
            ),
            {"pk": pk},
        )
    with engine.connect() as conn:
        assert _matches(conn, "posts_fts", "canaryuser") == 0
        assert _matches(conn, "posts_fts", CANARY) == 1
        assert fts_membership_count(conn, "posts_fts") == 1
        assert integrity_check(conn, "posts_fts")


# ------------------------------------------------- KI-009 and KI-012: bytes, not answers
#
# The SQLite seat (2026-09-14): the suite asserted the index's answers and never its bytes, so a
# scrub that left the term in the index's data blocks passed, and update triggers that rewrote
# every post on every routine sweep passed. These read the blocks and the file.

IDENTICAL_UPSERT = (
    "UPDATE posts SET title = title, selftext = selftext, author = author, "
    "content_state = content_state, score = score + 1 WHERE pk = :pk"
)


def _index_bytes(conn: Connection, table: str) -> int:
    return int(
        conn.execute(text(f"SELECT coalesce(sum(length(block)), 0) FROM {table}_data")).scalar_one()
    )


def _blocks_holding(conn: Connection, table: str, term: str) -> int:
    return int(
        conn.execute(
            text(f"SELECT count(*) FROM {table}_data WHERE instr(block, :needle) > 0"),
            {"needle": term.encode()},
        ).scalar_one()
    )


def test_a_routine_upsert_with_identical_text_leaves_the_index_untouched(
    engine: Engine, insert_post: PostInserter
) -> None:
    """KI-012: the upsert sets title, selftext, author, and content_state on every DO UPDATE;
    the update trigger fires on the SET list, so without a WHEN clause every sweep rewrote
    every post's index entry with identical text."""
    pk = insert_post("p1", title=f"about {CANARY}", selftext="a body")
    with engine.connect() as conn:
        before = _index_bytes(conn, "posts_fts")
    for _ in range(3):
        with engine.begin() as conn:
            conn.execute(text(IDENTICAL_UPSERT), {"pk": pk})
    with engine.connect() as conn:
        assert _index_bytes(conn, "posts_fts") == before
        assert _matches(conn, "posts_fts", CANARY) == 1
        assert integrity_check(conn, "posts_fts")
    with engine.begin() as conn:  # a real edit still reindexes
        conn.execute(text("UPDATE posts SET title = 'changedword' WHERE pk = :pk"), {"pk": pk})
    with engine.connect() as conn:
        assert _matches(conn, "posts_fts", CANARY) == 0
        assert _matches(conn, "posts_fts", "changedword") == 1


def test_positive_control_the_unconditional_trigger_rewrote_the_index(
    engine: Engine, insert_post: PostInserter
) -> None:
    """The same statements against revision 0002's triggers grow the index: the test above
    can go red."""
    pk = insert_post("p1", title=f"about {CANARY}", selftext="a body")
    _downgrade_to(engine, "0002")  # revision 0002's triggers: no WHEN clause
    with engine.connect() as conn:
        before = _index_bytes(conn, "posts_fts")
    for _ in range(3):
        with engine.begin() as conn:
            conn.execute(text(IDENTICAL_UPSERT), {"pk": pk})
    with engine.connect() as conn:
        assert _index_bytes(conn, "posts_fts") > before


_SCRUB = (
    "UPDATE posts SET title = NULL, selftext = NULL, selftext_html = NULL, "
    "author = NULL, author_fullname = NULL, url = NULL, permalink = NULL, "
    "content_state = 'deleted_by_author', scrubbed_at = :now, "
    "raw_json = '{\"tombstone\": true}' WHERE pk = :pk"
)


def _set_fts_secure_delete(engine: Engine, table: str, on: bool) -> None:
    with engine.begin() as conn:
        conn.execute(
            text(f"INSERT INTO {table}({table}, rank) VALUES ('secure-delete', :v)"),
            {"v": 1 if on else 0},
        )


def test_scrub_with_secure_delete_leaves_no_term_bytes_without_an_optimize(
    engine: Engine, insert_post: PostInserter, now: int, db_path: Path, tmp_path: Path
) -> None:
    """KI-009, revision 0004: FTS5's persistent ``secure-delete`` option is on at head, so the
    scrub trigger's ``'delete'`` removes the term's bytes as it runs. No ``optimize`` is needed
    for compliance: the term is gone from the data blocks, the database file, and a fresh copy
    immediately after the scrub. This is SC-01's byte-level guarantee."""
    pk = insert_post("p1", title=f"about {CANARY}", selftext=f"and {CANARY} again")
    with engine.begin() as conn:
        conn.execute(text(_SCRUB), {"now": now, "pk": pk})
    with engine.connect() as conn:
        assert _matches(conn, "posts_fts", CANARY) == 0
        assert _blocks_holding(conn, "posts_fts", CANARY) == 0  # gone without an optimize
        assert integrity_check(conn, "posts_fts")
    busy, _, _ = checkpoint_truncate(engine)
    assert busy == 0
    copy = tmp_path / "copy.sqlite"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"VACUUM INTO '{copy}'")
    assert CANARY.encode() not in db_path.read_bytes()
    assert CANARY.encode() not in copy.read_bytes()


def test_positive_control_without_secure_delete_the_term_survives_a_scrub_until_optimize(
    engine: Engine, insert_post: PostInserter, now: int, db_path: Path, tmp_path: Path
) -> None:
    """The control that makes the test above meaningful: with the option turned back off, a
    scrub leaves the term in the delete markers (search says "no match" but the bytes remain),
    and only ``optimize`` plus the core ``secure_delete`` pragma clears the file. This is the
    behaviour KI-009 had before revision 0004, and why the option, not ``optimize``, is the
    compliance mechanism."""
    _set_fts_secure_delete(engine, "posts_fts", on=False)
    pk = insert_post("p1", title=f"about {CANARY}", selftext=f"and {CANARY} again")
    with engine.begin() as conn:
        conn.execute(text(_SCRUB), {"now": now, "pk": pk})
    with engine.connect() as conn:
        assert _matches(conn, "posts_fts", CANARY) == 0
        assert _blocks_holding(conn, "posts_fts", CANARY) > 0  # the term survives the scrub
    with engine.begin() as conn:
        optimize(conn, "posts_fts")
    busy, _, _ = checkpoint_truncate(engine)
    assert busy == 0
    copy = tmp_path / "copy.sqlite"
    with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
        conn.exec_driver_sql(f"VACUUM INTO '{copy}'")
    with engine.connect() as conn:
        assert _blocks_holding(conn, "posts_fts", CANARY) == 0
        assert integrity_check(conn, "posts_fts")
    assert CANARY.encode() not in db_path.read_bytes()
    assert CANARY.encode() not in copy.read_bytes()
