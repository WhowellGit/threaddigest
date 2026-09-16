"""``services/migrate.py``: the two run-lifecycle migration commands, ``db init`` and
``db upgrade`` (design-round5.md §2.1, §3.3, §7 T9-T14, §10.3, §18.6, round5-findings.json
finding 5 / T12).

``services/migrate.py`` does not exist yet -- every test here is expected to fail on
``ModuleNotFoundError`` until step 6 implements it.

Both lifecycles are run-lifecycle commands (§10.3: "``db_upgrade`` and ``db_init`` are
run-lifecycle commands"), so they take the same ``RunContextFactory`` shape ``cli`` will pass
in step 7: ``lambda engine, kind: runs.start_run(engine, kind=kind, trigger=trigger,
clock=clock, settings=settings)``. Exit-code mapping (78/75/1) is a ``cli``-layer concern for
step 7; these tests assert the service-level contract only: what ``MigrationOutcome`` reports,
what lands in the database and on disk, and which exception propagates for the lock and the
behind-head cases.

**Db path convention.** Neither ``Settings`` nor any shipped module names the database file's
path yet (grep confirms it): these tests assume the same one
``tests/services/conftest.py`` / ``tests/db/conftest.py`` already use for a bare temp
database -- ``threaddigest.db`` -- placed under ``settings.data_dir``, i.e.
``settings.data_dir / "threaddigest.db"``. ``tests/services/test_doctor.py`` makes the same
assumption, for the same reason: it is the one path a real ``threaddigest`` invocation would
resolve to from ``settings.data_dir`` alone.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
import sqlalchemy as sa
import yaml
from sqlalchemy import Connection, Engine, select
from sqlalchemy.exc import OperationalError

from threaddigest.adapters.clock import FakeClock
from threaddigest.adapters.notify import FakeNotifier
from threaddigest.db import backup as db_backup
from threaddigest.db import migrate as db_migrate
from threaddigest.db import repo
from threaddigest.db.engine import engine_for
from threaddigest.db.schema import Base
from threaddigest.db.schema_dump import migrate_to_head
from threaddigest.services import lock, runs, seed
from threaddigest.services import migrate as migrate_service
from threaddigest.settings import Settings

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "db"
FIXTURE_0001 = FIXTURES_DIR / "0001.sqlite"


# --- local db_path: inside settings.data_dir, matching the convention documented above --------


@pytest.fixture
def db_path(settings: Settings) -> Path:
    return settings.data_dir / "threaddigest.db"


@pytest.fixture
def lock_path(settings: Settings) -> Path:
    return settings.data_dir / "locks" / "collector.lock"


CtxFactory = Callable[[Engine, str], runs.RunContext]


@pytest.fixture
def ctx_factory(clock: FakeClock, settings: Settings) -> CtxFactory:
    """Exactly what ``cli`` passes in step 7 (§10.3): the indirection ``db init`` needs
    because the ``runs`` table does not exist until after its own schema is created."""

    def _factory(engine: Engine, kind: str) -> runs.RunContext:
        return runs.start_run(engine, kind=kind, trigger="cli", clock=clock, settings=settings)

    return _factory


def _seed_at_revision_0001(db_path: Path) -> None:
    """Put the seeded rev-0001 fixture (with populated ``runs``/``run_subreddits``/
    ``raw_rejects`` -- §10.4) at ``db_path``, behind head."""
    assert FIXTURE_0001.is_file()
    shutil.copyfile(FIXTURE_0001, db_path)


def _read_runs(db_path: Path) -> list[dict[str, object]]:
    """Every ``runs`` row, oldest first, read through a fresh engine (never the live one a
    restore just swapped out from under).

    **Four named columns, not ``select(table)``.** After a failed upgrade the file is back at
    revision **0001**, which has no ``runs.violations_json``; ``select(table)`` is built from
    the *head* models and dies with ``no such column`` -- the same head-model-versus-older-file
    trap round 5's P1-2 found in T12, reached from the read side. ``pk``/``kind``/``status``/
    ``finished_at`` exist in every revision, and they are all any test here reads.
    """
    engine = engine_for(db_path)
    try:
        table = Base.metadata.tables["runs"]
        with engine.connect() as conn:
            rows = (
                conn.execute(
                    select(table.c.pk, table.c.kind, table.c.status, table.c.finished_at).order_by(
                        table.c.pk
                    )
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]
    finally:
        engine.dispose()


# --- db upgrade: DB-37 -------------------------------------------------------------------------


def test_backup_precedes_migration_and_records_a_row(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    _seed_at_revision_0001(db_path)

    outcome = migrate_service.db_upgrade(
        ctx_factory, settings=settings, clock=clock, notifier=notifier
    )

    assert outcome.from_revision == "0001"
    assert outcome.to_revision == db_migrate.head_revision()
    assert outcome.migrated is True
    assert outcome.restored is False
    assert outcome.error is None
    assert outcome.backup_path is not None
    assert outcome.backup_path.is_file()
    assert outcome.backup_sha256 == db_backup.sha256_of(outcome.backup_path)
    # Asserted before this test runs its own `quick_check`, which re-creates the pair: the
    # command's verification opens the copy read-only (panel P2-9) and cannot delete the
    # empty `-wal`/`-shm` it needs, so `db upgrade` tidies them. A sidecar beside a backup
    # file is what `db_backup.restore` treats as a corrupt database.
    assert not any(
        outcome.backup_path.with_name(outcome.backup_path.name + suffix).exists()
        for suffix in db_backup.BACKUP_SUFFIXES
    ), "db upgrade left a WAL sidecar beside the pre-migration backup"
    assert db_backup.quick_check(outcome.backup_path) == "ok"

    engine = engine_for(db_path)
    try:
        assert db_migrate.is_at_head(engine)
        with engine.connect() as conn:
            backups = repo.backups_of_kind(conn, "pre-migrate")
    finally:
        engine.dispose()
    assert len(backups) == 1
    _, path, _ = backups[0]
    assert path == str(outcome.backup_path)


def test_quick_check_failure_aborts_before_migrating(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§10.3 step 7: a non-``"ok"`` ``quick_check`` on the fresh backup removes the partial
    file and finishes the run failed **before** ``upgrade_head`` is ever called -- the live
    database must be untouched, at its original revision, with no ``backups`` row."""
    _seed_at_revision_0001(db_path)
    monkeypatch.setattr(db_backup, "quick_check", lambda _path: "database disk image is malformed")

    outcome = migrate_service.db_upgrade(
        ctx_factory, settings=settings, clock=clock, notifier=notifier
    )

    assert outcome.migrated is False
    assert outcome.restored is False
    assert outcome.error is not None

    engine = engine_for(db_path)
    try:
        assert db_migrate.current_revision(engine) == "0001"
        with engine.connect() as conn:
            assert repo.backups_of_kind(conn, "pre-migrate") == []
    finally:
        engine.dispose()
    assert list((settings.data_dir / "backups").glob("pre-migrate-*")) == []


def test_post_checks_run_after_upgrade(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§10.3 step 10: ``foreign_key_check`` on the LIVE database after a real ``upgrade_head``
    is what decides success -- planting a violation here proves the check actually runs and
    is actually consulted, not merely that the Alembic migration itself succeeded."""
    _seed_at_revision_0001(db_path)
    monkeypatch.setattr(
        db_backup,
        "foreign_key_check",
        lambda _path: ["('run_subreddits', 1, 'runs', 1)"],
    )

    outcome = migrate_service.db_upgrade(
        ctx_factory, settings=settings, clock=clock, notifier=notifier
    )

    assert outcome.migrated is False
    assert outcome.restored is True
    assert outcome.error is not None
    assert "restored from" in outcome.error

    rows = _read_runs(db_path)
    upgrade_rows = [row for row in rows if row["kind"] == "db_upgrade"]
    assert len(upgrade_rows) == 1
    assert upgrade_rows[0]["status"] == "failed"
    assert upgrade_rows[0]["finished_at"] is not None

    engine = engine_for(db_path)
    try:
        assert db_migrate.current_revision(engine) == "0001"
        with engine.connect() as conn:
            assert len(repo.backups_of_kind(conn, "pre-migrate")) == 1
    finally:
        engine.dispose()


# --- db upgrade: DB-38 service half (restore-on-failure, keep-last-3) --------------------------


def test_a_failed_integrity_check_also_restores(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The other §10.3 step-10 post-check: ``integrity_check`` failing restores exactly like
    a ``foreign_key_check`` failure does -- both are named as equally decisive."""
    _seed_at_revision_0001(db_path)
    monkeypatch.setattr(
        db_backup, "integrity_check", lambda _path: "database disk image is malformed"
    )

    outcome = migrate_service.db_upgrade(
        ctx_factory, settings=settings, clock=clock, notifier=notifier
    )

    assert outcome.restored is True
    assert outcome.migrated is False
    engine = engine_for(db_path)
    try:
        assert db_migrate.current_revision(engine) == "0001"
    finally:
        engine.dispose()


def _plant_backup(conn: Connection, path: Path, *, created_at: int) -> Path:
    """One ``pre-migrate`` file on disk and its ``backups`` row, through ``repo`` only."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not a real sqlite file")
    repo.insert_backup(
        conn,
        repo.BackupInsert(
            path=str(path),
            sha256=f"sha-{path.name}",
            size_bytes=1,
            integrity="ok",
            kind="pre-migrate",
            created_at=created_at,
            schema_rev="0001",
            table_counts_json=None,
        ),
    )
    return path


def _backup_paths(engine: Engine) -> set[str]:
    with engine.connect() as conn:
        return {path for _pk, path, _created_at in repo.backups_of_kind(conn, "pre-migrate")}


def test_prune_pre_migrate_backups_deletes_the_rows_and_returns_the_files(
    db_path: Path, settings: Settings, now: int
) -> None:
    """§10.3 step 12, with the row/file order the panel's P2-7b and finding 12 require.

    The call deletes the two oldest **rows** and hands their paths back; the files are still
    on disk when it returns, because ``unlink`` cannot be rolled back and the caller has not
    committed yet. Unlinking them is the caller's step, asserted here in the order
    ``_upgrade_with_backup`` performs it.
    """
    engine = engine_for(db_path)
    try:
        migrate_to_head(engine)
        home = migrate_service.backups_dir(settings)
        with engine.begin() as conn:
            paths = [
                _plant_backup(conn, home / f"pre-migrate-000{i}.db", created_at=now + i)
                for i in range(5)
            ]

        with engine.begin() as conn:
            pruned = migrate_service.prune_pre_migrate_backups(conn, home=home, keep=3)

        assert sorted(pruned.unlink) == sorted(paths[:2])
        assert pruned.skipped == ()
        assert all(path.exists() for path in paths), "prune must not unlink inside the transaction"
        assert _backup_paths(engine) == {str(p) for p in paths[2:]}

        for path in pruned.unlink:  # the caller's post-commit half
            path.unlink()
        assert [path.exists() for path in paths] == [False, False, True, True, True]
    finally:
        engine.dispose()


def test_prune_leaves_a_backup_row_pointing_outside_the_backups_directory_alone(
    db_path: Path, settings: Settings, tmp_path: Path, now: int
) -> None:
    """Panel P2-7a: the pruner must never unlink whatever a row happens to name.

    A ``backups`` row is an untrusted string -- hand-edited, restored from another machine's
    absolute paths, or pointing through a symlink out of the tree. Before this, the oldest
    such row's file was unlinked wherever it was. Now the row is left alone *entirely* (the
    row too, so the operator can still see it) and reported on ``skipped``.
    """
    engine = engine_for(db_path)
    try:
        migrate_to_head(engine)
        home = migrate_service.backups_dir(settings)
        outsider = tmp_path / "elsewhere" / "precious.db"
        with engine.begin() as conn:
            _plant_backup(conn, outsider, created_at=now)  # oldest => first to be pruned
            inside = [
                _plant_backup(conn, home / f"pre-migrate-000{i}.db", created_at=now + 1 + i)
                for i in range(3)
            ]

        with engine.begin() as conn:
            pruned = migrate_service.prune_pre_migrate_backups(conn, home=home, keep=3)

        assert pruned.unlink == ()
        assert pruned.skipped == (outsider,)
        assert outsider.exists(), "a file outside the backups directory was unlinked"
        assert _backup_paths(engine) == {str(outsider), *(str(p) for p in inside)}
    finally:
        engine.dispose()


def test_a_rolled_back_prune_leaves_no_dangling_backup_rows(
    db_path: Path, settings: Settings, now: int
) -> None:
    """Panel P2-7b / finding 12, the failure the ordering is about.

    ``unlink`` is not transactional. With the files deleted first, a transaction that rolled
    back afterwards -- a locked database, a crash between the two statements -- restored the
    ``backups`` rows and left them pointing at restore targets that no longer existed. With
    the order reversed the worst case is a file with no row, which ``doctor`` can see and an
    operator can delete. Here: roll back after the prune and every row and every file is
    still there.
    """
    engine = engine_for(db_path)
    try:
        migrate_to_head(engine)
        home = migrate_service.backups_dir(settings)
        with engine.begin() as conn:
            paths = [
                _plant_backup(conn, home / f"pre-migrate-000{i}.db", created_at=now + i)
                for i in range(5)
            ]

        with engine.connect() as conn:
            transaction = conn.begin()
            pruned = migrate_service.prune_pre_migrate_backups(conn, home=home, keep=3)
            transaction.rollback()

        assert sorted(pruned.unlink) == sorted(paths[:2])
        assert _backup_paths(engine) == {str(p) for p in paths}, "the rollback left rows deleted"
        assert all(path.exists() for path in paths), "a rolled-back prune destroyed a file"
    finally:
        engine.dispose()


def test_db_upgrade_with_nothing_pending_is_a_no_op_but_still_records_a_run(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    """§10.3 step 5: equal revisions ⇒ ``migrated=False``, no backup, ``finish_run`` ``ok``.
    The run row still exists -- RL-04 is about taking the lock and recording the attempt."""
    engine = engine_for(db_path)
    try:
        migrate_to_head(engine)
    finally:
        engine.dispose()

    outcome = migrate_service.db_upgrade(
        ctx_factory, settings=settings, clock=clock, notifier=notifier
    )

    assert outcome.migrated is False
    assert outcome.backup_path is None
    assert outcome.restored is False
    assert outcome.error is None
    rows = [row for row in _read_runs(db_path) if row["kind"] == "db_upgrade"]
    assert len(rows) == 1
    assert rows[0]["status"] == "ok"


def test_db_upgrade_against_a_held_lock_raises(
    db_path: Path,
    lock_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    _seed_at_revision_0001(db_path)

    with lock.acquire(lock_path):
        with pytest.raises(lock.LockHeldError):
            migrate_service.db_upgrade(
                ctx_factory, settings=settings, clock=clock, notifier=notifier
            )


# --- db init -------------------------------------------------------------------------------


def test_db_init_creates_the_schema_and_seeds_the_default_workspace(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    assert not db_path.exists()

    outcome = migrate_service.db_init(
        ctx_factory, settings=settings, clock=clock, notifier=notifier
    )

    assert outcome.to_revision == db_migrate.head_revision()
    assert outcome.restored is False
    assert outcome.error is None
    assert db_path.is_file()
    for name in ("backups", "locks", "logs"):
        assert (settings.data_dir / name).is_dir()

    engine = engine_for(db_path)
    try:
        assert db_migrate.is_at_head(engine)
        with engine.connect() as conn:
            workspace_pk = repo.default_workspace_pk(conn)
            rows = repo.enabled_subreddits(conn, workspace_pk)
    finally:
        engine.dispose()
    assert {row.name_lower for row in rows} == {"premiere", "videoediting", "editors"}

    init_rows = [row for row in _read_runs(db_path) if row["kind"] == "db_init"]
    assert len(init_rows) == 1
    assert init_rows[0]["status"] == "ok"


def test_db_init_is_idempotent(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    """§10.3: idempotent, not a no-op -- a second ``db init`` still takes the lock, still
    sweeps stale rows and still writes a run row (so it needs no RL-04 exclusion)."""
    migrate_service.db_init(ctx_factory, settings=settings, clock=clock, notifier=notifier)
    outcome = migrate_service.db_init(
        ctx_factory, settings=settings, clock=clock, notifier=notifier
    )

    assert outcome.migrated is False
    assert outcome.error is None

    engine = engine_for(db_path)
    try:
        with engine.connect() as conn:
            workspace_pk = repo.default_workspace_pk(conn)
            rows = repo.enabled_subreddits(conn, workspace_pk)
    finally:
        engine.dispose()
    assert len(rows) == 3  # not doubled

    init_rows = [row for row in _read_runs(db_path) if row["kind"] == "db_init"]
    assert len(init_rows) == 2
    assert all(row["status"] == "ok" for row in init_rows)


def test_db_init_sweeps_stale_rows(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
    now: int,
) -> None:
    """§10.3 step 5 (round-4 P2): the earliest point at which ``runs`` is guaranteed to
    exist is still inside the lock, so a crashed row from a previous process is recovered by
    ``db init`` too, not only by ``run``/``db upgrade`` (§12.2)."""
    migrate_service.db_init(ctx_factory, settings=settings, clock=clock, notifier=notifier)

    engine = engine_for(db_path)
    try:
        stale = repo.RunInsert(
            kind="run",
            trigger="cli",
            status="running",
            created_at=now,
            started_at=now,
            pid=2**31 - 1,
            stage=None,
            options_json=None,
            app_version=None,
            praw_version=None,
            schema_rev=None,
            settings_fingerprint=None,
            log_path=None,
        )
        with engine.begin() as conn:
            stale_pk = repo.insert_run(conn, stale)
    finally:
        engine.dispose()

    migrate_service.db_init(ctx_factory, settings=settings, clock=clock, notifier=notifier)

    rows = {row["pk"]: row for row in _read_runs(db_path)}
    assert rows[stale_pk]["status"] == "crashed"


def test_db_init_behind_head_refuses_and_writes_no_run_row(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    """§10.3 step 3: ``init`` must never migrate an existing, non-fresh database without a
    backup -- that is ``db upgrade``'s job."""
    _seed_at_revision_0001(db_path)

    with pytest.raises(db_migrate.MigrationsPendingError):
        migrate_service.db_init(ctx_factory, settings=settings, clock=clock, notifier=notifier)

    engine = engine_for(db_path)
    try:
        assert db_migrate.current_revision(engine) == "0001"
        with engine.connect() as conn:
            run_count = repo.table_counts(conn, ("runs",))["runs"]
    finally:
        engine.dispose()
    assert run_count == 1  # exactly the fixture's own seeded row; db_init added none


def test_db_init_against_a_held_lock_raises(
    lock_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    with lock.acquire(lock_path):
        with pytest.raises(lock.LockHeldError):
            migrate_service.db_init(ctx_factory, settings=settings, clock=clock, notifier=notifier)


# --- db current ------------------------------------------------------------------------------


def test_db_current_reports_none_before_any_schema_exists(settings: Settings) -> None:
    current, head = migrate_service.db_current(settings=settings)
    assert current is None
    assert head == db_migrate.head_revision()


def test_db_current_reports_the_current_revision_at_head(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    migrate_service.db_init(ctx_factory, settings=settings, clock=clock, notifier=notifier)

    current, head = migrate_service.db_current(settings=settings)

    assert current == head == db_migrate.head_revision()


# --- the documented failure paths, each given the seam it needs to be reachable ---------------

_DISK_IO = "disk I/O error"


def _raise_operational(*_args: object, **_kwargs: object) -> None:
    raise OperationalError("injected", None, RuntimeError(_DISK_IO))


def test_db_upgrade_against_a_held_lock_with_no_database_fabricates_nothing(
    db_path: Path,
    lock_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    """§10.3 step 1's ``skipped_locked`` attempt is best effort, and "best effort" must not
    mean "create the database to have somewhere to write it"."""
    assert not db_path.exists()

    with lock.acquire(lock_path), pytest.raises(lock.LockHeldError):
        migrate_service.db_upgrade(ctx_factory, settings=settings, clock=clock, notifier=notifier)

    assert not db_path.exists()


def test_a_migration_that_raises_is_restored_like_a_failed_post_check(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§10.3 step 11 says "on any failure in 9-10", not "on a failed post-check": a revision
    that dies mid-way has to take the same restore path."""
    _seed_at_revision_0001(db_path)
    monkeypatch.setattr(db_migrate, "upgrade_head", _raise_operational)

    outcome = migrate_service.db_upgrade(
        ctx_factory, settings=settings, clock=clock, notifier=notifier
    )

    assert outcome.restored is True
    assert outcome.migrated is False
    engine = engine_for(db_path)
    try:
        assert db_migrate.current_revision(engine) == "0001"
    finally:
        engine.dispose()


def test_failed_restore_bookkeeping_still_reports_restored_and_leaves_a_recoverable_row(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§10.3 T12 point 3: ``restored=True`` is reported on **both** paths, because the restore
    is what the operator must know about and the bookkeeping failing on top of it is a second
    sentence, not a different outcome. The run row then reads ``running`` in the restored
    file, which §12.2 makes the next run stamp ``crashed`` -- recoverable, never silent.

    **The outcome must NAME the bookkeeping failure** (round5-findings.json panel P1). It used
    to say only "migration failed, restored from <path>", which reads as a clean restore: the
    caller recorded and printed that sentence while the pre-migrate file sat on disk with no
    ``backups`` row. ``prune_pre_migrate_backups`` reads ``repo.backups_of_kind``, so an
    unreferenced file is never counted against ``KEEP_PRE_MIGRATE_BACKUPS`` and never deleted,
    and ``doctor`` cannot see it either. Both sentences now travel on ``MigrationOutcome.error``
    and therefore into the exit-1 block ``cli._print_migration`` prints."""
    _seed_at_revision_0001(db_path)
    monkeypatch.setattr(
        db_backup, "foreign_key_check", lambda _path: ["('run_subreddits', 1, 'runs', 1)"]
    )
    monkeypatch.setattr(db_migrate, "finish_restored_run", _raise_operational)

    outcome = migrate_service.db_upgrade(
        ctx_factory, settings=settings, clock=clock, notifier=notifier
    )

    assert outcome.restored is True
    assert outcome.error is not None
    assert "restored from" in outcome.error
    assert "could not be updated" in outcome.error
    assert "OperationalError" in outcome.error
    assert "will not be pruned" in outcome.error
    # The orphan the sentence is about: a backup file on disk with no `backups` row.
    assert outcome.backup_path is not None and outcome.backup_path.is_file()
    engine = engine_for(db_path)
    try:
        with engine.connect() as conn:
            assert repo.backups_of_kind(conn, "pre-migrate") == []
    finally:
        engine.dispose()
    upgrade_rows = [row for row in _read_runs(db_path) if row["kind"] == "db_upgrade"]
    assert len(upgrade_rows) == 1
    assert upgrade_rows[0]["status"] == "running"


def _inject_operational(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> type[Exception]:
    """The database half: the seed's write itself fails."""
    del tmp_path
    monkeypatch.setattr(seed, "apply_seed", _raise_operational)
    return OperationalError


def _inject_malformed_seed_yaml(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> type[Exception]:
    """The file half: a real ``config/seed.yaml`` with a syntax error, parsed for real.

    Nothing is stubbed -- ``seed.read_seed_names`` opens this file and ``yaml.safe_load``
    raises its own ``ScannerError``. That is the ordinary way a hand-edited seed file fails,
    and it is what escaped ``_seed``'s handler before ``yaml.YAMLError`` joined the tuple.
    """
    broken = tmp_path / "broken-seed.yaml"
    broken.write_text("subreddits: [premiere, videoediting\nthemes: {\n", encoding="utf-8")
    monkeypatch.setattr(seed, "DEFAULT_SEED_FILE", broken)
    return yaml.YAMLError


@pytest.mark.parametrize(
    "inject",
    [_inject_operational, _inject_malformed_seed_yaml],
    ids=["database_error", "malformed_seed_yaml"],
)
def test_a_seed_failure_finishes_the_db_init_run_row_failed(
    inject: Callable[[pytest.MonkeyPatch, Path], type[Exception]],
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """T14: all the seeded sources or none. The run row is closed ``failed`` before the
    exception leaves, so the database is at head with no sources and a repeat ``db init``
    finishes the job rather than finding a row that reads ``running`` forever.

    Parametrized over both failure classes (panel P2-10). Only the injected
    ``OperationalError`` was covered, and a malformed seed file -- the failure an operator
    actually meets -- went straight past ``_seed``'s ``except`` tuple: the run row stayed
    ``running`` until the next command condemned it as ``crashed``, and the notifier said
    nothing. Both cases must end the same way, which is what this parametrization pins.
    """
    expected = inject(monkeypatch, tmp_path)

    with pytest.raises(expected):
        migrate_service.db_init(ctx_factory, settings=settings, clock=clock, notifier=notifier)

    init_rows = [row for row in _read_runs(db_path) if row["kind"] == "db_init"]
    assert len(init_rows) == 1
    assert init_rows[0]["status"] == "failed"
    assert init_rows[0]["finished_at"] is not None
    assert [level for level, _message in notifier.sent] == ["error"]


# --- the missing-database precondition (round5-findings.json panel P0) -------------------------


def test_db_upgrade_with_no_database_refuses_before_it_writes_anything(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    """The panel's P0, closed. ``_upgrade_locked`` used to call ``ctx_factory`` first:
    ``engine_for`` created a 0-byte ``threaddigest.db`` and ``repo.insert_run`` then died with
    ``no such table: runs`` as an uncaught traceback (exit 1), leaving a phantom database that
    made the next ``run`` report "pending migrations" instead of "run: threaddigest db init".

    The refusal is §8's named precondition and it happens before any engine is opened, so the
    data directory is left with no database file at all. The subdirectory tree IS still
    created -- that is the earlier P0's fix (the flock lives inside it) and it is not a
    fabricated database.
    """
    assert not db_path.exists()

    with pytest.raises(migrate_service.DatabaseMissingError) as caught:
        migrate_service.db_upgrade(ctx_factory, settings=settings, clock=clock, notifier=notifier)

    assert caught.value.db_path == db_path
    assert str(caught.value) == migrate_service.database_missing_message(db_path)
    assert "threaddigest db init" in str(caught.value)
    assert not db_path.exists(), "db upgrade fabricated a database it was supposed to refuse"
    assert not list(settings.data_dir.glob("*.db"))
    assert notifier.sent == []


def test_db_upgrade_refuses_a_database_stamped_ahead_of_this_build(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
) -> None:
    """A rollback to an older binary: the stamp names a revision this build does not ship.

    Verified failure before the fix: alembic ``CommandError: Can't locate revision`` escaped
    as a raw traceback, the ``runs`` row was left ``running``, and a full-size pre-migrate
    backup was left on disk on every attempt because step 12's prune only runs on success. The
    refusal now happens before the run row and before the backup (panel P1).
    """
    engine = engine_for(db_path)
    try:
        migrate_to_head(engine)
        version = sa.table("alembic_version", sa.column("version_num"))
        with engine.begin() as conn:
            conn.execute(sa.update(version).values(version_num="0009_future"))
    finally:
        engine.dispose()

    with pytest.raises(db_migrate.UnknownRevisionError):
        migrate_service.db_upgrade(ctx_factory, settings=settings, clock=clock, notifier=notifier)

    assert _read_runs(db_path) == [], "a refused upgrade wrote a run row"
    assert list((settings.data_dir / "backups").glob("pre-migrate-*")) == []


_UNLOCATABLE = "Can't locate revision identified by '0009_future'"


def _raise_migration_failed(*_args: object, **_kwargs: object) -> None:
    raise db_migrate.MigrationFailedError(_UNLOCATABLE)


def test_a_command_error_inside_the_migration_is_restored_like_a_database_error(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """panel P1: ``_migrate_and_verify`` caught only ``DatabaseError``, so an Alembic-level
    failure escaped ``db_upgrade`` uncaught -- no ``MigrationOutcome``, no restore, a stuck
    ``running`` row, and no printed backup path -- while ``run``, ``db init`` and ``doctor``
    all told the operator to run exactly this command. Every migration failure now takes the
    step-11 restore path."""
    _seed_at_revision_0001(db_path)
    monkeypatch.setattr(db_migrate, "upgrade_head", _raise_migration_failed)

    outcome = migrate_service.db_upgrade(
        ctx_factory, settings=settings, clock=clock, notifier=notifier
    )

    assert outcome.restored is True
    assert outcome.migrated is False
    assert outcome.error is not None and "restored from" in outcome.error
    assert outcome.backup_path is not None and outcome.backup_path.is_file()
    upgrade_rows = [row for row in _read_runs(db_path) if row["kind"] == "db_upgrade"]
    assert len(upgrade_rows) == 1
    assert upgrade_rows[0]["status"] == "failed"
    assert upgrade_rows[0]["finished_at"] is not None
    engine = engine_for(db_path)
    try:
        assert db_migrate.current_revision(engine) == "0001"
    finally:
        engine.dispose()
    assert [level for level, _message in notifier.sent] == ["error"]
