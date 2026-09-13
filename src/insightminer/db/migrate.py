"""Alembic revision queries, the upgrade driver, and the post-restore bookkeeping.

Alembic is imported here and in ``db/schema_dump.py`` only; ``services/migrate.py`` calls
this module and never touches Alembic itself.

This module also owns the one write path that must work against a database **below head**
(:func:`finish_restored_run`). Every other statement in ``src/`` is built from the head
models in ``db/repo.py``; this one is built from bare ``sa.table`` / ``sa.column`` objects
naming only columns the restored revision is known to have, exactly as revision 0002's own
``downgrade()`` does and for the same reason: code that runs against an older file must not
import the models (design-round5 §10.2, §10.3 T12).
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory
from sqlalchemy import Engine

from insightminer.db.backup import BackupResult
from insightminer.db.schema_dump import alembic_config, migrate_to_head

__all__ = [
    "MigrationsPendingError",
    "current_revision",
    "downgrade_one",
    "finish_restored_run",
    "head_revision",
    "is_at_head",
    "pending",
    "require_head",
    "upgrade_head",
]


class MigrationsPendingError(RuntimeError):
    """The database is behind head and the caller refuses to run against it.

    The message is built here so call sites pass fields and never a string (TRY003).
    """

    def __init__(self, current: str | None, head: str, revisions: tuple[str, ...]) -> None:
        listed = ", ".join(revisions) if revisions else "(unknown)"
        super().__init__(
            f"database is at revision {current or '(none)'}, head is {head}; "
            f"pending: {listed}. Run `insightminer db upgrade`."
        )
        self.current = current
        self.head = head
        self.revisions = revisions


def _script_directory() -> ScriptDirectory:
    return ScriptDirectory.from_config(alembic_config())


def head_revision() -> str:
    """The head revision, read from the ScriptDirectory rather than from a constant.

    ``get_heads()`` rather than ``get_current_head()``: the latter is ``str | None`` and the
    ``None`` branch is unreachable while the package ships a revision, so testing it would
    need a fabricated empty ScriptDirectory. Indexing an empty tuple raises just as loudly.
    """
    return _script_directory().get_heads()[0]


def current_revision(engine: Engine) -> str | None:
    """The revision stamped in the database, or ``None`` when ``alembic_version`` is absent."""
    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def is_at_head(engine: Engine) -> bool:
    """True when the database is stamped at the head revision. No schema at all is not head."""
    return current_revision(engine) == head_revision()


def pending(engine: Engine) -> list[str]:
    """Revisions between the database's current revision and head, in upgrade order."""
    head = head_revision()
    current = current_revision(engine)
    if current == head:
        return []
    revisions = _script_directory().iterate_revisions(head, current or "base")
    return [revision.revision for revision in reversed(list(revisions))]


def upgrade_head(engine: Engine) -> None:
    """Upgrade the database behind ``engine`` to head through the Alembic API."""
    migrate_to_head(engine)


def downgrade_one(engine: Engine) -> None:
    """Step one revision back. DB-46's driver; used by tests, never by a command."""
    cfg = alembic_config()
    cfg.attributes["connection"] = engine
    command.downgrade(cfg, "-1")


def require_head(engine: Engine) -> None:
    """Raise :class:`MigrationsPendingError` unless the database is at head."""
    if is_at_head(engine):
        return
    raise MigrationsPendingError(current_revision(engine), head_revision(), tuple(pending(engine)))


# --- T12: bookkeeping inside a database that has just been restored -------------------------

#: The four ``runs`` columns T12 may touch. Deliberately not the model: the restored file is
#: at the PRE-migration revision, so a head-model write raises ``no such column`` -- which is
#: what revision 0002's ``violations_json`` did to round 4's shape.
_RESTORED_RUNS = sa.table(
    "runs", sa.column("pk"), sa.column("status"), sa.column("finished_at"), sa.column("error")
)

#: The eight ``backups`` columns T12 may touch: the six NOT NULL ones plus the two nullable
#: ones the pre-migration insert filled (``schema_rev``, ``table_counts_json``). The table's
#: only other column is the autoincrement ``pk``.
_RESTORED_BACKUPS = sa.table(
    "backups",
    sa.column("path"),
    sa.column("sha256"),
    sa.column("size_bytes"),
    sa.column("integrity"),
    sa.column("kind"),
    sa.column("created_at"),
    sa.column("schema_rev"),
    sa.column("table_counts_json"),
)


def finish_restored_run(
    engine: Engine,
    *,
    run_pk: int,
    backup: BackupResult,
    dest: Path,
    frm: str | None,
    table_counts_json: str | None,
    now: int,
) -> None:
    """T12: re-insert the ``backups`` row and close the run row inside the RESTORED file.

    Revision-independent by construction. **The column list is the contract:** this function
    may touch ``runs.pk``, ``runs.status``, ``runs.finished_at``, ``runs.error`` and the eight
    ``backups`` columns of :data:`_RESTORED_BACKUPS`, and nothing else. It writes no
    ``counters_json``, no ``api_requests`` and no ``violations_json``: the run never counted
    anything and the invariants never ran. ``runs.status='failed'`` with a non-NULL
    ``finished_at`` is what stops the row reading ``running`` forever.

    It must NEVER call ``repo.finish_run`` / ``repo.insert_backup``, which are built from the
    head models: the restored file is at the pre-migration revision, the two writes share one
    transaction, and a ``no such column`` there takes the ``backups`` row down with the run
    row -- leaving a backup file on disk that nothing points at.

    ``sa.table`` takes no types and validates nothing, which is why it survives a revision
    skew and also why a typo surfaces as ``no such column`` at runtime; the e2e test that
    fails the real 0001 -> 0002 upgrade is what catches that.

    The ``backups`` row written here is the row the pre-migration insert wrote and the
    restore rolled back, value for value, so the restored file's ``backups`` table describes
    the file on disk.
    """
    with engine.begin() as conn:
        conn.execute(
            sa.insert(_RESTORED_BACKUPS).values(
                path=str(dest),
                sha256=backup.sha256,
                size_bytes=backup.size_bytes,
                integrity=backup.integrity,
                kind="pre-migrate",
                created_at=now,
                schema_rev=frm,
                table_counts_json=table_counts_json,
            )
        )
        conn.execute(
            sa.update(_RESTORED_RUNS)
            .where(_RESTORED_RUNS.c.pk == run_pk)
            .values(
                status="failed",
                finished_at=now,
                error=f"migration failed, restored from {dest}",
            )
        )
