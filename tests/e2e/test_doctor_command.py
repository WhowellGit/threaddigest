"""``doctor --no-network``: exit 0 on a healthy install, the check list rendered, and
``--alert-if-stale`` flipping ``last_run_age`` between ok and not-ok for the same data
(design-round5.md section 15, section 16, "Additional tests with no spec id").
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from threaddigest import cli
from threaddigest.db import repo
from threaddigest.db.engine import db_path_for, engine_for
from threaddigest.ports import AuthFailed

#: Every check name ``services.doctor.run_checks`` emits with a database present (section
#: 15.2's twelve, plus ``hooks_installed`` wired in as the thirteenth).
EXPECTED_CHECKS = {
    "settings_valid",
    "sqlite_version",
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
                warnings_json="[]",
            )
    finally:
        engine.dispose()


def test_doctor_alert_if_stale_flips(cli_runner, db_at_head: Path) -> None:
    """The same successful run reads as fresh under a generous threshold and stale under a
    tight one: ``--alert-if-stale`` genuinely controls ``last_run_age``, not a hard-coded
    value (section 15.1's contract; the default itself is pinned by the schedule contract in
    ``tests/deploy/test_schedule_contract.py``, KI-024).
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


# --- --network: the one doctor path that can reach Reddit (tranche B) --------------------------

#: The row ``--network`` adds and ``--no-network`` must never produce.
AUTH_PING = "auth_ping"


def test_doctor_network_is_refused_under_pytest_with_78_and_no_traceback(
    cli_runner, db_at_head: Path
) -> None:
    """``--network`` builds a PRAW gateway, and ``cli._guard_gateway`` refuses any gateway but
    the fake while ``PYTEST_CURRENT_TEST`` is set (section 11.3 step 3, guard G06). So the one
    doctor path that can reach Reddit cannot be reached from a test at all -- it exits 78 like
    every other precondition, with a message rather than a traceback. A ``typer.Exit`` arrives
    at ``CliRunner`` as ``SystemExit``; anything else here would be an unhandled exception.
    """
    result = cli_runner.invoke(cli.app, ["doctor", "--network"])

    assert isinstance(result.exception, SystemExit), result.output
    assert result.exit_code == 78
    assert "refusing --gateway praw under pytest" in result.output
    assert "Traceback" not in result.output


def test_doctor_no_network_json_payload_is_the_only_thing_on_stdout(
    cli_runner, db_at_head: Path
) -> None:
    """``--json`` is a machine-readable mode: the payload is the output, so a check row, a
    warning line or a stray echo alongside it would break every consumer that parses it.
    Asserted by parsing the WHOLE of stdout, not by finding JSON inside it.
    """
    result = cli_runner.invoke(cli.app, ["doctor", "--no-network", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert set(payload) == {"ok", "checks"}
    assert EXPECTED_CHECKS <= {check["name"] for check in payload["checks"]}
    assert AUTH_PING not in {check["name"] for check in payload["checks"]}


def test_the_auth_ping_row_appears_only_when_the_network_is_asked_for(
    cli_runner, db_at_head: Path, loaded_gateway, monkeypatch
) -> None:
    """The row's presence, end to end, through the CLI the operator actually types.

    Two deliberate choices, both about not letting a test reach Reddit. The gateway comes
    from the ``GATEWAY_FACTORY`` seam ``tests/e2e/conftest.py`` installs, so the CLI is handed
    this in-memory fake rather than a ``PrawGateway`` -- the seam is installed by the fixture
    before anything below runs. And ``PYTEST_CURRENT_TEST`` is removed for the duration,
    because ``cli._guard_gateway`` reads exactly that variable to refuse a network gateway
    under pytest (the test above proves it does): without removing it, ``--network`` exits 78
    and this path is unreachable. Removing it does **not** unlock the data directory --
    ``settings._pytest_is_loaded`` also checks ``sys.modules``, so the refusal of the real
    ``data/`` directory still stands -- and ``--block-network`` still fails any real socket.
    """
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    quiet = cli_runner.invoke(cli.app, ["doctor", "--no-network", "--json"])
    loud = cli_runner.invoke(cli.app, ["doctor", "--network", "--json"])

    assert quiet.exit_code == 0, quiet.output
    assert AUTH_PING not in {c["name"] for c in json.loads(quiet.output)["checks"]}
    assert loud.exit_code == 0, loud.output
    rows = {c["name"]: c for c in json.loads(loud.output)["checks"]}
    assert AUTH_PING in rows, sorted(rows)
    assert rows[AUTH_PING]["ok"] is True, rows[AUTH_PING]["detail"]
    assert loaded_gateway.count("about") == 1
    assert loaded_gateway.requests_made == 1


def test_doctor_network_exits_78_when_the_gateway_cannot_be_built(
    cli_runner, db_at_head: Path, monkeypatch
) -> None:
    """A gateway this build cannot construct is the case ``cli.ConfigError`` already names.

    PRAW refuses to build a client from some credential shapes, and the adapter translates
    that refusal into ``ports.AuthFailed`` at construction -- before ``run_checks`` is reached,
    so the ``auth_ping`` row cannot report it. Left alone it would escape as a traceback out of
    the one command whose job is to report, which is the same failure shape the corrupt-database
    finding closed. It exits 78 with a sentence instead, like every other precondition.

    The failure is planted on the ``GATEWAY_FACTORY`` seam rather than by feeding real
    credentials to PRAW, so nothing here constructs a client or opens a socket.
    """

    refusal = "credentials rejected: missing required attribute"

    def _refuse(spec: object) -> object:
        raise AuthFailed(refusal)

    monkeypatch.setattr(cli, "GATEWAY_FACTORY", _refuse)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    result = cli_runner.invoke(cli.app, ["doctor", "--network"])

    assert isinstance(result.exception, SystemExit), result.output
    assert result.exit_code == 78
    assert "cannot build the praw gateway for the auth ping" in result.output
    assert "Traceback" not in result.output
