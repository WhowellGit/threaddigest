"""RL-04: walk the Typer command tree; every mutating command takes the collector lock and
leaves a run row; every excluded command provably writes nothing (design-round5.md section
11.3, section 11.4, section 16).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
import typer
from click.testing import Result
from tests.db.sqlhelp import run_pks, table_digest
from typer.testing import CliRunner

from threaddigest import cli
from threaddigest.db.engine import db_path_for, engine_for
from threaddigest.db.schema import Base
from threaddigest.services import lock

FIXTURE_0001 = Path(__file__).resolve().parents[1] / "fixtures" / "db" / "0001.sqlite"

#: Stands in for the demo corpus inside the argument lists below. The corpus is generated
#: into a session temp directory (``tests/conftest.py``), so there is no path to freeze at
#: import time -- the placeholder is replaced per test by :func:`_with_fixture`.
FIXTURE_PLACEHOLDER = "{fixture}"


def _with_fixture(args: list[str], fixture: Path) -> list[str]:
    return [str(fixture) if arg == FIXTURE_PLACEHOLDER else arg for arg in args]


#: The documented command tree (section 11.1), as a set of space-joined dotted paths.
EXPECTED_COMMAND_TREE = {
    "run",
    "doctor",
    "db init",
    "db upgrade",
    "db current",
    "config validate",
}


def _walk_commands(app: typer.Typer, prefix: str = "") -> set[str]:
    """Every command name the Typer app exposes, walking ``registered_commands`` and
    ``registered_groups`` recursively -- a command added without updating this set is a
    red, not a silent gap (RL-04's own contract).
    """
    names: set[str] = set()
    for command in app.registered_commands:
        name = command.name or (command.callback.__name__ if command.callback else "")
        names.add(f"{prefix}{name}".strip())
    for group in app.registered_groups:
        group_name = group.name or ""
        sub_app = group.typer_instance
        names |= _walk_commands(sub_app, prefix=f"{prefix}{group_name} ")
    return names


def test_the_command_tree_is_exactly_the_documented_one() -> None:
    assert _walk_commands(cli.app) == EXPECTED_COMMAND_TREE


def _prepare_for_run(cli_runner: CliRunner, data_dir: Path) -> None:
    result = cli_runner.invoke(cli.app, ["db", "init"])
    assert result.exit_code == 0, result.output


def _prepare_for_db_init(cli_runner: CliRunner, data_dir: Path) -> None:
    """An empty directory is exactly what "db init on an empty dir" needs: nothing to do.

    The signature matches the other two preparers so the parametrization can call them all
    the same way; both parameters are deliberately unused."""
    del cli_runner, data_dir


def _prepare_for_db_upgrade(cli_runner: CliRunner, data_dir: Path) -> None:
    del cli_runner
    db_path_for(data_dir).write_bytes(FIXTURE_0001.read_bytes())


MUTATING_COMMANDS: list[tuple[str, list[str], Callable[[CliRunner, Path], None]]] = [
    ("run", ["run", "--gateway", "fake", "--fixture", FIXTURE_PLACEHOLDER], _prepare_for_run),
    ("db_init", ["db", "init"], _prepare_for_db_init),
    ("db_upgrade", ["db", "upgrade"], _prepare_for_db_upgrade),
]


def _count_run_rows(data_dir: Path) -> int:
    """How many ``runs`` rows exist, tolerating a database that is absent or below head.

    ``db init`` is exercised on an empty directory (no database file at all) and
    ``db upgrade`` on the revision-0001 fixture (no ``runs.violations_json``), so the
    head-model ``table_rows("runs")`` cannot be used here: it would create an empty file in
    the first case and raise ``no such column`` in the second. ``sqlhelp.run_pks`` is the
    revision-independent read (section 2.3).
    """
    db_path = db_path_for(data_dir)
    if not db_path.is_file():
        return 0
    engine = engine_for(db_path)
    try:
        with engine.connect() as conn:
            return len(run_pks(conn))
    finally:
        engine.dispose()


@pytest.mark.gate("RL-04")
@pytest.mark.parametrize(
    "name,args,prepare", MUTATING_COMMANDS, ids=[case[0] for case in MUTATING_COMMANDS]
)
def test_every_mutating_command_takes_the_lock_and_writes_a_run_row(
    name: str,
    args: list[str],
    prepare: Callable[[CliRunner, Path], None],
    cli_runner: CliRunner,
    isolated_data_dir: Path,
    demo_fixture_path: Path,
) -> None:
    """Runs against the DEFAULT ``GATEWAY_FACTORY`` (section 11.6, item 4): ``run`` builds
    its own ``FakeRedditGateway`` from ``--fixture`` on disk, so the production
    construction path is covered rather than bypassed by a test seam.
    """
    assert name in {case[0] for case in MUTATING_COMMANDS}  # keeps the id list honest
    prepare(cli_runner, isolated_data_dir)
    args = _with_fixture(args, demo_fixture_path)

    lock_path = isolated_data_dir / "locks" / "collector.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock.acquire(lock_path):
        held = cli_runner.invoke(cli.app, args)
    assert held.exit_code == 75, f"{name} did not respect a held lock: {held.output}"

    before = _count_run_rows(isolated_data_dir)
    result = cli_runner.invoke(cli.app, args)
    assert result.exit_code in {0, 1, 3}, f"{name}: {result.output}"
    after = _count_run_rows(isolated_data_dir)
    assert after == before + 1, f"{name} did not write exactly one run row"


#: ``(id, argv, expected exit code)``. Every case here is the command's HAPPY path against a
#: database at head, so the expected code is 0: a command that wrote nothing because it
#: refused to start (78) or died (1) would otherwise pass this gate by doing nothing at all.
EXCLUDED_COMMANDS: list[tuple[str, list[str], int]] = [
    ("doctor", ["doctor", "--no-network"], 0),
    ("config_validate", ["config", "validate"], 0),
    ("db_current", ["db", "current"], 0),
    (
        "run_dry_run",
        ["run", "--dry-run", "--gateway", "fake", "--fixture", FIXTURE_PLACEHOLDER],
        0,
    ),
]


@pytest.mark.gate("RL-04")
@pytest.mark.parametrize(
    "name,args,expected_exit", EXCLUDED_COMMANDS, ids=[case[0] for case in EXCLUDED_COMMANDS]
)
def test_excluded_commands_write_nothing(
    name: str,
    args: list[str],
    expected_exit: int,
    cli_runner: CliRunner,
    db_at_head: Path,
    demo_fixture_path: Path,
    exited_cleanly: Callable[[Result], bool],
) -> None:
    """A dry run opens no writable connection, so it is not a mutating command (section
    11.4); ``doctor``, ``config validate`` and ``db current`` are read-only by construction.
    Every table's content hash -- ``runs`` included -- must be unchanged, not just row
    counts (section 11.4's own falsifiability requirement).

    The exit code is asserted too (panel P2-3 / finding 14). "Wrote nothing" is trivially
    true of a command that never ran: a ``config validate`` refusing at 78, or a dry run
    crashing on its first page, would have kept this gate green while the behaviour it
    guards was gone. ``exited_cleanly`` is the second half of that -- ``CliRunner`` catches
    exceptions and reports them as exit 1, so the code alone cannot tell a refusal from a
    traceback.
    """
    engine = engine_for(db_path_for(db_at_head))
    try:
        with engine.connect() as conn:
            before = {t: table_digest(conn, t) for t in Base.metadata.tables}
        result = cli_runner.invoke(cli.app, _with_fixture(args, demo_fixture_path))
        with engine.connect() as conn:
            after = {t: table_digest(conn, t) for t in Base.metadata.tables}
    finally:
        engine.dispose()
    changed = [t for t in before if before[t] != after.get(t)]
    assert changed == [], f"{name} (exit {result.exit_code}) wrote to: {changed}"
    assert exited_cleanly(result), f"{name} raised: {result.exception!r}\n{result.output}"
    assert result.exit_code == expected_exit, f"{name}: {result.output}"
