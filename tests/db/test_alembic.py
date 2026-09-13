"""Migration history tests: pytest-alembic built-ins plus project-specific guarantees."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from alembic import command
from pytest_alembic.tests import (  # noqa: F401 - collected by pytest
    test_model_definitions_match_ddl,
    test_single_head_revision,
    test_up_down_consistency,
    test_upgrade,
)
from sqlalchemy import Engine, text
from sqlalchemy.dialects.sqlite import insert

from insightminer.db.engine import engine_for
from insightminer.db.fts import fts_membership_count, integrity_check
from insightminer.db.schema import Post
from insightminer.db.schema_dump import alembic_config

NOW = 1_800_000_000  # matches the conftest row builders


def test_foreign_keys_off_inside_migration_and_clean_after(tmp_path: Path) -> None:
    """env.py issues PRAGMA foreign_keys=OFF before the transaction, and restores it after."""
    seen: list[int] = []

    def probe(ctx: Any, **_kwargs: Any) -> None:
        seen.append(int(ctx.connection.exec_driver_sql("PRAGMA foreign_keys").scalar()))

    engine = engine_for(tmp_path / "fk.db")
    try:
        cfg = alembic_config()
        cfg.attributes["connection"] = engine
        cfg.attributes["on_version_apply"] = probe
        command.upgrade(cfg, "head")
        assert seen == [0], "foreign_keys must read 0 while a migration runs"
        with engine.connect() as conn:
            # Same pooled DBAPI connection env.py used: proves the pragma was switched back.
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            assert conn.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    finally:
        engine.dispose()


def _post_values(reddit_id: str, subreddit_pk: int, *, score: int, seen_at: int) -> dict[str, Any]:
    return {
        "reddit_id": reddit_id,
        "fullname": f"t3_{reddit_id}",
        "subreddit_pk": subreddit_pk,
        "title": f"title {score}",
        "created_utc": NOW - 3600,
        "score": score,
        "first_seen_at": seen_at,
        "last_fetched_at": seen_at,
        "next_check_at": seen_at + 86_400,
        "source": "subreddit_new",
        "normalizer_version": 1,
        "raw_json": "{}",
    }


def _identity(engine: Engine) -> tuple[int, int, int, int]:
    with engine.connect() as conn:
        pk, first_seen_at, score = conn.execute(
            text("SELECT pk, first_seen_at, score FROM posts WHERE reddit_id = 'up1'")
        ).one()
        max_pk, count = conn.execute(text("SELECT max(pk), count(*) FROM posts")).one()
        assert max_pk == count, "max(pk) == count(*) is the PK-stability invariant"
    return int(pk), int(first_seen_at), int(score), int(count)


def test_on_conflict_upsert_preserves_pk_and_first_seen_at(
    engine: Engine, subreddit_pk: int
) -> None:
    results = []
    for i in range(3):
        values = _post_values("up1", subreddit_pk, score=i, seen_at=NOW + i)
        stmt = insert(Post).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["reddit_id"],
            set_={
                "score": stmt.excluded.score,
                "title": stmt.excluded.title,
                "last_fetched_at": stmt.excluded.last_fetched_at,
            },
        )
        with engine.begin() as conn:
            conn.execute(stmt)
        results.append(_identity(engine))
    pks = {r[0] for r in results}
    first_seen = {r[1] for r in results}
    assert pks == {1}
    assert first_seen == {NOW}
    assert results[-1][2] == 2
    with engine.connect() as conn:
        assert fts_membership_count(conn, "posts_fts") == 1
        assert integrity_check(conn, "posts_fts")


@pytest.mark.gate
def test_insert_or_replace_burns_the_pk_and_detaches_fts(engine: Engine, subreddit_pk: int) -> None:
    """Positive control: the forbidden upsert form does exactly the damage the plan describes."""
    columns = list(_post_values("x", 1, score=0, seen_at=0))
    sql = text(
        f"INSERT OR REPLACE INTO posts ({', '.join(columns)}) "
        f"VALUES ({', '.join(':' + c for c in columns)})"
    )
    pks = []
    for i in range(3):
        with engine.begin() as conn:
            conn.execute(sql, _post_values("up1", subreddit_pk, score=i, seen_at=NOW + i))
        with engine.connect() as conn:
            pk, first_seen_at = conn.execute(
                text("SELECT pk, first_seen_at FROM posts WHERE reddit_id = 'up1'")
            ).one()
        pks.append(int(pk))
        assert first_seen_at == NOW + i, "REPLACE overwrote first_seen_at"
    assert pks == [1, 2, 3], "REPLACE deletes and re-inserts, burning a pk each time"
    with engine.connect() as conn:
        max_pk, count = conn.execute(text("SELECT max(pk), count(*) FROM posts")).one()
        assert (max_pk, count) == (3, 1)
        # REPLACE's implicit delete fires no delete trigger (recursive_triggers is off), so
        # the two burned pks stay in the index: detached FTS rows.
        assert fts_membership_count(conn, "posts_fts") == 3
        assert not integrity_check(conn, "posts_fts")
