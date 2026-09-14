"""Behavioral tests of the connection chokepoint: pragmas, FK enforcement, read-only, DDL."""

from __future__ import annotations

import gc
import sqlite3
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError

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


def test_busy_timeout_is_overridable_and_defaults_to_30s(db_path: Path) -> None:
    """§10.5: ``busy_timeout_ms`` overrides the pragma for THIS engine only, and every
    existing call site (no ``busy_timeout_ms`` given) still gets the 30 s default.
    """
    default_engine = engine_for(db_path)
    override_engine = engine_for(db_path, busy_timeout_ms=300)
    try:
        with default_engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 30_000
        with override_engine.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA busy_timeout").scalar() == 300
    finally:
        default_engine.dispose()
        override_engine.dispose()


def test_checkpoint_truncate_empties_the_wal(
    engine: Engine, db_path: Path, insert_post: PostInserter
) -> None:
    insert_post("wal1")
    wal = db_path.with_name(db_path.name + "-wal")
    assert wal.stat().st_size > 0
    busy, _log_frames, _checkpointed = checkpoint_truncate(engine)
    assert busy == 0
    assert wal.stat().st_size == 0


def test_a_pragma_that_fails_closes_the_dbapi_connection(engine: Engine, db_path: Path) -> None:
    """A corrupt file makes the ``connect`` listener's first ``PRAGMA`` raise, and the raw
    connection must be closed on the way out.

    The pool does not own the connection yet at that point, so nothing else will ever close
    it and ``engine.dispose()`` cannot: the record was never checked in. Left open it surfaces
    as ``ResourceWarning: unclosed database`` at the next collection, which this project's
    ``-W error`` turns into a red run with no failing test attached to it -- exactly what
    ``tests/services/test_doctor.py``'s corrupt-database report hit. Detected here
    deterministically: the connection is still reachable through the raised exception's
    traceback, so it can be asked whether it is closed.
    """
    checkpoint_truncate(engine)
    engine.dispose()
    with db_path.open("r+b") as handle:
        handle.seek(100)
        handle.write(b"\xff" * 4096)

    before = {id(obj) for obj in gc.get_objects() if isinstance(obj, sqlite3.Connection)}
    corrupt = engine_for(db_path)
    try:
        with pytest.raises(DatabaseError):
            corrupt.connect()
    finally:
        corrupt.dispose()

    opened = [
        obj
        for obj in gc.get_objects()
        if isinstance(obj, sqlite3.Connection) and id(obj) not in before
    ]
    assert len(opened) == 1, "the failed connect did not create exactly one raw connection"
    with pytest.raises(sqlite3.ProgrammingError, match="closed database"):
        opened[0].execute("select 1")
