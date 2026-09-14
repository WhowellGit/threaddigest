"""Connection-factory chokepoint.

This is the only module in the project allowed to call ``create_engine`` (ruff bans it
elsewhere), so every connection the application ever opens passes through
:func:`engine_for` and carries the same pragmas.

Transaction control: the sqlite3 driver's legacy mode only emits ``BEGIN`` before DML,
which makes DDL non-transactional and defeats Alembic's ``transaction_per_migration``.
Following the SQLAlchemy-documented recipe, the driver's implicit ``BEGIN`` is disabled
(``isolation_level = None``) and SQLAlchemy emits ``BEGIN`` itself from the ``begin``
event, so ``CREATE TABLE`` inside ``engine.begin()`` really rolls back on failure. The
connect-time pragmas run before any ``BEGIN``, which matters because ``journal_mode`` and
``foreign_keys`` cannot be changed inside a transaction.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final
from urllib.parse import quote

from sqlalchemy import Connection, Engine, create_engine, event
from sqlalchemy.engine import URL

__all__ = [
    "CONNECTION_PRAGMAS",
    "DEFAULT_BUSY_TIMEOUT_MS",
    "DB_FILENAME",
    "checkpoint_truncate",
    "db_path_for",
    "engine_for",
]

#: The database file's name inside a data directory. One constant, because ``doctor``,
#: ``db init``, ``db upgrade``, ``db current`` and ``run`` must all resolve the same file
#: from ``settings.data_dir`` alone, and a second spelling anywhere would be a second
#: database.
DB_FILENAME: Final = "insightminer.db"

#: Lock wait every connection gets unless :func:`engine_for` is given an override. Extracted
#: from ``CONNECTION_PRAGMAS`` so the default and the override cannot drift (design-round5 §10.5).
DEFAULT_BUSY_TIMEOUT_MS: Final = 30_000

#: Pragmas applied to every connection, in order. ``journal_mode`` is persistent in the
#: file; the rest are per-connection and must be re-applied on every checkout.
CONNECTION_PRAGMAS: tuple[tuple[str, str], ...] = (
    ("journal_mode", "WAL"),
    ("synchronous", "NORMAL"),
    ("foreign_keys", "ON"),
    ("busy_timeout", str(DEFAULT_BUSY_TIMEOUT_MS)),
    ("temp_store", "MEMORY"),
    ("secure_delete", "ON"),
)


def db_path_for(data_dir: Path) -> Path:
    """The database file inside ``data_dir``. Resolves nothing and creates nothing."""
    return data_dir / DB_FILENAME


def _sqlite_url(db_path: Path, *, read_only: bool) -> URL:
    """Build a ``sqlite+pysqlite`` URI-mode URL for ``db_path``.

    The path is percent-encoded so spaces, ``?`` and ``#`` survive the SQLite URI parser;
    ``uri=true`` tells the driver to interpret the filename as a URI.
    """
    filename = "file:" + quote(str(db_path.resolve()), safe="/")
    query: dict[str, str] = {"uri": "true"}
    if read_only:
        query["mode"] = "ro"
    return URL.create("sqlite+pysqlite", database=filename, query=query)


def _pragmas_with_busy_timeout(busy_timeout_ms: int | None) -> tuple[tuple[str, str], ...]:
    """``CONNECTION_PRAGMAS`` with the one ``busy_timeout`` value substituted, or unchanged."""
    if busy_timeout_ms is None:
        return CONNECTION_PRAGMAS
    return tuple(
        (name, str(busy_timeout_ms) if name == "busy_timeout" else value)
        for name, value in CONNECTION_PRAGMAS
    )


def engine_for(
    db_path: Path, *, read_only: bool = False, busy_timeout_ms: int | None = None
) -> Engine:
    """Return an engine for the SQLite file at ``db_path`` with the project pragmas.

    ``read_only=True`` opens the file with ``mode=ro`` so any write raises
    ``OperationalError``; the file must already exist.

    ``busy_timeout_ms`` overrides the default :data:`DEFAULT_BUSY_TIMEOUT_MS` lock wait for
    THIS engine only; every other pragma is unchanged and every existing call site keeps the
    30 s default. The parameter exists because two tests need the application's writer to
    actually give up on a held write lock inside a test's lifetime rather than after half a
    minute, and ``mock.patch`` is banned outside ``tests/adapters/`` (design-round5 §10.5).
    """
    pragmas = _pragmas_with_busy_timeout(busy_timeout_ms)
    engine = create_engine(_sqlite_url(db_path, read_only=read_only))

    @event.listens_for(engine, "connect")
    def _on_connect(dbapi_connection: Any, _record: Any) -> None:
        # Disable the driver's implicit BEGIN; SQLAlchemy emits it below.
        dbapi_connection.isolation_level = None
        cursor = dbapi_connection.cursor()
        try:
            for name, value in pragmas:
                cursor.execute(f"PRAGMA {name}={value}")
        finally:
            cursor.close()

    @event.listens_for(engine, "begin")
    def _on_begin(conn: Connection) -> None:
        if conn.get_execution_options().get("isolation_level") != "AUTOCOMMIT":
            conn.exec_driver_sql("BEGIN")

    return engine


def checkpoint_truncate(engine: Engine) -> tuple[int, int, int]:
    """Run ``PRAGMA wal_checkpoint(TRUNCATE)`` outside any transaction.

    Returns SQLite's ``(busy, log_frames, checkpointed_frames)`` triple; ``busy == 1``
    means another connection held the WAL and the checkpoint could not complete.
    """
    raw = engine.raw_connection()
    try:
        cursor = raw.cursor()
        try:
            cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            row = cursor.fetchone()
        finally:
            cursor.close()
    finally:
        raw.close()
    if row is None:  # pragma: no cover - SQLite always returns one row
        msg = "PRAGMA wal_checkpoint returned no row"
        raise RuntimeError(msg)
    busy, log_frames, checkpointed = row
    return int(busy), int(log_frames), int(checkpointed)
