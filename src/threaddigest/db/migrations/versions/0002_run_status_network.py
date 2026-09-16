"""Add ``network`` to the runs.status CHECK and ``runs.violations_json``.

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-13

Not reversible in value: ``downgrade()`` rewrites ``status='network'`` rows to ``'failed'``
before restoring the narrower CHECK, because the batch copy would otherwise violate it.
``runs.error`` already carries the outage text, and ``failed`` and ``network`` share nothing
but the exit code (1 vs 5), so the rewrite loses a distinction, never a row.
``violations_json`` is dropped by the downgrade; the M2 /runs page is the only reader.

``op.f(...)`` is load-bearing on **both** sides of the swap, because ``env.py`` hands
``target_metadata`` to the migration context and Alembic therefore builds its own schema
objects under this project's ``NAMING_CONVENTION``. A bare ``"ck_runs_status"`` passed to
``create_check_constraint`` is treated as a convention *token* and emits
``CONSTRAINT status CHECK (...)``; the same bare string passed to ``drop_constraint`` is
expanded to ``ck_runs_ck_runs_status`` and raises ``ValueError: No such constraint``.
``op.f`` marks the name as already final on both.

SQLite has no ALTER for constraints, so ``batch_alter_table`` recreates ``runs``
(CREATE-new, INSERT-SELECT, DROP-old, RENAME). ``runs`` has two ``ON DELETE CASCADE``
children (``run_subreddits.run_pk``, ``raw_rejects.run_pk``), so the DROP would delete every
child row if foreign keys were enforced. ``migrations/env.py::_set_foreign_keys`` issues
``PRAGMA foreign_keys=OFF`` on the raw DBAPI connection before any transaction begins, which
is what keeps the children; ``tests/db/test_migrate_revisions.py`` asserts both halves.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: The statuses revision 0001's CHECK allows; ``network`` is what this revision adds.
_PRE_0002: tuple[str, ...] = (
    "queued",
    "running",
    "ok",
    "partial",
    "failed",
    "rate_limited",
    "skipped_locked",
    "crashed",
    "cancelled",
)


def _check(values: tuple[str, ...]) -> str:
    """Render the ``status IN (...)`` CHECK body for ``values``."""
    rendered = ", ".join(f"'{v}'" for v in values)
    return f"status IN ({rendered})"


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(
            sa.Column(
                "violations_json",
                sa.Text(),
                nullable=True,
                comment="Invariant violations as JSON; NULL when they did not run.",
            )
        )
        batch.drop_constraint(op.f("ck_runs_status"), type_="check")
        batch.create_check_constraint(op.f("ck_runs_status"), _check((*_PRE_0002, "network")))


def downgrade() -> None:
    # A lightweight table object: the migration must not import db.schema (models move, a
    # migration must not). One column is enough for the UPDATE, and it runs *before* the
    # batch recreate so the copy never sees a value the restored CHECK rejects.
    runs = sa.table("runs", sa.column("status", sa.Text))
    op.execute(sa.update(runs).where(runs.c.status == "network").values(status="failed"))
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("violations_json")
        batch.drop_constraint(op.f("ck_runs_status"), type_="check")
        batch.create_check_constraint(op.f("ck_runs_status"), _check(_PRE_0002))
