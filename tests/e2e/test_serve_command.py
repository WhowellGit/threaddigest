"""CF-12: what ``threaddigest serve`` refuses before it opens a socket.

``serve`` checks exactly what ``run`` checks, in the same order and with the same words: the
settings resolve, the database file exists, and the schema is at head. Every refusal is a 78,
and none of them writes a run row -- ``serve`` is not a mutating command (RL-04 excludes it).

Maintenance-only mode -- serving ``/system`` so a pending migration could be applied from the
page -- is deliberately not built: ``/system`` arrives at M2, and a maintenance mode with
nowhere to go is the UI panel's § D finding 1 in reverse (a button that can never be reached,
the other way round). Until then the refusal names the command that fixes it.

The last test is the reason no test here reaches ``uvicorn.run``: the command refuses to
start a server while pytest is loaded, and it refuses *after* the preconditions above, so
those preconditions are reachable by a test instead of being shadowed by the guard.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

from tests.db.sqlhelp import run_pks
from typer.testing import CliRunner

from threaddigest import cli
from threaddigest.core.retry import ExitCode
from threaddigest.db import migrate as db_migrate
from threaddigest.db.engine import db_path_for, engine_for

FIXTURE_0001 = Path(__file__).resolve().parents[1] / "fixtures" / "db" / "0001.sqlite"

#: Environment for a help-text invocation: NO_COLOR and TERM=dumb are what typer's rich
#: integration and click both honour to turn colour off regardless of what the runner
#: thinks its terminal can do (KI-037); FORCE_COLOR is cleared so an ambient one (CI, or a
#: developer's shell) cannot override the other two.
_NO_COLOR_ENV = {"NO_COLOR": "1", "TERM": "dumb", "FORCE_COLOR": None}

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _strip_ansi(text: str) -> str:
    """Belt and braces on top of ``_NO_COLOR_ENV``: drop any colour escape that still made
    it into help text before a test asserts on the text's content (KI-037)."""
    return _ANSI_ESCAPE.sub("", text)


def _run_pks(data_dir: Path) -> list[int]:
    """Every ``runs.pk``, read revision-independently so a database below head is readable."""
    db_path = db_path_for(data_dir)
    if not db_path.is_file():
        return []
    engine = engine_for(db_path)
    try:
        with engine.connect() as conn:
            return run_pks(conn)
    finally:
        engine.dispose()


def test_serve_refuses_a_missing_database(cli_runner: CliRunner, isolated_data_dir: Path) -> None:
    result = cli_runner.invoke(cli.app, ["serve"])
    assert result.exit_code == ExitCode.CONFIG
    assert "db init" in result.output, "the refusal does not name the command that fixes it"
    assert _run_pks(isolated_data_dir) == []


def test_serve_refuses_a_database_behind_head(cli_runner: CliRunner, db_at_head: Path) -> None:
    """A pending migration is a refusal, not a page served against the wrong schema."""
    engine = engine_for(db_path_for(db_at_head))
    try:
        db_migrate.downgrade_one(engine)
    finally:
        engine.dispose()

    before = _run_pks(db_at_head)
    result = cli_runner.invoke(cli.app, ["serve"])
    assert result.exit_code == ExitCode.CONFIG
    assert _run_pks(db_at_head) == before


def test_serve_refuses_a_database_from_an_older_revision(
    cli_runner: CliRunner, isolated_data_dir: Path
) -> None:
    """The same refusal from the other direction: a real revision-0001 file, not a downgrade."""
    shutil.copyfile(FIXTURE_0001, db_path_for(isolated_data_dir))
    result = cli_runner.invoke(cli.app, ["serve"])
    assert result.exit_code == ExitCode.CONFIG


def test_serve_refuses_unresolvable_settings(
    cli_runner: CliRunner, db_at_head: Path, monkeypatch
) -> None:
    monkeypatch.setenv("THREADDIGEST_SETTINGS_FILE", str(db_at_head / "does-not-exist.yaml"))
    result = cli_runner.invoke(cli.app, ["serve"])
    assert result.exit_code == ExitCode.CONFIG


def test_serve_refuses_to_start_a_server_under_pytest(
    cli_runner: CliRunner, db_at_head: Path
) -> None:
    """The guard immediately before the one line that opens a socket, with every precondition
    met: this is the test that would hang if the guard were ever removed."""
    result = cli_runner.invoke(cli.app, ["serve"])
    assert result.exit_code == ExitCode.CONFIG
    assert "under pytest" in result.output
    assert "TestClient" in result.output


def test_serve_takes_a_port_and_no_host(cli_runner: CliRunner) -> None:
    """The plan's command line is ``serve [--port 8765]``: binding elsewhere is a decision.

    Invoked with colour off (KI-037): rich's help renderer can interleave ``--port`` with
    ANSI escapes on a runner it believes is a terminal, which breaks a plain substring
    check without changing what the help text says.
    """
    result = cli_runner.invoke(cli.app, ["serve", "--help"], env=_NO_COLOR_ENV)
    help_text = _strip_ansi(result.output)
    assert "--port" in help_text
    assert "--host" not in help_text
    assert cli.SERVE_HOST == "127.0.0.1"


def test_a_port_outside_the_range_is_a_usage_error(cli_runner: CliRunner) -> None:
    assert cli_runner.invoke(cli.app, ["serve", "--port", "0"]).exit_code == 2
    assert cli_runner.invoke(cli.app, ["serve", "--port", "70000"]).exit_code == 2
