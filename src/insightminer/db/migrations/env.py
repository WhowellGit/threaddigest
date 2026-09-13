"""Alembic environment for the SQLite database.

Rules that live here (docs/PLAN.md "Release, upgrade and migration practices"):

- ``render_as_batch=True``: SQLite lacks most of ALTER, so column changes recreate the table.
- ``transaction_per_migration=True``: a failed step never leaves a half-migrated database.
  This is real only because ``engine_for`` makes DDL transactional (explicit BEGIN).
- ``include_object`` hides the FTS5 virtual tables, their shadow tables, the ``*_live``
  views and SQLite internals from autogenerate, so it never tries to drop them.
- ``PRAGMA foreign_keys=OFF`` is issued on the raw DBAPI connection *before* any
  transaction begins; inside a transaction the pragma is a silent no-op. It is switched
  back on afterwards so a pooled connection does not leak the setting into the app.

The URL comes from, in order: ``config.attributes["connection"]`` (an Engine or a
Connection handed in programmatically), ``-x db_url=...``, ``sqlalchemy.url`` in the
config, or the ``INSIGHTMINER_DB_URL`` environment variable.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any

from alembic import context
from sqlalchemy import Connection, Engine
from sqlalchemy.engine import make_url

from insightminer.db.engine import engine_for
from insightminer.db.schema import Base

config = context.config
target_metadata = Base.metadata

#: Reflected names autogenerate must ignore (FTS5 tables and shadows, live views, internals).
EXCLUDED_NAME_PATTERNS: tuple[str, ...] = ("*_fts", "*_fts_*", "*_live", "sqlite_*")


def include_object(
    obj: Any,
    name: str | None,
    type_: str,
    reflected: bool,  # noqa: FBT001 - Alembic callback signature
    compare_to: Any,
) -> bool:
    """Keep ordinary tables; hide FTS5, views and SQLite internals from autogenerate."""
    del obj, reflected, compare_to
    if type_ == "table" and name is not None:
        return not any(fnmatchcase(name, pattern) for pattern in EXCLUDED_NAME_PATTERNS)
    return True


def _resolve_url() -> str:
    x_args = context.get_x_argument(as_dictionary=True)
    url = (
        x_args.get("db_url")
        or config.get_main_option("sqlalchemy.url")
        or os.environ.get("INSIGHTMINER_DB_URL")
    )
    if not url:
        msg = (
            "No database URL: pass -x db_url=sqlite:///path.db, set INSIGHTMINER_DB_URL, "
            "or hand a connection in through config.attributes['connection']"
        )
        raise RuntimeError(msg)
    return url


def _engine_from_url(url: str) -> Engine:
    parsed = make_url(url)
    if parsed.get_backend_name() != "sqlite" or not parsed.database:
        msg = f"Only file-based sqlite URLs are supported, got {url!r}"
        raise RuntimeError(msg)
    database = parsed.database
    if database.startswith("file:"):
        database = database.removeprefix("file:").split("?", 1)[0]
    return engine_for(Path(database))


def _set_foreign_keys(connection: Connection, *, enabled: bool) -> None:
    """Toggle foreign-key enforcement on the raw DBAPI connection, outside any transaction."""
    if connection.in_transaction():
        return  # the pragma would be a silent no-op; the caller owns the transaction
    dbapi = connection.connection.dbapi_connection
    if dbapi is None:  # pragma: no cover - only for a detached pool proxy
        return
    dbapi.execute(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")


def _run_with_connection(connection: Connection) -> None:
    _set_foreign_keys(connection, enabled=False)
    on_version_apply: Callable[..., None] | None = config.attributes.get("on_version_apply")
    try:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=True,
            transaction_per_migration=True,
            include_object=include_object,
            compare_type=True,
            on_version_apply=on_version_apply,
        )
        with context.begin_transaction():
            context.run_migrations()
    finally:
        _set_foreign_keys(connection, enabled=True)


def run_migrations_offline() -> None:
    """Emit SQL to stdout instead of running it (``alembic upgrade head --sql``)."""
    context.configure(
        url=_resolve_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
        include_object=include_object,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations against a live connection."""
    connectable = config.attributes.get("connection")
    if connectable is None:
        engine = _engine_from_url(_resolve_url())
        try:
            with engine.connect() as connection:
                _run_with_connection(connection)
        finally:
            engine.dispose()
    elif isinstance(connectable, Engine):
        with connectable.connect() as connection:
            _run_with_connection(connection)
    else:
        _run_with_connection(connectable)


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
