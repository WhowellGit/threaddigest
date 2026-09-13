"""FTS5 maintenance helpers: membership count, rebuild, integrity check.

The FTS5 tables are external-content tables over the ``posts_live`` / ``comments_live``
views. Two facts drive the shape of this module (verified by the database panel on SQLite
3.53 and by ``tests/db/test_fts.py``):

- ``SELECT count(*) FROM posts_fts`` reads the *content* source, not the index, so it can
  never disagree with the live-row count and can never go red. Membership is counted from
  the ``<table>_docsize`` shadow table instead (``columnsize`` is on by default).
- ``rebuild`` re-reads the content source; because that source is the live-only view, a
  rebuild indexes live rows only and ``integrity-check`` then agrees with the triggers.
"""

from __future__ import annotations

from sqlalchemy import Connection, text
from sqlalchemy.exc import DatabaseError

__all__ = ["FTS_TABLES", "fts_membership_count", "integrity_check", "rebuild"]

#: The FTS5 tables shipped in schema revision 1.
FTS_TABLES: tuple[str, ...] = ("posts_fts", "comments_fts")


def _checked(table: str) -> str:
    if table not in FTS_TABLES:
        msg = f"unknown FTS table {table!r}; expected one of {FTS_TABLES}"
        raise ValueError(msg)
    return table


def fts_membership_count(conn: Connection, table: str) -> int:
    """Number of rows actually present in the FTS index for ``table``.

    Counts the ``<table>_docsize`` shadow table. Never ``count(*) FROM <table>``: on an
    external-content FTS5 table that returns the content source's count instead.
    """
    name = _checked(table)
    return int(conn.execute(text(f"SELECT count(*) FROM {name}_docsize")).scalar_one())


def rebuild(conn: Connection, table: str) -> None:
    """Discard the index for ``table`` and re-read it from its live-only content view."""
    name = _checked(table)
    conn.execute(text(f"INSERT INTO {name}({name}) VALUES ('rebuild')"))


def integrity_check(conn: Connection, table: str) -> bool:
    """Return True when the index agrees with its content view, False when FTS5 says malformed.

    Uses the ``rank = 1`` form: on SQLite 3.53 the plain ``'integrity-check'`` only verifies
    the index's internal structure and passes with entries missing, stale or wrong; ``rank = 1``
    also compares the index against the content view (verified in ``tests/db/test_fts.py``).
    Any error other than FTS5's malformed / checksum-mismatch verdict is re-raised.
    """
    name = _checked(table)
    try:
        conn.execute(text(f"INSERT INTO {name}({name}, rank) VALUES ('integrity-check', 1)"))
    except DatabaseError as exc:
        message = str(exc.orig).lower()
        if "malformed" in message or "checksum mismatch" in message:
            return False
        raise
    return True
