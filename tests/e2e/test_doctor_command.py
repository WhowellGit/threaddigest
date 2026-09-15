"""``doctor --no-network``: exit 0 on a healthy install, the check list rendered, and
``--alert-if-stale`` flipping ``last_run_age`` between ok and not-ok for the same data
(design-round5.md section 15, section 16, "Additional tests with no spec id").
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from insightminer import cli
from insightminer.db import repo
from insightminer.db.engine import db_path_for, engine_for

#: Every check name ``services.doctor.run_checks`` emits with a database present (section
#: 15.2's twelve, plus ``hooks_installed`` wired in as the thirteenth).
EXPECTED_CHECKS = {
    "settings_valid",
    "data_dir_writable",
    "data_dir_outside_tcc",
    "database_present",
    "alembic_at_head",
    "quick_check",
    "schema_fingerprint",
    "free_disk",
    "last_run_age",
    "enabled_sources",
    "lock_not_stale",
    "credentials_present",
    "no_stale_running_rows",
    "hooks_installed",
}


def test_doctor_no_network_exits_0(cli_runner, db_at_head: Path) -> None:
    """A fresh install with no run yet: ``last_run_age`` is a WARNING (Wes's Q5), which
    does not flip the exit code, so ``doctor`` is still 0.
    """
    result = cli_runner.invoke(cli.app, ["doctor", "--no-network"])
    assert result.exit_code == 0, result.output


def test_doctor_renders_the_check_list(cli_runner, db_at_head: Path) -> None:
    """``--json`` renders every check ``run_checks`` produces, by name (section 15.1)."""
    result = cli_runner.invoke(cli.app, ["doctor", "--no-network", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    names = {check["name"] for check in payload["checks"]}
    assert EXPECTED_CHECKS <= names


def _plant_successful_run(db_path: Path, *, finished_at: int) -> None:
    engine = engine_for(db_path)
    try:
        with engine.begin() as conn:
            pk = repo.insert_run(
                conn,
                repo.RunInsert(
                    kind="run",
                    trigger="cli",
                    status="running",
                    created_at=finished_at,
                    started_at=finished_at,
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
            repo.finish_run(
                conn,
                run_pk=pk,
                status="ok",
                finished_at=finished_at,
                counters_json="{}",
                api_requests=0,
                error=None,
                violations_json="[]",
            )
    finally:
        engine.dispose()


def test_doctor_alert_if_stale_flips(cli_runner, db_at_head: Path) -> None:
    """The same successful run reads as fresh under a generous threshold and stale under a
    tight one: ``--alert-if-stale`` genuinely controls ``last_run_age``, not a hard-coded
    36h (section 15.1's contract, Q5's default).
    """
    import time

    finished_at = int(time.time()) - 10_000  # ~2h45m ago
    _plant_successful_run(db_path_for(db_at_head), finished_at=finished_at)

    fresh = cli_runner.invoke(
        cli.app, ["doctor", "--no-network", "--json", "--alert-if-stale", "1d"]
    )
    assert fresh.exit_code == 0, fresh.output
    fresh_checks = json.loads(fresh.output)["checks"]
    fresh_check = next(c for c in fresh_checks if c["name"] == "last_run_age")
    assert fresh_check["ok"] is True

    stale = cli_runner.invoke(
        cli.app, ["doctor", "--no-network", "--json", "--alert-if-stale", "1h"]
    )
    stale_checks = json.loads(stale.output)["checks"]
    stale_check = next(c for c in stale_checks if c["name"] == "last_run_age")
    assert stale_check["ok"] is False
    assert stale.exit_code == 1


def test_doctor_rejects_an_unparseable_alert_window_with_78(cli_runner, db_at_head: Path) -> None:
    """``--alert-if-stale nonsense`` is a configuration error, not a traceback: the duration
    is parsed by ``services.doctor.parse_duration``, whose ``ValueError`` the CLI maps to
    ``ExitCode.CONFIG`` like every other precondition (section 11.2).
    """
    result = cli_runner.invoke(cli.app, ["doctor", "--no-network", "--alert-if-stale", "soon"])
    # A `typer.Exit` reaches CliRunner as a SystemExit; anything else would be a traceback.
    assert isinstance(result.exception, SystemExit), result.output
    assert result.exit_code == 78


def test_doctor_rejects_an_unparseable_alert_window_with_78_before_a_database_exists(
    cli_runner, isolated_data_dir: Path
) -> None:
    """The same bad ``--alert-if-stale``, but on a data directory with no database yet (no
    ``db init`` has run). Before the fix, ``parse_duration`` was only called deep inside
    ``services.doctor._checks_with_a_database``, so this exact invocation fell through
    ``database_present`` failing first and exited 1 with the check list printed instead of
    the documented 78 -- a bad value silently read as "healthy install, just no database."
    The duration is now parsed once at the top of ``run_checks``, before ``database_present``
    runs at all, so this is a config error on every path.
    """
    del isolated_data_dir  # present only to make "no db init happened" explicit at the call site
    result = cli_runner.invoke(cli.app, ["doctor", "--no-network", "--alert-if-stale", "soon"])
    assert isinstance(result.exception, SystemExit), result.output
    assert result.exit_code == 78


def test_doctor_with_a_good_alert_window_still_reports_before_a_database_exists(
    cli_runner, isolated_data_dir: Path
) -> None:
    """A valid duration must not be mistaken for a config error just because it is now parsed
    eagerly: on a data directory with no database yet, ``doctor`` still runs the whole check
    list and exits 1 for the documented reason (``database_present`` failing, an ERROR-
    severity check), never 78.
    """
    del isolated_data_dir
    result = cli_runner.invoke(cli.app, ["doctor", "--no-network", "--alert-if-stale", "36h"])
    assert result.exit_code == 1, result.output
    assert "database_present" in result.output


def test_doctor_on_a_corrupt_database_lists_its_checks_instead_of_a_traceback(
    cli_runner, db_at_head: Path
) -> None:
    """round5-findings.json panel P1, end to end.

    Reproduced on this tree before the fix: ``db init``, zero 4096 bytes at offset 100, then
    ``doctor --no-network`` exited 1 with an unhandled ``sqlalchemy`` ``DatabaseError`` and NO
    output at all. ``run_checks`` fell through to ``_checks_with_a_database`` because it
    branched on "the file exists" rather than on the ``database_present`` check, and neither
    ``cli.doctor`` (``ConfigError``) nor ``cli._doctor_report`` (``ValueError``) catches a
    ``DatabaseError``. The definition of done -- "doctor lists its checks" -- failed in the one
    case the ``database_present`` and ``quick_check`` rows exist for.
    """
    db_path = db_path_for(db_at_head)
    with db_path.open("r+b") as handle:
        handle.seek(100)
        handle.write(b"\xff" * 4096)

    result = cli_runner.invoke(cli.app, ["doctor", "--no-network"])

    assert result.exception is None or isinstance(result.exception, SystemExit), result.output
    assert result.exit_code == 1, result.output
    listed = {
        line.split("] ", 1)[1].split(":", 1)[0]
        for line in result.output.splitlines()
        if "]" in line
    }
    assert listed == EXPECTED_CHECKS, result.output
    assert "database_present" in result.output
    assert "quick_check" in result.output
