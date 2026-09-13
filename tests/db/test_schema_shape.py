"""Shape invariants of schema revision 1 (docs/PLAN.md "Data model" conventions).

Each test scans the whole metadata or the whole live database rather than a hand-kept list,
so a new table or column is covered the moment it exists.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    Engine,
    Integer,
    Time,
    UniqueConstraint,
    inspect,
    text,
)
from sqlalchemy.exc import IntegrityError

from insightminer.db.schema import Base

PostInserter = Callable[..., int]

EPOCH_SUFFIXES = ("_utc", "_at")

DECLARED_INDEXES: dict[str, set[str]] = {
    "posts": {
        "ix_posts_next_check_at",
        "ix_posts_subreddit_pk_created_utc",
        "ix_posts_author_fullname",
        "ix_posts_content_state",
    },
    "comments": {"ix_comments_post_pk_parent_comment_pk", "ix_comments_author_fullname"},
    "post_themes": {"ix_post_themes_theme_pk"},
    "item_snapshots": {"ix_item_snapshots_item_pk_fetched_at"},
    "subreddits": {"ix_subreddits_workspace_pk"},
    "searches": {"ix_searches_workspace_pk"},
    "themes": {"ix_themes_workspace_pk"},
}


def _live_columns(engine: Engine, table: str) -> dict[str, dict[str, object]]:
    with engine.connect() as conn:
        rows = conn.execute(text(f"PRAGMA table_info({table})")).mappings().all()
    return {str(r["name"]): dict(r) for r in rows}


def test_every_reddit_id_table_has_integer_pk_and_unique_reddit_id(engine: Engine) -> None:
    insp = inspect(engine)
    tables = [
        t
        for t in insp.get_table_names()
        if any(c["name"] == "reddit_id" for c in insp.get_columns(t))
    ]
    assert sorted(tables) == ["comments", "posts"]
    for table in tables:
        assert insp.get_pk_constraint(table)["constrained_columns"] == ["pk"]
        live = _live_columns(engine, table)
        assert live["pk"]["type"] == "INTEGER", "pk must be a rowid alias (declared INTEGER)"
        assert live["pk"]["pk"] == 1
        assert [c for c, info in live.items() if info["pk"]] == ["pk"]
        assert live["reddit_id"]["notnull"] == 1
        unique_sets = [u["column_names"] for u in insp.get_unique_constraints(table)]
        assert ["reddit_id"] in unique_sets
        with engine.connect() as conn:
            ddl = conn.execute(
                text("SELECT sql FROM sqlite_master WHERE name = :t"), {"t": table}
            ).scalar_one()
        assert "AUTOINCREMENT" in ddl, f"{table} must never recycle a rowid"
        assert "WITHOUT ROWID" not in ddl


def test_every_pk_column_is_a_rowid_alias(engine: Engine, workspace_pk: int, now: int) -> None:
    """``pk INTEGER`` + table-level PRIMARY KEY is still a rowid alias; prove it on a row."""
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO subreddits (workspace_pk, name_lower, display_name, added_at) "
                "VALUES (:ws, 'x', 'x', :now)"
            ),
            {"ws": workspace_pk, "now": now},
        )
        rowid, pk = conn.execute(text("SELECT rowid, pk FROM subreddits")).one()
    assert rowid == pk


def test_every_timestamp_is_integer_epoch_and_no_datetime_anywhere(engine: Engine) -> None:
    for table in Base.metadata.tables.values():
        live = _live_columns(engine, table.name)
        for column in table.columns:
            assert not isinstance(column.type, DateTime | Date | Time), (
                f"{table.name}.{column.name} uses a date/time type"
            )
            if column.name.endswith(EPOCH_SUFFIXES):
                assert isinstance(column.type, Integer), f"{table.name}.{column.name}"
                assert live[column.name]["type"] == "INTEGER", f"{table.name}.{column.name}"


def test_every_column_has_a_single_line_comment() -> None:
    missing = [
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if not (column.comment and column.comment.strip()) or "\n" in (column.comment or "")
    ]
    assert missing == []


def test_next_check_at_is_not_null(engine: Engine) -> None:
    assert Base.metadata.tables["posts"].c.next_check_at.nullable is False
    assert _live_columns(engine, "posts")["next_check_at"]["notnull"] == 1


def test_check_rejects_unknown_derived_state(insert_post: PostInserter) -> None:
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        insert_post("bad1", content_state="foo")
    with pytest.raises(IntegrityError, match="CHECK constraint failed"):
        insert_post("bad2", author_state="bar")


def test_check_rejects_unknown_run_status(engine: Engine, now: int) -> None:
    with (
        pytest.raises(IntegrityError, match="CHECK constraint failed"),
        engine.begin() as conn,
    ):
        conn.execute(
            text(
                "INSERT INTO runs (kind, trigger, status, created_at) "
                "VALUES ('run', 'cli', 'weird', :now)"
            ),
            {"now": now},
        )


def test_check_accepts_unknown_upstream_enum_values(
    engine: Engine, insert_post: PostInserter
) -> None:
    pk = insert_post("open1", removed_by_category="brand_new", post_hint="hologram")
    with engine.connect() as conn:
        stored = conn.execute(
            text("SELECT removed_by_category, post_hint FROM posts WHERE pk = :pk"), {"pk": pk}
        ).one()
    assert tuple(stored) == ("brand_new", "hologram")


def test_declared_indexes_exist(engine: Engine) -> None:
    insp = inspect(engine)
    for table, expected in DECLARED_INDEXES.items():
        present = {ix["name"] for ix in insp.get_indexes(table)}
        assert expected <= present, f"{table}: missing {expected - present}"


def test_no_foreign_key_on_comment_parent(engine: Engine) -> None:
    fks = inspect(engine).get_foreign_keys("comments")
    assert all("parent_comment_pk" not in fk["constrained_columns"] for fk in fks)
    assert [fk["constrained_columns"] for fk in fks] == [["post_pk"]]


def test_workspace_seed_and_ownership(engine: Engine) -> None:
    with engine.connect() as conn:
        slug, ranking = conn.execute(text("SELECT slug, ranking FROM workspaces")).one()
    assert (slug, ranking) == ("premiere", "distinct_authors")
    insp = inspect(engine)
    for table in ("subreddits", "searches", "themes"):
        fk_columns = [fk["constrained_columns"] for fk in insp.get_foreign_keys(table)]
        assert ["workspace_pk"] in fk_columns, table
        assert _live_columns(engine, table)["workspace_pk"]["notnull"] == 1, table
    for table in ("posts", "comments"):
        assert "workspace_pk" not in _live_columns(engine, table), table


def test_subreddit_identity_is_per_workspace(engine: Engine, workspace_pk: int, now: int) -> None:
    """Two workspaces may monitor the same subreddit; one workspace may not list it twice."""
    insert = text(
        "INSERT INTO subreddits (workspace_pk, name_lower, display_name, subreddit_id, added_at) "
        "VALUES (:ws, 'premiere', 'premiere', 't5_2qh1e', :now)"
    )
    with engine.begin() as conn:
        other = conn.execute(
            text(
                "INSERT INTO workspaces (slug, name, created_at) "
                "VALUES ('smb-ai', 'AI adoption in SMBs', :now)"
            ),
            {"now": now},
        ).lastrowid
        conn.execute(insert, {"ws": workspace_pk, "now": now})
        conn.execute(insert, {"ws": other, "now": now})
        assert conn.execute(text("SELECT count(*) FROM subreddits")).scalar_one() == 2
    with pytest.raises(IntegrityError, match="UNIQUE constraint failed"), engine.begin() as conn:
        conn.execute(insert, {"ws": workspace_pk, "now": now})


def test_constraint_names_follow_the_naming_convention(engine: Engine) -> None:
    """§10.4: ``op.f(...)`` is load-bearing for a batch recreate on SQLite -- a bare string
    name (e.g. ``"status"``) emits an unnamed-by-convention ``CONSTRAINT status CHECK (...)``
    instead of ``CONSTRAINT ck_runs_status CHECK (...)``, and nothing else in the suite would
    notice, because ``make schema`` regenerates ``schema.sql`` from the same damaged database
    and pytest-alembic's ``test_model_definitions_match_ddl`` does not compare CHECK
    constraints. This test reflects every table's live CHECK and UNIQUE constraint names and
    compares them against ``Base.metadata``, so a migration that recreates a table under the
    wrong name goes red here.

    Primary keys are excluded: ``posts`` and ``comments`` declare ``sqlite_autoincrement``,
    which forces the inline ``INTEGER PRIMARY KEY`` form rather than a table-level
    ``PRIMARY KEY (...)`` constraint, so SQLAlchemy's reflection reports their primary-key
    constraint name as ``None`` even though the naming convention would name it. That is a
    reflection quirk of AUTOINCREMENT, not a naming defect, so this test does not touch PKs.
    """
    insp = inspect(engine)
    for table in Base.metadata.tables.values():
        live_checks = {c["name"] for c in insp.get_check_constraints(table.name)}
        meta_checks = {
            c.name for c in table.constraints if isinstance(c, CheckConstraint) and c.name
        }
        assert live_checks == meta_checks, table.name

        live_unique = {u["name"] for u in insp.get_unique_constraints(table.name)}
        meta_unique = {
            c.name for c in table.constraints if isinstance(c, UniqueConstraint) and c.name
        }
        assert live_unique == meta_unique, table.name

    assert {c["name"] for c in insp.get_check_constraints("runs")} == {
        "ck_runs_status",
        "ck_runs_trigger",
    }
