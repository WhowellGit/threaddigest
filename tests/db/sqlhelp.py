"""The one legal home for a ``text()``-based test helper, if one is ever wanted.

``pyproject``'s ``TID251`` per-file-ignore lifts the banned-API rule for
``src/threaddigest/db/**``, ``tests/db/**`` and ``tests/adapters/**`` only. The three
packages this tranche creates -- ``tests/services/``, ``tests/e2e/``, ``tests/gates/`` --
are not on that list and must not import ``sqlalchemy.text`` or ``create_engine``
themselves (design-round5.md §2.3). Both helpers below are built with plain SQLAlchemy
Core (``select`` over ``Base.metadata.tables[...]``) and need no ``text()`` today; the
module exists so the temptation to add one has a legal, reviewed home instead of a
widened ignore list.
"""

from __future__ import annotations

import hashlib
from typing import Any

import sqlalchemy as sa
from sqlalchemy import Connection, select

from threaddigest.db.schema import Base

__all__ = ["read_run", "run_pks", "table_digest"]


def table_digest(conn: Connection, table: str) -> str:
    """A stable content hash of every row of ``table``, ordered by its primary key.

    Used by the excluded-command / dry-run "nothing was written" tests: two digests
    taken before and after an operation are equal iff every column of every row is
    byte-for-byte unchanged, including columns the caller did not think to name.
    """
    t = Base.metadata.tables[table]
    rows = conn.execute(select(t).order_by(*t.primary_key.columns)).all()
    return hashlib.sha256(repr(rows).encode("utf-8")).hexdigest()


def read_run(conn: Connection) -> dict[str, Any] | None:
    """The most recently inserted ``runs`` row as a plain mapping, or ``None`` if empty.

    e2e / gate tests use this instead of hand-rolling ``SELECT * FROM runs ORDER BY pk
    DESC LIMIT 1`` with ``text()``: one call, one place that knows the column list is
    "everything", so a schema change never needs an update here.
    """
    runs = Base.metadata.tables["runs"]
    row = conn.execute(select(runs).order_by(runs.c.pk.desc()).limit(1)).mappings().first()
    return dict(row) if row is not None else None


def run_pks(conn: Connection) -> list[int]:
    """Every ``runs.pk``, oldest first, read **revision-independently**.

    Built from ``sa.table(...)`` rather than ``Base.metadata.tables["runs"]`` because the
    head models name ``violations_json``, which revision 0001 does not have: a test that
    counts run rows in a database deliberately below head (the 0001 fixture, a downgraded
    file) would otherwise die with ``no such column: runs.violations_json`` before it could
    assert anything. Same reason, and same shape, as ``db.migrate``'s T12 statements.
    """
    runs = sa.table("runs", sa.column("pk"))
    return [int(row.pk) for row in conn.execute(sa.select(runs).order_by(runs.c.pk)).all()]
