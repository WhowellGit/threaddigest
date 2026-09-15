"""Turn on FTS5 persistent secure-delete so a scrub removes term bytes without an optimize (KI-009).

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-15

``PRAGMA secure_delete`` zeroes freed pages in the main database, but FTS5 is a virtual table:
its ``'delete'`` command normally appends a delete-key to a new segment and leaves the old
term bytes in ``<table>_data`` until a ``'merge'``/``'optimize'``/``'rebuild'`` rewrites the
segment. Anyone with read access to the file can reconstruct a "deleted" row's text until then
(SQLite FTS5 docs, "The secure-delete Configuration Option"). The external review's SQLite seat
and reviewer C both pointed at the persistent ``'secure-delete'`` option as the mechanism built
for exactly this threat: with it set, FTS5 removes the old entries as rows are updated or
deleted, so the scrub triggers (revision 0003) clear the bytes immediately and ``optimize``
becomes maintenance rather than the compliance step.

This migration sets the option on both indexes and runs one ``'optimize'`` to merge away any
delete markers written before it. Nothing else changes: no table is recreated, so the batch
checklist does not apply.

Constraint (SQLite FTS5 docs): once a row has been updated or deleted with this option set, the
index may not be read or written by FTS5 older than 3.42.0. ``services/doctor.py`` checks the
runtime SQLite version, and the container image (M4) must satisfy it.

``downgrade()`` sets the option back to 0 for future writes. It cannot restore already-removed
term bytes, and there is nothing to restore: the point of the option is that they are gone.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

FTS_TABLES = ("posts_fts", "comments_fts")


def upgrade() -> None:
    for table in FTS_TABLES:
        op.execute(f"INSERT INTO {table}({table}, rank) VALUES ('secure-delete', 1)")
        op.execute(f"INSERT INTO {table}({table}) VALUES ('optimize')")


def downgrade() -> None:
    for table in FTS_TABLES:
        op.execute(f"INSERT INTO {table}({table}, rank) VALUES ('secure-delete', 0)")
