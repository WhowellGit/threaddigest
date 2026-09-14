"""Gate the search-index update triggers on an actual change (KI-012).

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-14

``UPDATE OF title, selftext, author, content_state`` fires on the SET list, not on a change of
value, and the one upsert generator (``db/ownership.py``, ``db/repo.py``) sets all four columns
on every ``DO UPDATE``. So every routine sweep re-upserted the whole listing window and every
post wrote a delete marker plus a fresh entry into the index each day with identical text: the
index grew almost fivefold over seven identical sweeps of a thousand posts in the SQLite
seat's reproduction, and each delete marker holds the term verbatim, a copy a scrub never
reaches (see KI-009 and ``db/fts.py::optimize``). A ``WHEN`` clause on the two update triggers
makes an unchanged row a no-op; ``IS NOT`` handles NULLs. Nothing else changes: no table is
recreated, so the batch checklist in the runbook does not apply, and the index needs no
rebuild because the existing entries are correct.

``downgrade()`` restores the unconditional triggers of revision 0001, text for text.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

POSTS_AU_GATED = """CREATE TRIGGER IF NOT EXISTS posts_fts_au
    AFTER UPDATE OF title, selftext, author, content_state ON posts
    WHEN old.title IS NOT new.title
      OR old.selftext IS NOT new.selftext
      OR old.author IS NOT new.author
      OR old.content_state IS NOT new.content_state
    BEGIN
        INSERT INTO posts_fts(posts_fts, rowid, title, selftext, author)
        SELECT 'delete', old.pk, old.title, old.selftext, old.author
        WHERE old.content_state = 'live';
        INSERT INTO posts_fts(rowid, title, selftext, author)
        SELECT new.pk, new.title, new.selftext, new.author
        WHERE new.content_state = 'live';
    END"""

COMMENTS_AU_GATED = """CREATE TRIGGER IF NOT EXISTS comments_fts_au
    AFTER UPDATE OF body, author, content_state ON comments
    WHEN old.body IS NOT new.body
      OR old.author IS NOT new.author
      OR old.content_state IS NOT new.content_state
    BEGIN
        INSERT INTO comments_fts(comments_fts, rowid, body, author)
        SELECT 'delete', old.pk, old.body, old.author
        WHERE old.content_state = 'live';
        INSERT INTO comments_fts(rowid, body, author)
        SELECT new.pk, new.body, new.author
        WHERE new.content_state = 'live';
    END"""

# Revision 0001's text, verbatim, for the downgrade.
POSTS_AU_UNCONDITIONAL = """CREATE TRIGGER IF NOT EXISTS posts_fts_au
    AFTER UPDATE OF title, selftext, author, content_state ON posts
    BEGIN
        INSERT INTO posts_fts(posts_fts, rowid, title, selftext, author)
        SELECT 'delete', old.pk, old.title, old.selftext, old.author
        WHERE old.content_state = 'live';
        INSERT INTO posts_fts(rowid, title, selftext, author)
        SELECT new.pk, new.title, new.selftext, new.author
        WHERE new.content_state = 'live';
    END"""

COMMENTS_AU_UNCONDITIONAL = """CREATE TRIGGER IF NOT EXISTS comments_fts_au
    AFTER UPDATE OF body, author, content_state ON comments
    BEGIN
        INSERT INTO comments_fts(comments_fts, rowid, body, author)
        SELECT 'delete', old.pk, old.body, old.author
        WHERE old.content_state = 'live';
        INSERT INTO comments_fts(rowid, body, author)
        SELECT new.pk, new.body, new.author
        WHERE new.content_state = 'live';
    END"""


def upgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS posts_fts_au")
    op.execute("DROP TRIGGER IF EXISTS comments_fts_au")
    op.execute(POSTS_AU_GATED)
    op.execute(COMMENTS_AU_GATED)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS posts_fts_au")
    op.execute("DROP TRIGGER IF EXISTS comments_fts_au")
    op.execute(POSTS_AU_UNCONDITIONAL)
    op.execute(COMMENTS_AU_UNCONDITIONAL)
