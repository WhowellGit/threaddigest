"""Behavioral tests of the connection chokepoint: pragmas, FK enforcement, read-only, DDL."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import IntegrityError, OperationalError

from insightminer.db.engine import checkpoint_truncate, engine_for

PostInserter = Callable[..., int]

EXPECTED_PRAGMAS = {
    "journal_mode": "wal",
    "synchronous": 1,  # NORMAL
    "foreign_keys": 1,
    "busy_timeout": 30000,
    "temp_store": 2,  # MEMORY
    "secure_delete": 1,
}


def _pragmas(conn: Connection) -> dict[str, object]:
    return {name: conn.exec_driver_sql(f"PRAGMA {name}").scalar() for name in EXPECTED_PRAGMAS}


def test_two_pool_checkouts_both_carry_the_pragmas(engine: Engine) -> None:
    first = engine.connect()
    second = engine.connect()
    try:
        assert first.connection.dbapi_connection is not second.connection.dbapi_connection
        assert _pragmas(first) == EXPECTED_PRAGMAS
        assert _pragmas(second) == EXPECTED_PRAGMAS
    finally:
        first.close()
        second.close()


def test_foreign_keys_are_enforced(engine: Engine) -> None:
    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"), engine.begin() as c:
        c.execute(
            text(
                "INSERT INTO comments (reddit_id, fullname, post_pk, parent_fullname, "
                "created_utc, first_seen_at, last_fetched_at, source, normalizer_version, "
                "raw_json) VALUES ('c1', 't1_c1', 999999, 't3_x', 1, 1, 1, 'comments', 1, '{}')"
            )
        )


def test_read_only_engine_refuses_insert(engine: Engine, db_path: Path) -> None:
    ro = engine_for(db_path, read_only=True)
    try:
        with ro.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA journal_mode").scalar() == "wal"
            assert conn.execute(text("SELECT count(*) FROM workspaces")).scalar_one() == 1
            with pytest.raises(OperationalError, match="readonly"):
                conn.execute(
                    text("INSERT INTO ui_state (key, value, updated_at) VALUES ('k', 'v', 1)")
                )
    finally:
        ro.dispose()


def test_ddl_is_transactional(engine: Engine) -> None:
    """The explicit-BEGIN recipe makes CREATE TABLE roll back; legacy sqlite3 mode would not."""
    with pytest.raises(RuntimeError, match="abort"), engine.begin() as conn:
        conn.exec_driver_sql("CREATE TABLE ddl_probe (x INTEGER)")
        assert "ddl_probe" in inspect(conn).get_table_names()
        raise RuntimeError("abort")
    assert "ddl_probe" not in inspect(engine).get_table_names()


def test_checkpoint_truncate_empties_the_wal(
    engine: Engine, db_path: Path, insert_post: PostInserter
) -> None:
    insert_post("wal1")
    wal = db_path.with_name(db_path.name + "-wal")
    assert wal.stat().st_size > 0
    busy, _log_frames, _checkpointed = checkpoint_truncate(engine)
    assert busy == 0
    assert wal.stat().st_size == 0
