"""``db init`` / ``db upgrade``: the lock, the run row, idempotency, the below-head refusal,
and DB-38's e2e half -- a REAL 0001->0002 upgrade that fails and restores (design-round5.md
section 10.3, section 16, "Additional tests with no spec id").
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from tests.db.sqlhelp import run_pks

from threaddigest import cli
from threaddigest.db import migrate as db_migrate
from threaddigest.db.engine import db_path_for, engine_for
from threaddigest.services import lock
from threaddigest.services import migrate as migrate_service

FIXTURE_0001 = Path(__file__).resolve().parents[1] / "fixtures" / "db" / "0001.sqlite"


def test_db_init_takes_the_lock_and_writes_a_run_row(
    cli_runner, isolated_data_dir: Path, table_rows
) -> None:
    """section 10.3, T13: ``db init`` is a run-lifecycle command -- one ``runs`` row,
    ``kind='db_init'``, and the lock released when it returns.
    """
    result = cli_runner.invoke(cli.app, ["db", "init"])
    assert result.exit_code == 0, result.output
    runs = table_rows("runs")
    assert len(runs) == 1
    assert runs[0]["kind"] == "db_init"
    assert runs[0]["status"] == "ok"
    lock_path = isolated_data_dir / "locks" / "collector.lock"
    assert lock.is_held(lock_path) is False


def test_db_init_sweeps_stale_rows(cli_runner, db_at_head: Path, table_rows) -> None:
    """A ``running`` row with a dead pid, left over from an earlier crash, is stamped
    ``crashed`` by the next ``db init``'s stale sweep (section 10.3 step 5).
    """
    from threaddigest.db import repo

    engine = engine_for(db_path_for(db_at_head))
    try:
        with engine.begin() as conn:
            stale_pk = repo.insert_run(
                conn,
                repo.RunInsert(
                    kind="run",
                    trigger="cli",
                    status="running",
                    created_at=0,
                    started_at=0,
                    pid=999_999_999,
                    stage=None,
                    options_json=None,
                    app_version=None,
                    praw_version=None,
                    schema_rev=None,
                    settings_fingerprint=None,
                    log_path=None,
                ),
            )
    finally:
        engine.dispose()

    result = cli_runner.invoke(cli.app, ["db", "init"])
    assert result.exit_code == 0, result.output
    stale_row = next(row for row in table_rows("runs") if row["pk"] == stale_pk)
    assert stale_row["status"] == "crashed"


def test_db_init_is_idempotent(cli_runner, isolated_data_dir: Path, table_rows) -> None:
    """A second ``db init`` is not a no-op (it still takes the lock and writes a run row)
    but IS idempotent: the seeded sources are not duplicated (section 10.3).
    """
    first = cli_runner.invoke(cli.app, ["db", "init"])
    assert first.exit_code == 0, first.output
    second = cli_runner.invoke(cli.app, ["db", "init"])
    assert second.exit_code == 0, second.output

    runs = table_rows("runs")
    assert len(runs) == 2
    assert all(row["kind"] == "db_init" for row in runs)
    assert all(row["status"] == "ok" for row in runs)
    assert len(table_rows("subreddits")) == 6


def _run_pks(data_dir: Path) -> list[int]:
    """Every ``runs.pk``, tolerating a database that is missing or below head.

    ``table_rows("runs")`` selects the HEAD model's column list, which includes
    ``violations_json``; the two tests below deliberately look at a 0001 database, where
    that column does not exist yet, so they count rows through ``sqlhelp.run_pks``
    (a revision-independent ``sa.table``) instead.
    """
    db_path = db_path_for(data_dir)
    if not db_path.is_file():
        return []
    engine = engine_for(db_path)
    try:
        with engine.connect() as conn:
            return run_pks(conn)
    finally:
        engine.dispose()


def test_db_init_behind_head_refuses_with_78(cli_runner, db_at_head: Path) -> None:
    """``db init`` must never migrate without a backup: a database that already exists but
    is behind head is refused before any run row is written (section 10.3's ``db_init``).
    """
    engine = engine_for(db_path_for(db_at_head))
    try:
        db_migrate.downgrade_one(engine)
    finally:
        engine.dispose()

    before = _run_pks(db_at_head)
    result = cli_runner.invoke(cli.app, ["db", "init"])
    assert result.exit_code == 78
    assert _run_pks(db_at_head) == before


def _plant_orphan_run_subreddit(db_path: Path) -> None:
    """Insert a ``run_subreddits`` row whose ``run_pk`` references no ``runs`` row.

    The pragma toggle must happen on the RAW DBAPI connection, outside any transaction
    (db/engine.py's own docstring: ``foreign_keys`` cannot be changed mid-transaction) --
    the same idiom ``db.engine.checkpoint_truncate`` already uses in production.
    """
    engine = engine_for(db_path)
    try:
        raw = engine.raw_connection()
        try:
            cursor = raw.cursor()
            cursor.execute("PRAGMA foreign_keys=OFF")
            cursor.execute(
                "INSERT INTO run_subreddits "
                "(run_pk, subreddit_pk, pages, items_seen, new_items, updated_items, "
                "stop_reason, error) VALUES (999999, 1, 0, 0, 0, 0, NULL, NULL)"
            )
            raw.commit()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.close()
        finally:
            raw.close()
    finally:
        engine.dispose()


def test_failed_upgrade_restores_and_finishes_the_run_row_failed(
    cli_runner, isolated_data_dir: Path
) -> None:
    """DB-38's e2e half (round-5 P1-2): a REAL 0001->0002 upgrade, failed at step 10 by a
    planted orphan child row that survives the batch recreate and trips
    ``foreign_key_check``. The restore brings the file back to 0001; the run row inserted
    before the backup is finished ``failed`` with a non-NULL ``finished_at`` INSIDE the
    restored file, and the ``backups`` row is present there too (T12, ``db.migrate.
    finish_restored_run``, built revision-independently from ``sa.table``).
    """
    db_path = db_path_for(isolated_data_dir)
    db_path.write_bytes(FIXTURE_0001.read_bytes())
    _plant_orphan_run_subreddit(db_path)

    result = cli_runner.invoke(cli.app, ["db", "upgrade"])
    assert result.exit_code == 1, result.output

    runs = sa.table("runs", sa.column("pk"), sa.column("status"), sa.column("finished_at"))
    backups = sa.table("backups", sa.column("pk"))
    engine = engine_for(db_path)
    try:
        with engine.connect() as conn:
            rows = conn.execute(sa.select(runs).order_by(sa.desc(runs.c.pk))).all()
            assert rows, "no runs row in the restored file"
            latest = rows[0]
            assert latest.status == "failed"
            assert latest.finished_at is not None
            assert len(conn.execute(sa.select(backups)).all()) >= 1
    finally:
        engine.dispose()


def test_db_init_on_a_data_dir_with_no_locks_directory_succeeds(
    cli_runner, isolated_data_dir: Path, table_rows
) -> None:
    """round5-findings.json's P0 "lock acquisition versus directory creation", closed.

    ``db init`` is the documented first command of every fresh install, and the collector
    lock lives at ``data/locks/collector.lock`` -- inside a directory nothing had created.
    Driven from the autouse fixture's bare ``data/`` (no ``locks/``, no ``backups/``, no
    ``logs/``, no database): the tree is created BEFORE the lock decision, so this is exit 0
    and a seeded database, never a ``FileNotFoundError`` traceback at step 1.
    """
    assert not (isolated_data_dir / "locks").exists()

    result = cli_runner.invoke(cli.app, ["db", "init"])

    assert result.exit_code == 0, result.output
    assert (isolated_data_dir / "locks").is_dir()
    assert [row["kind"] for row in table_rows("runs")] == ["db_init"]
    assert len(table_rows("subreddits")) == 6


def test_db_upgrade_with_no_database_exits_78_and_fabricates_nothing(
    cli_runner, isolated_data_dir: Path
) -> None:
    """round5-findings.json panel P0, end to end.

    Verified before the fix: ``THREADDIGEST_DATA_DIR=/tmp/empty threaddigest db upgrade`` died
    with a 60-line SQLAlchemy traceback (``no such table: runs``, exit 1) and left a fabricated
    0-byte ``threaddigest.db`` behind -- which ``db current`` then reported as ``current: None``
    and ``run`` reported as pending migrations, so every retry crashed the same way. It is now
    §8's named precondition: exit 78, the message names ``threaddigest db init``, and no
    database file is created.
    """
    db_path = db_path_for(isolated_data_dir)
    assert not db_path.exists()

    result = cli_runner.invoke(cli.app, ["db", "upgrade"])

    assert result.exit_code == 78, result.output
    assert f"no database at {db_path}" in result.output
    assert "threaddigest db init" in result.output
    assert not db_path.exists()
    assert _run_pks(isolated_data_dir) == []


def test_db_upgrade_and_run_name_the_missing_database_the_same_way(
    cli_runner, isolated_data_dir: Path
) -> None:
    """The panel's "§8's named precondition (78)": an operator who reaches the precondition
    from either command gets the same sentence and the same next action. Both are built from
    ``migrate_service.database_missing_message``, so this asserts they cannot drift apart."""
    upgrade = cli_runner.invoke(cli.app, ["db", "upgrade"])
    run = cli_runner.invoke(cli.app, ["run", "--gateway", "fake"])

    assert upgrade.exit_code == 78 == run.exit_code
    expected = migrate_service.database_missing_message(db_path_for(isolated_data_dir))
    assert expected in upgrade.output
    assert expected in run.output


def test_db_upgrade_refuses_a_database_stamped_ahead_of_this_build(
    cli_runner, db_at_head: Path
) -> None:
    """A rollback to an older binary. Alembic's ``CommandError: Can't locate revision`` used to
    escape ``db_upgrade`` uncaught: a raw traceback, exit 1, a ``running`` run row left behind
    and a full-size pre-migrate backup on disk for every attempt (step 12's prune only runs on
    success). The refusal is a precondition now -- exit 78, before the run row and before the
    backup (round5-findings.json panel P1)."""
    db_path = db_path_for(db_at_head)
    version = sa.table("alembic_version", sa.column("version_num"))
    engine = engine_for(db_path)
    try:
        with engine.begin() as conn:
            conn.execute(sa.update(version).values(version_num="0009_future"))
    finally:
        engine.dispose()

    before = _run_pks(db_at_head)
    result = cli_runner.invoke(cli.app, ["db", "upgrade"])

    assert result.exit_code == 78, result.output
    assert "0009_future" in result.output
    assert _run_pks(db_at_head) == before
    assert list((db_at_head / "backups").glob("pre-migrate-*")) == []
