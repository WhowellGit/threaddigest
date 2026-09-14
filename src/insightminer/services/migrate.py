"""``db init`` and ``db upgrade``: the two migration lifecycles (design-round5 §10.3).

Both are **run-lifecycle commands**, not schema utilities: each takes the collector flock,
sweeps the stale rows a previous process left behind, writes a ``runs`` row, and closes it.
That is why neither is on RL-04's exclusion list and why this module depends on
``services/runs.py`` rather than only on ``db/``.

``RunContextFactory`` is the one indirection, and it is not abstraction: ``db init`` cannot
build a :class:`~insightminer.services.runs.RunContext` until the ``runs`` table exists, so
the service must create it at a point of its own choosing rather than receive one.
``db_upgrade`` calls it after the stale sweep; ``db_init`` after ``upgrade_head``.

**Directories are created before the lock is taken** (round5-findings.json P0, "lock
acquisition versus directory creation"). The flock lives at ``data/locks/collector.lock``,
and on a fresh data directory nothing has created ``data/locks/`` yet, so the documented
first command of every install would die with ``FileNotFoundError`` at step 1. Creating
directories *inside* the data dir is not a mutation of shared state, so it does not need the
lock: ``db init`` is create-the-tree then acquire, and ``db upgrade``'s tree step moves above
its lock step.

**No SQL is built here.** The post-restore bookkeeping (T12) writes into a database at the
*pre-migration* revision, so it cannot go through ``db/repo.py``'s head-model statements --
but it does not live in this module either (round5-findings.json P1): it is
``db.migrate.finish_restored_run``, built from ``sa.table``/``sa.column`` inside the ``db``
layer, and what stays here is the ``except DatabaseError`` wrap and the
exit-1 / ``restored=True`` outcome, which is where the decision belongs.

**Nothing in this module writes to stdout or stderr** (round5-findings.json panel P1, "a
services module writing to the CLI's stderr"). Both messages that used to go out through
``typer.echo`` now go through the injected :class:`~insightminer.ports.Notifier`, so
``db upgrade`` is drivable headlessly from M2's web UI without capturing stdio, and
``tests/gates/test_layering.py`` scans ``services/`` for an ``import typer`` that
import-linter's ``insightminer.*``-only contracts cannot see.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Final

import yaml
from sqlalchemy import Connection, Engine
from sqlalchemy.exc import DatabaseError

from insightminer.core.retry import RunStatus
from insightminer.db import backup as db_backup
from insightminer.db import migrate as db_migrate
from insightminer.db import repo
from insightminer.db.backup import TIMESTAMP_FORMAT, BackupResult
from insightminer.db.engine import db_path_for, engine_for
from insightminer.ports import Clock, Notifier
from insightminer.services import lock, runs, seed
from insightminer.settings import Settings

__all__ = [
    "DATA_SUBDIRECTORIES",
    "KEEP_PRE_MIGRATE_BACKUPS",
    "DatabaseMissingError",
    "MigrationOutcome",
    "PruneOutcome",
    "RunContextFactory",
    "backups_dir",
    "create_data_tree",
    "database_missing_message",
    "db_current",
    "db_init",
    "db_upgrade",
    "prune_pre_migrate_backups",
]

#: Created under ``settings.data_dir`` before either lifecycle takes the lock.
DATA_SUBDIRECTORIES: Final[tuple[str, ...]] = ("backups", "locks", "logs")

#: How many ``pre-migrate`` backups survive a successful upgrade (§10.3 step 12).
KEEP_PRE_MIGRATE_BACKUPS: Final = 3

_PRE_MIGRATE: Final = "pre-migrate"

type RunContextFactory = Callable[[Engine, str], runs.RunContext]


def database_missing_message(db_path: Path) -> str:
    """§8's sentence for "the database file does not exist", spelled once.

    ``cli.run`` (§11.3 step 4) and ``db upgrade`` (below) must not disagree about it: an
    operator who reaches the precondition from either command has the same next action, and
    ``tests/e2e/test_db_commands.py`` asserts the two sentences are the same string.
    """
    return f"no database at {db_path}; run: insightminer db init"


class DatabaseMissingError(RuntimeError):
    """``db upgrade`` was asked to migrate a database that is not there.

    §8 maps it to exit **78** with no run row, and ``cli`` re-raises it as its ``ConfigError``.
    Before it existed, ``_upgrade_locked`` called ``ctx_factory`` first: ``engine_for`` created
    a 0-byte ``insightminer.db``, ``repo.insert_run`` died with ``no such table: runs`` as an
    uncaught traceback, and the phantom database it left behind made every retry -- and the
    next ``run`` -- report the wrong problem (round5-findings.json panel P0).

    The message is built here, so call sites pass the path and never a string (TRY003).
    """

    def __init__(self, db_path: Path) -> None:
        super().__init__(database_missing_message(db_path))
        self.db_path = db_path


@dataclass(frozen=True, slots=True)
class PruneOutcome:
    """What :func:`prune_pre_migrate_backups` decided, for a caller that has committed.

    ``unlink`` are the files whose ``backups`` rows this call deleted -- the caller removes
    them **after** its transaction commits. ``skipped`` are rows whose recorded path does not
    resolve under the backups directory: left entirely alone, row and file, and reported.
    """

    unlink: tuple[Path, ...]
    skipped: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class MigrationOutcome:
    """What one lifecycle did. ``restored=True`` and ``migrated=False`` is the failure shape:
    the database is back at ``from_revision`` and the backup on disk is what it came from."""

    from_revision: str | None
    to_revision: str
    migrated: bool
    backup_path: Path | None
    backup_sha256: str | None
    restored: bool
    error: str | None


# --- shared plumbing --------------------------------------------------------------------------


def _lock_path(settings: Settings) -> Path:
    return settings.data_dir / "locks" / "collector.lock"


def create_data_tree(data_dir: Path) -> None:
    """Create ``data/`` and its three subdirectories. Runs **before** the lock decision.

    Public because ``cli.run`` needs the same tree before ITS lock decision (§11.3's step
    between 4 and 5, round5-findings.json P0 "lock acquisition versus directory creation"):
    two concrete callers, one function, and no second spelling of the subdirectory list."""
    data_dir.mkdir(parents=True, exist_ok=True)
    for name in DATA_SUBDIRECTORIES:
        (data_dir / name).mkdir(parents=True, exist_ok=True)


def _sweep_stale(
    engine: Engine, *, settings: Settings, clock: Clock, this_run_pk: int | None = None
) -> runs.StaleSweep:
    """T1, inside the lock -- the same rules ``run`` applies (§12.2).

    ``this_run_pk`` is ``None`` in ``db init``, which sweeps before ``start_run``. ``db
    upgrade`` sweeps **after** the schema reaches head and therefore passes its own run pk, so
    §12.2 clause 4 ("a ``running`` row carrying our own pid belongs to a run that is already
    over") cannot condemn the row this very command just wrote. The parameter exists for
    exactly this: ``sweep_stale``'s docstring says it is there so the function stays callable
    from a second point without skipping a row by accident.

    **Why ``db upgrade`` cannot sweep at §10.3's step 2.** ``repo.stale_candidates`` issues
    ``SELECT <every runs column>``, built from the head models, and ``db upgrade`` by
    definition opens a database *below* head: against revision 0001 the read dies with
    ``no such column: runs.violations_json`` before the backup is even taken. That is the same
    head-model-versus-older-file trap round 5's P1-2 found in T12, reached from the read side;
    the sweep moves to the first point where the file really is at head.
    """
    with engine.begin() as conn:
        return runs.sweep_stale(
            conn,
            now=clock.now(),
            this_pid=os.getpid(),
            this_run_pk=this_run_pk,
            stale_after_seconds=settings.static.run.stale_after_minutes * 60,
        )


def _table_counts_json(engine: Engine) -> str:
    """The tracked-table counts recorded alongside a backup, so a cascade that eats rows is
    detectable after the fact as well as before it (§10.3 step 8)."""
    with engine.connect() as conn:
        counts = repo.table_counts(conn, runs.TRACKED_TABLES)
    return json.dumps(counts, sort_keys=True, separators=(",", ":"))


def backups_dir(settings: Settings) -> Path:
    """``<data_dir>/backups``: where every backup this build writes lives, spelled once.

    Public because it is also the containment test :func:`prune_pre_migrate_backups` applies
    to a recorded path before unlinking it, and the two must not be able to disagree.
    """
    return settings.data_dir / "backups"


def _backup_destination(settings: Settings, *, frm: str | None, to: str, now: int) -> Path:
    stamp = datetime.fromtimestamp(now, UTC).strftime(TIMESTAMP_FORMAT)
    return backups_dir(settings) / f"{_PRE_MIGRATE}-{frm or 'none'}-{to}-{stamp}.db"


def _remove_backup_file(path: Path) -> None:
    for candidate in (path, *(path.with_name(path.name + s) for s in db_backup.BACKUP_SUFFIXES)):
        candidate.unlink(missing_ok=True)


def _record_skipped_locked(settings: Settings, clock: Clock, notifier: Notifier) -> None:
    """Best-effort ``skipped_locked`` row for a refused ``db upgrade`` (§10.3 step 1).

    Guarded twice. No database file means there is nothing to write into, and a
    ``DatabaseError`` here is the expected shape when the holder is mid-migration -- the
    caller still raises :class:`~insightminer.services.lock.LockHeldError`, so the operator
    sees the same exit 75 either way and nothing is swallowed silently.

    The failure goes out through the injected ``notifier``, never ``typer.echo``: a service
    that writes to the CLI's stderr is invisible to M2's web UI and unusable headlessly
    (round5-findings.json panel P1).
    """
    db_path = db_path_for(settings.data_dir)
    if not db_path.is_file():
        return
    engine = engine_for(db_path)
    now = clock.now()
    try:
        with engine.begin() as conn:
            repo.insert_run(
                conn,
                repo.RunInsert(
                    kind="db_upgrade",
                    trigger="cli",
                    status=RunStatus.SKIPPED_LOCKED.value,
                    created_at=now,
                    started_at=None,
                    pid=os.getpid(),
                    stage=None,
                    options_json=None,
                    app_version=None,
                    praw_version=None,
                    schema_rev=None,
                    settings_fingerprint=None,
                    log_path=None,
                ),
            )
    except DatabaseError as exc:
        notifier.notify(
            "error",
            f"the collector lock is held and the attempt could not be recorded "
            f"({exc.__class__.__name__})",
        )
    finally:
        engine.dispose()


def prune_pre_migrate_backups(
    conn: Connection, *, home: Path, keep: int = KEEP_PRE_MIGRATE_BACKUPS
) -> PruneOutcome:
    """Delete the ``backups`` rows of all but the newest ``keep`` ``pre-migrate`` copies.

    **Rows here, files afterwards** (panel P2-7b / finding 12). The rows are deleted in the
    caller's transaction; the files are *not* touched. Their paths come back on
    :class:`PruneOutcome` and the caller unlinks them once that transaction has committed,
    because ``unlink`` is not transactional: the old ordering deleted the file first, so a
    rollback -- or any failure between the two statements -- left a ``backups`` row pointing
    at a restore target that no longer existed. The reverse order can only ever leave a file
    with no row, which is recoverable and visible, rather than a row with no file.

    **Nothing outside ``home`` is ever unlinked** (panel P2-7a). ``home`` is
    :func:`backups_dir`; a recorded path that does not resolve under it -- a hand-edited row,
    a restored database carrying another machine's absolute paths, a symlink out of the tree
    -- is left completely alone, row and file, and returned in ``skipped`` for the caller to
    report. A pruner that unlinks whatever a row names is a delete primitive pointed at an
    untrusted string.
    """
    rows = repo.backups_of_kind(conn, _PRE_MIGRATE)  # newest first
    resolved_home = home.resolve()
    doomed: list[tuple[int, Path]] = []
    skipped: list[Path] = []
    for pk, path, _created_at in rows[keep:]:
        candidate = Path(path)
        if candidate.resolve().is_relative_to(resolved_home):
            doomed.append((pk, candidate))
        else:
            skipped.append(candidate)
    repo.delete_backups(conn, [pk for pk, _path in doomed])
    return PruneOutcome(unlink=tuple(path for _pk, path in doomed), skipped=tuple(skipped))


# --- db upgrade (§10.3) ------------------------------------------------------------------------


def db_upgrade(
    ctx_factory: RunContextFactory, *, settings: Settings, clock: Clock, notifier: Notifier
) -> MigrationOutcome:
    """Back up, migrate, verify, and restore on failure.

    The directory tree is created **before** the lock decision (round5-findings.json P0): the
    lock file lives inside the tree, so the old ordering could not reach its own step 1.
    """
    create_data_tree(settings.data_dir)
    try:
        with lock.acquire(_lock_path(settings)):
            return _upgrade_locked(ctx_factory, settings=settings, clock=clock, notifier=notifier)
    except lock.LockHeldError:
        _record_skipped_locked(settings, clock, notifier)
        raise


def _upgrade_locked(
    ctx_factory: RunContextFactory, *, settings: Settings, clock: Clock, notifier: Notifier
) -> MigrationOutcome:
    """The two preconditions come **before** ``engine_for`` and ``ctx_factory``.

    Neither may write a run row, and the first may not even open an engine:
    ``engine_for`` creates the file it is pointed at, so a typo'd ``INSIGHTMINER_DATA_DIR``
    or a ``db upgrade`` run before ``db init`` used to leave a 0-byte phantom database behind
    and die inside ``repo.insert_run`` with ``no such table: runs``
    (round5-findings.json panel P0). The second refuses a file stamped *ahead* of this build
    before a backup is taken, because nothing in steps 6-13 can succeed against it
    (panel P1, ``_migrate_and_verify``).
    """
    db_path = db_path_for(settings.data_dir)
    if not db_path.is_file():
        raise DatabaseMissingError(db_path)
    engine = engine_for(db_path)
    try:
        db_migrate.require_known_revision(engine)
        ctx = ctx_factory(engine, "db_upgrade")
        runs.heartbeat(ctx, stage="upgrade:backup")
        frm = db_migrate.current_revision(engine)
        to = db_migrate.head_revision()
        if frm == to:
            # Nothing pending: no backup is taken, and the run row still records the attempt.
            _sweep_stale(engine, settings=settings, clock=clock, this_run_pk=ctx.run_pk)
            runs.finish_run_from(ctx, status=RunStatus.OK, violations_json=None, error=None)
            return MigrationOutcome(
                from_revision=frm,
                to_revision=to,
                migrated=False,
                backup_path=None,
                backup_sha256=None,
                restored=False,
                error=None,
            )
        return _upgrade_with_backup(
            ctx,
            engine=engine,
            db_path=db_path,
            settings=settings,
            clock=clock,
            notifier=notifier,
            frm=frm,
            to=to,
        )
    finally:
        engine.dispose()


def _upgrade_with_backup(
    ctx: runs.RunContext,
    *,
    engine: Engine,
    db_path: Path,
    settings: Settings,
    clock: Clock,
    notifier: Notifier,
    frm: str | None,
    to: str,
) -> MigrationOutcome:
    dest = _backup_destination(settings, frm=frm, to=to, now=clock.now())
    backup = db_backup.online_backup(db_path, dest)
    verdict = db_backup.quick_check(dest)
    if verdict != "ok":
        # Step 7: abort BEFORE migrating, and take the unusable copy with us so nothing on
        # disk looks like a backup that could be restored from.
        _remove_backup_file(dest)
        error = f"backup verification failed: {verdict}"
        # The database is still BELOW head here, so the run row is closed through
        # `db.migrate`, never `repo.finish_run` (round5-findings.json P1): the head models
        # write `violations_json`, which revision 0001 does not have.
        db_migrate.finish_below_head_run(
            engine,
            run_pk=ctx.run_pk,
            status=RunStatus.FAILED.value,
            finished_at=clock.now(),
            error=error,
        )
        notifier.notify("error", error)
        return MigrationOutcome(
            from_revision=frm,
            to_revision=to,
            migrated=False,
            backup_path=None,
            backup_sha256=None,
            restored=False,
            error=error,
        )
    counts_json = _table_counts_json(engine)
    with engine.begin() as conn:  # T10, in the LIVE database
        repo.insert_backup(
            conn,
            repo.BackupInsert(
                path=str(dest),
                sha256=backup.sha256,
                size_bytes=backup.size_bytes,
                integrity=backup.integrity,
                kind=_PRE_MIGRATE,
                created_at=clock.now(),
                schema_rev=frm,
                table_counts_json=counts_json,
            ),
        )
    runs.heartbeat(ctx, stage=f"upgrade:{frm}->{to}")
    failure = _migrate_and_verify(engine, db_path)
    if failure is not None:
        return _restore(
            ctx,
            engine=engine,
            db_path=db_path,
            dest=dest,
            backup=backup,
            frm=frm,
            to=to,
            counts_json=counts_json,
            clock=clock,
            notifier=notifier,
            failure=failure,
        )
    # At head at last: `repo`'s head-model statements are legal again, so the stale sweep
    # and the ordinary `finish_run` happen here (see `_sweep_stale`'s docstring).
    _sweep_stale(engine, settings=settings, clock=clock, this_run_pk=ctx.run_pk)
    with engine.begin() as conn:
        pruned = prune_pre_migrate_backups(conn, home=backups_dir(settings))
    # Outside the `with`: the rows are committed, so an unlink can no longer be rolled back
    # out from under a deleted file (panel P2-7b).
    for stale_backup in pruned.unlink:
        _remove_backup_file(stale_backup)
    for outsider in pruned.skipped:
        notifier.notify(
            "warning",
            f"backups row points outside {backups_dir(settings)}: {outsider} was not pruned",
        )
    runs.finish_run_from(ctx, status=RunStatus.OK, violations_json=None, error=None)
    return MigrationOutcome(
        from_revision=frm,
        to_revision=to,
        migrated=True,
        backup_path=dest,
        backup_sha256=backup.sha256,
        restored=False,
        error=None,
    )


def _migrate_and_verify(engine: Engine, db_path: Path) -> str | None:
    """Steps 9-10: upgrade, then ``integrity_check`` **and** ``foreign_key_check`` on the live
    file. Returns the failure sentence, or ``None`` when the migration stands.

    Both post-checks are equally decisive: a migration that leaves an orphan child row has
    lost data just as surely as one that leaves a malformed page, and 0002's batch recreate
    is exactly the shape that could do it (§10.4).

    **Three failure classes, not one** (round5-findings.json panel P1). Round 5 caught only
    ``DatabaseError``, so an Alembic scripting failure -- reproduced with a database stamped
    ``0009_future``: ``CommandError: Can't locate revision`` -- escaped ``db_upgrade``
    uncaught: no ``MigrationOutcome``, no restore, the run row left ``running``, and a
    full-size pre-migrate backup left on disk per attempt, because step 12's prune only runs
    on success. ``db.migrate.upgrade_head`` now re-raises ``CommandError`` as
    :class:`~insightminer.db.migrate.MigrationFailedError`, and ``OSError`` covers a disk or
    permission failure mid-script. It is deliberately **not** ``except Exception``: §8's first
    unsoftenable rule is "never a bare ``except Exception``", and the suppression ratchet
    counts the ``noqa: BLE001`` one would need.
    """
    try:
        db_migrate.upgrade_head(engine)
    except (DatabaseError, db_migrate.MigrationFailedError, OSError) as exc:
        return f"migration raised {exc.__class__.__name__}: {exc}"
    integrity = db_backup.integrity_check(db_path)
    if integrity != "ok":
        return f"integrity_check after migration: {integrity}"
    violations = db_backup.foreign_key_check(db_path)
    if violations:
        return f"foreign_key_check after migration: {'; '.join(violations)}"
    return None


def _restore(
    ctx: runs.RunContext,
    *,
    engine: Engine,
    db_path: Path,
    dest: Path,
    backup: BackupResult,
    frm: str | None,
    to: str,
    counts_json: str,
    clock: Clock,
    notifier: Notifier,
    failure: str,
) -> MigrationOutcome:
    """Step 11: swap the pre-migration copy back and close the run row inside it (T12).

    The run row survives the restore because it was committed before the backup was taken
    (§7 T9), so it is in the copy, under its original pk. The bookkeeping itself is
    ``db.migrate.finish_restored_run`` -- revision-independent, and in the ``db`` layer where
    statement construction belongs (round5-findings.json P1).

    ``restored=True`` and exit 1 are reported on **both** paths: the restore is the thing the
    operator must know about, and the bookkeeping failing on top of it is a second sentence,
    not a different outcome. A ``running`` row left in the restored file is stamped
    ``crashed`` by the next run (§12.2).

    **The second sentence is carried on the outcome, not only echoed** (round5-findings.json
    panel P1). When ``finish_restored_run`` fails, the backup file exists with no ``backups``
    row to point at it: ``prune_pre_migrate_backups`` reads ``repo.backups_of_kind``, so an
    unreferenced file is never counted against :data:`KEEP_PRE_MIGRATE_BACKUPS` and never
    deleted. An outcome whose ``error`` said only "restored from …" reported that as a clean
    restore; it now names the bookkeeping failure so the printed exit-1 block carries both
    sentences and a later reconcile has something to match the orphan file against.
    """
    engine.dispose()
    db_backup.restore(dest, db_path)
    restored_engine = engine_for(db_path)
    error = f"migration failed, restored from {dest}"
    try:
        db_migrate.finish_restored_run(
            restored_engine,
            run_pk=ctx.run_pk,
            backup=backup,
            dest=dest,
            frm=frm,
            table_counts_json=counts_json,
            now=clock.now(),
        )
    except DatabaseError as exc:
        error = (
            f"{error}; the restored database could not be updated "
            f"({exc.__class__.__name__}): its run row is still `running` and {dest} has no "
            f"`backups` row, so it will not be pruned"
        )
    finally:
        restored_engine.dispose()
    notifier.notify("error", f"{failure}; {error}")
    return MigrationOutcome(
        from_revision=frm,
        to_revision=to,
        migrated=False,
        backup_path=dest,
        backup_sha256=backup.sha256,
        restored=True,
        error=error,
    )


# --- db init (§10.3) ---------------------------------------------------------------------------


def db_init(
    ctx_factory: RunContextFactory, *, settings: Settings, clock: Clock, notifier: Notifier
) -> MigrationOutcome:
    """Create the tree, take the lock, bring the schema to head, sweep, seed, record.

    Idempotent, **not** a no-op: a second ``db init`` still takes the lock, still sweeps stale
    rows and still writes a run row, so it needs no RL-04 exclusion and a repeat is a
    recorded, harmless event rather than an unexplained silence.

    No ``skipped_locked`` row when the lock is held: there may be no schema to write it into,
    and a command whose lock behaviour depends on whether a file exists is worse than one
    that always prints the reason. The exit code is unchanged.
    """
    create_data_tree(settings.data_dir)  # before the lock: the lock file lives inside the tree
    with lock.acquire(_lock_path(settings)):
        return _init_locked(ctx_factory, settings=settings, clock=clock, notifier=notifier)


def _revisions_for_init(engine: Engine) -> tuple[str | None, str]:
    """``(current, head)``, refusing a database that is **behind** head.

    ``init`` must never migrate without a backup -- that is ``db upgrade``'s job, and the
    refusal happens before any run row is written.
    """
    current = db_migrate.current_revision(engine)
    head = db_migrate.head_revision()
    if current is not None and current != head:
        raise db_migrate.MigrationsPendingError(current, head, tuple(db_migrate.pending(engine)))
    return current, head


def _init_locked(
    ctx_factory: RunContextFactory, *, settings: Settings, clock: Clock, notifier: Notifier
) -> MigrationOutcome:
    engine = engine_for(db_path_for(settings.data_dir))
    try:
        frm, to = _revisions_for_init(engine)
        db_migrate.upgrade_head(engine)
        # Step 5: the earliest point at which `runs` is guaranteed to exist, still inside the
        # lock -- which is what makes "stale rows are swept" total over all three run kinds.
        _sweep_stale(engine, settings=settings, clock=clock)
        ctx = ctx_factory(engine, "db_init")
        _seed(ctx, clock=clock, notifier=notifier)
        runs.finish_run_from(ctx, status=RunStatus.OK, violations_json=None, error=None)
        return MigrationOutcome(
            from_revision=frm,
            to_revision=to,
            migrated=frm != to,
            backup_path=None,
            backup_sha256=None,
            restored=False,
            error=None,
        )
    finally:
        engine.dispose()


def _seed(ctx: runs.RunContext, *, clock: Clock, notifier: Notifier) -> None:
    """T14: every seeded source, or none. A failure closes the run row ``failed`` and
    re-raises, so the database is at head with no sources and the next ``db init`` finishes
    the job.

    ``yaml.YAMLError`` is in the tuple because ``seed.apply_seed`` parses ``config/seed.yaml``
    (panel P2-10): a seed file with a syntax error -- the ordinary way a hand-edited YAML
    fails -- raised straight past this handler, so ``db init`` left its run row ``running``
    forever and the next one condemned it as ``crashed``. ``TypeError`` already covered the
    *structural* half (a file that parses but is not a mapping of strings); this is the half
    that never parses at all. Still four named classes, never ``except Exception`` (§8).
    """
    try:
        with ctx.engine.begin() as conn:
            seed.apply_seed(conn, workspace_pk=ctx.workspace_pk, now=clock.now())
    except (DatabaseError, OSError, TypeError, yaml.YAMLError) as exc:
        error = f"seed failed: {exc.__class__.__name__}: {exc}"
        runs.finish_run_from(ctx, status=RunStatus.FAILED, violations_json=None, error=error)
        notifier.notify("error", error)
        raise


# --- db current ---------------------------------------------------------------------------------


def db_current(*, settings: Settings) -> tuple[str | None, str]:
    """``(current revision, head revision)``. Reads nothing into existence: a data directory
    with no database file reports ``None`` rather than having one created for it."""
    db_path = db_path_for(settings.data_dir)
    head = db_migrate.head_revision()
    if not db_path.is_file():
        return None, head
    engine = engine_for(db_path)
    try:
        return db_migrate.current_revision(engine), head
    finally:
        engine.dispose()
