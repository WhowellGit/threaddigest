"""Add ``runs.settings_json`` and ``runs.warnings_json``: what the run was configured with,
and which warnings made it amber.

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-17

Two gaps the first web slice exposed and stated rather than hid (``DECISIONS.md``, D-38's
follow-ups):

* the row stored only ``settings_fingerprint``, so a digest could say the settings changed
  and never which keys -- ``RunSummary.settings_changes`` was always empty;
* a warning raised through ``services.runs.RunContext.warn`` survived only as
  ``counters_json["warnings"]``, a number, so the Runs page could say three warnings made
  the run ``partial`` and name none of them.

``settings_json`` holds the resolved **non-secret** settings, the mapping
``settings.non_secret_settings()`` returns, serialized by ``settings.settings_json()`` --
the same bytes ``settings.settings_fingerprint()`` hashes, so the column and the
fingerprint beside it cannot disagree about what a setting is, and no second definition of
"secret" can appear next to the structural one. ``warnings_json`` is a list of
``{"name": ..., "detail": ...}`` objects, shaped like ``violations_json``'s list of
``{"invariant", "severity", "detail"}`` so one reader parses both the same way.

Both are nullable, and NULL is load-bearing on both: a row written before this revision
carries none, and the readers say "not recorded" rather than "nothing changed" or "no
warning" (``services/runs_view.py``, ``services/report.py``).

``batch_alter_table`` on both sides, the house pattern. It costs nothing on the upgrade:
Alembic's SQLite batch recreates the table only for operations other than ``add_column``,
so the upgrade emits two plain ``ALTER TABLE ... ADD COLUMN`` statements and ``runs`` is
never copied. The downgrade's ``drop_column`` does force the copy, and ``runs`` has two
``ON DELETE CASCADE`` children (``run_subreddits.run_pk``, ``raw_rejects.run_pk``) whose
rows the DROP would take with it if foreign keys were enforced;
``migrations/env.py::_set_foreign_keys`` issues ``PRAGMA foreign_keys=OFF`` on the raw
DBAPI connection before any transaction begins, which is what keeps them, exactly as for
revision 0002's downgrade. No view or FTS trigger references ``runs``, so the batch
checklist's drop-and-recreate step does not apply here.

Not reversible in value: ``downgrade()`` drops both columns, and the settings and warning
names they held are gone. The counter (``counters_json["warnings"]``) and the fingerprint
stay, so what the row said before this revision is what it says again.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.add_column(
            sa.Column(
                "settings_json",
                sa.Text(),
                nullable=True,
                comment=(
                    "Resolved non-secret settings as JSON, the bytes "
                    "settings_fingerprint hashes; NULL on a row written before 0005."
                ),
            )
        )
        batch.add_column(
            sa.Column(
                "warnings_json",
                sa.Text(),
                nullable=True,
                comment=(
                    "Warnings recorded by RunContext.warn as JSON [{name, detail}]; [] means "
                    "the run recorded none, NULL that it recorded nothing (a row before 0005)."
                ),
            )
        )


def downgrade() -> None:
    with op.batch_alter_table("runs") as batch:
        batch.drop_column("warnings_json")
        batch.drop_column("settings_json")
