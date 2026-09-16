"""RL-01 and the e2e half of RL-02: the preconditions ``run`` checks before any engine is
opened, and the one place a status and its exit code disagree (design-round5.md section
11.3, section 9, section 12.2).
"""

from __future__ import annotations

import shutil
from pathlib import Path

from click.testing import Result
from sqlalchemy.schema import DropTable
from tests.db.sqlhelp import run_pks

from threaddigest import cli
from threaddigest.adapters.reddit_fake import FakeRedditGateway
from threaddigest.core.retry import EXIT_CODES, ExitCode, RunStatus
from threaddigest.db import migrate as db_migrate
from threaddigest.db.engine import db_path_for, engine_for
from threaddigest.db.schema import Base
from threaddigest.services import lock


def test_invalid_settings_exit_78_with_no_run_row(
    cli_runner, db_at_head: Path, monkeypatch, table_rows
) -> None:
    """section 11.3 step 1: a ``ValidationError`` (here: the static settings file cannot be
    found, so every required static key is missing) exits 78 before a run row exists.
    """
    before = table_rows("runs")
    monkeypatch.setenv("THREADDIGEST_SETTINGS_FILE", str(db_at_head / "does-not-exist.yaml"))
    result = cli_runner.invoke(cli.app, ["run", "--gateway", "fake"])
    assert result.exit_code == 78
    assert table_rows("runs") == before


def _run_pks(data_dir: Path) -> list[int]:
    """Every ``runs.pk``, read revision-independently (``sqlhelp.run_pks``).

    The test below downgrades the database on purpose, and ``table_rows("runs")`` selects
    the HEAD column list -- including ``violations_json``, which revision 0001 does not
    have -- so counting rows that way would raise ``no such column`` before the assertion.
    """
    engine = engine_for(db_path_for(data_dir))
    try:
        with engine.connect() as conn:
            return run_pks(conn)
    finally:
        engine.dispose()


def test_pending_migrations_exit_78_with_no_run_row(cli_runner, db_at_head: Path) -> None:
    """section 11.3 step 7: ``db.migrate.require_head`` refuses a database below head, before
    any engine write, with no run row (section 19.10's ``run`` never migrates for itself).
    """
    engine = engine_for(db_path_for(db_at_head))
    try:
        db_migrate.downgrade_one(engine)
    finally:
        engine.dispose()

    before = _run_pks(db_at_head)
    result = cli_runner.invoke(cli.app, ["run", "--gateway", "fake"])
    assert result.exit_code == 78
    assert _run_pks(db_at_head) == before


def test_exit_code_table_is_total_over_run_status(
    cli_runner,
    db_at_head: Path,
    loaded_gateway: FakeRedditGateway,
    demo_fixture_path: Path,
    table_rows,
) -> None:
    """section 9: ``core.retry.EXIT_CODES`` covers every :class:`RunStatus`, and the one
    place a status and its exit code disagree -- a mid-run ``AuthFailed`` ends ``failed``
    in the status column but exits 78, so "auth failures exit 78" still holds.
    """
    assert set(EXIT_CODES) == set(RunStatus)
    assert EXIT_CODES[RunStatus.FAILED] == ExitCode.FAILED == 1

    loaded_gateway.set_auth_failed()
    result = cli_runner.invoke(
        cli.app, ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
    )
    assert result.exit_code == ExitCode.CONFIG == 78
    runs = table_rows("runs")
    assert runs[-1]["status"] == "failed"


def test_held_lock_exits_75_with_zero_gateway_calls(
    cli_runner, db_at_head: Path, cli_gateway: FakeRedditGateway, demo_fixture_path: Path
) -> None:
    """section 11.3 step 5: steps 1-5 run before the gateway object exists, so RL-02's
    "zero gateway calls" is structural -- ``len(fake.factory_calls) == 0`` -- not merely
    an absence of recorded requests (section 11.6, item 2).
    """
    lock_path = db_at_head / "locks" / "collector.lock"
    with lock.acquire(lock_path):
        result = cli_runner.invoke(
            cli.app, ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
        )
    assert result.exit_code == 75
    assert len(cli_gateway.factory_calls) == 0


def test_dry_run_against_a_held_lock_exits_75_without_writing(
    cli_runner,
    db_at_head: Path,
    cli_gateway: FakeRedditGateway,
    demo_fixture_path: Path,
    table_rows,
) -> None:
    """A dry run PROBES the lock (``lock.is_held``), never acquires it; held ⇒ exit 75 with
    no run row and no engine at all (section 11.3 step 5, dry-run column).
    """
    before = table_rows("runs")
    lock_path = db_at_head / "locks" / "collector.lock"
    with lock.acquire(lock_path):
        result = cli_runner.invoke(
            cli.app,
            ["run", "--dry-run", "--gateway", "fake", "--fixture", str(demo_fixture_path)],
        )
    assert result.exit_code == 75
    assert table_rows("runs") == before
    assert len(cli_gateway.factory_calls) == 0


def test_missing_database_exits_78_and_names_db_init(cli_runner, isolated_data_dir: Path) -> None:
    """section 19.10: ``run`` against a data directory with no database file exits 78 and
    names ``threaddigest db init`` -- ``run`` never creates a schema for itself.
    """
    result = cli_runner.invoke(cli.app, ["run", "--gateway", "fake"])
    assert result.exit_code == 78
    assert "db init" in result.output


def test_held_lock_during_a_migration_still_exits_75(
    cli_runner, db_at_head: Path, cli_gateway: FakeRedditGateway, demo_fixture_path: Path
) -> None:
    """section 11.3: the lock may be held by a ``db upgrade`` that is mid-migration, so the
    read-mostly ``skipped_locked`` insert must not turn a held lock into a traceback. Here:
    hold the lock from the test, and drop ``runs`` from a second connection so the insert
    itself raises ``DatabaseError``. The documented outcome is still 75.
    """
    engine = engine_for(db_path_for(db_at_head))
    try:
        with engine.begin() as conn:
            conn.execute(DropTable(Base.metadata.tables["runs"]))
    finally:
        engine.dispose()

    lock_path = db_at_head / "locks" / "collector.lock"
    with lock.acquire(lock_path):
        result = cli_runner.invoke(
            cli.app, ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
        )
    assert result.exit_code == 75


def _exited_cleanly(result: Result) -> bool:
    """ "Never a traceback" means nothing escaped but the ``SystemExit`` a ``typer.Exit``
    raises: ``CliRunner`` records that one in ``result.exception`` on every non-zero exit."""
    return result.exception is None or isinstance(result.exception, SystemExit)


def test_run_with_no_locks_directory_exits_78_or_75_never_a_traceback(
    cli_runner, db_at_head: Path, loaded_gateway: FakeRedditGateway, demo_fixture_path: Path
) -> None:
    """round5-findings.json's P0 "lock acquisition versus directory creation", ``run``'s half.

    Section 11.3 gains a step between 4 and 5 that creates ``locks/`` (and ``backups/``,
    ``logs/``) when they are missing, before the lock decision -- creating directories inside
    the data dir is not a mutation of shared state, so it needs no lock. Both halves are
    asserted: with the database at head the run completes and re-creates the tree, and
    against a data dir with neither ``locks/`` nor a database the answer is the documented
    78 naming ``db init`` -- never a ``FileNotFoundError`` from ``lock.acquire``.
    """
    shutil.rmtree(db_at_head / "locks")
    completed = cli_runner.invoke(
        cli.app, ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
    )
    assert _exited_cleanly(completed), completed.output
    assert completed.exit_code == 0, completed.output
    assert (db_at_head / "locks").is_dir()

    shutil.rmtree(db_at_head / "locks")
    db_path_for(db_at_head).unlink()
    refused = cli_runner.invoke(cli.app, ["run", "--gateway", "fake"])
    assert _exited_cleanly(refused), refused.output
    assert refused.exit_code == 78
    assert "db init" in refused.output
