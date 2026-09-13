"""FTS5 behaviour: live-gated triggers, scrub removes the entry, rebuild indexes live only.

The database panel's three empirical findings are each pinned here: the naive
``count(*) FROM posts_fts`` is not a membership count, ``rebuild`` over the live view skips
tombstones, and ``integrity-check`` goes red when the index holds a row the view does not.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import Connection, Engine, text

from insightminer.db.fts import fts_membership_count, integrity_check, rebuild

PostInserter = Callable[..., int]

CANARY = "zxqcanaryword"


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
