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
database -- ``insightminer.db`` -- placed under ``settings.data_dir``, i.e.
``settings.data_dir / "insightminer.db"``. ``tests/services/test_doctor.py`` makes the same
assumption, for the same reason: it is the one path a real ``insightminer`` invocation would
resolve to from ``settings.data_dir`` alone.
"""

from __future__ import annotations

import shutil
from collections.abc import Callable
from pathlib import Path

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.exc import OperationalError

from insightminer.adapters.clock import FakeClock
from insightminer.adapters.notify import FakeNotifier
from insightminer.db import backup as db_backup
from insightminer.db import migrate as db_migrate
from insightminer.db import repo
from insightminer.db.engine import engine_for
from insightminer.db.schema import Base
from insightminer.db.schema_dump import migrate_to_head
from insightminer.services import lock, runs, seed
from insightminer.services import migrate as migrate_service
from insightminer.settings import Settings

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "db"
FIXTURE_0001 = FIXTURES_DIR / "0001.sqlite"


# --- local db_path: inside settings.data_dir, matching the convention documented above --------


@pytest.fixture
def db_path(settings: Settings) -> Path:
    return settings.data_dir / "insightminer.db"


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


def test_prune_pre_migrate_backups_keeps_only_the_newest_three(
    db_path: Path, settings: Settings, now: int
) -> None:
    engine = engine_for(db_path)
    try:
        migrate_to_head(engine)
        backups_dir = settings.data_dir / "backups"
        backups_dir.mkdir(parents=True, exist_ok=True)
        paths = []
        with engine.begin() as conn:
            for i in range(5):
                path = backups_dir / f"pre-migrate-000{i}.db"
                path.write_bytes(b"not a real sqlite file")
                paths.append(path)
                repo.insert_backup(
                    conn,
                    repo.BackupInsert(
                        path=str(path),
                        sha256=f"sha{i}",
                        size_bytes=1,
                        integrity="ok",
                        kind="pre-migrate",
                        created_at=now + i,
                        schema_rev="0001",
                        table_counts_json=None,
                    ),
                )

        with engine.begin() as conn:
            removed = migrate_service.prune_pre_migrate_backups(conn, keep=3)

        assert sorted(removed) == sorted(paths[:2])
        for path in paths[:2]:
            assert not path.exists()
        for path in paths[2:]:
            assert path.exists()
        with engine.connect() as conn:
            remaining = repo.backups_of_kind(conn, "pre-migrate")
        assert len(remaining) == 3
        assert {p for _, p, _ in remaining} == {str(p) for p in paths[2:]}
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
    file, which §12.2 makes the next run stamp ``crashed`` -- recoverable, never silent."""
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
    upgrade_rows = [row for row in _read_runs(db_path) if row["kind"] == "db_upgrade"]
    assert len(upgrade_rows) == 1
    assert upgrade_rows[0]["status"] == "running"


def test_a_seed_failure_finishes_the_db_init_run_row_failed(
    db_path: Path,
    ctx_factory: CtxFactory,
    settings: Settings,
    clock: FakeClock,
    notifier: FakeNotifier,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """T14: all the seeded sources or none. The run row is closed ``failed`` before the
    exception leaves, so the database is at head with no sources and a repeat ``db init``
    finishes the job rather than finding a row that reads ``running`` forever."""
    monkeypatch.setattr(seed, "apply_seed", _raise_operational)

    with pytest.raises(OperationalError):
        migrate_service.db_init(ctx_factory, settings=settings, clock=clock, notifier=notifier)

    init_rows = [row for row in _read_runs(db_path) if row["kind"] == "db_init"]
    assert len(init_rows) == 1
    assert init_rows[0]["status"] == "failed"
    assert init_rows[0]["finished_at"] is not None
    assert [level for level, _message in notifier.sent] == ["error"]
