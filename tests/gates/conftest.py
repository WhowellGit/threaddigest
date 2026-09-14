"""``tests/gates/`` needs the same CLI harness ``tests/e2e/`` does (a real ``CliRunner``,
the demo fixture, the ``GATEWAY_FACTORY`` seam, a data dir at head) -- pytest fixtures are
not inherited across sibling packages, so this file mirrors ``tests/e2e/conftest.py``'s
essentials rather than leaving every gate test to rebuild them by hand (design-round5.md
section 11.6, section 16's gate rows).
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from click.testing import Result
from sqlalchemy import select
from typer.testing import CliRunner

from insightminer import cli
from insightminer.adapters.reddit_fake import FakeRedditGateway
from insightminer.db.engine import db_path_for, engine_for
from insightminer.db.schema import Base

#: ``demo_fixture_path`` is the session-scoped, generated corpus from ``tests/conftest.py``
#: (root conftests *are* inherited, so this one does not restate it).


@pytest.fixture
def cli_runner() -> CliRunner:
    return CliRunner()


ExitedCleanly = Callable[[Result], bool]


@pytest.fixture
def exited_cleanly() -> ExitedCleanly:
    """ "Never a traceback": nothing escaped but the ``SystemExit`` a ``typer.Exit`` raises.

    ``CliRunner`` records that one in ``result.exception`` on every non-zero exit, so an exit
    code on its own cannot tell a documented refusal apart from a crash the runner caught.

    Copied from ``tests/e2e/test_run_lock_and_preconditions.py``'s helper of the same name
    rather than imported: ``tests/e2e/`` is not an importable package (no ``__init__.py``,
    unlike ``tests/db/``), and importing a *test module* from another test module would give
    the same file two module identities under pytest's prepend import mode.
    """

    def _cleanly(result: Result) -> bool:
        return result.exception is None or isinstance(result.exception, SystemExit)

    return _cleanly


@pytest.fixture
def cli_gateway(fake: FakeRedditGateway, monkeypatch: pytest.MonkeyPatch) -> FakeRedditGateway:
    """See ``tests/e2e/conftest.py``'s fixture of the same name (section 11.6)."""
    calls: list[Any] = []

    def factory(spec: Any) -> FakeRedditGateway:
        calls.append(spec)
        return fake

    monkeypatch.setattr(cli, "GATEWAY_FACTORY", factory)
    fake.factory_calls = calls  # a plain attribute; see tests/e2e/conftest.py
    return fake


@pytest.fixture
def loaded_gateway(cli_gateway: FakeRedditGateway, demo_fixture_path: Path) -> FakeRedditGateway:
    cli_gateway.load_fixture(str(demo_fixture_path))
    return cli_gateway


@pytest.fixture
def db_at_head(cli_runner: CliRunner, isolated_data_dir: Path) -> Path:
    result = cli_runner.invoke(cli.app, ["db", "init"])
    assert result.exit_code == 0, (
        f"db init failed (expected until cli.py's db group and services/collect.py "
        f"exist): exit {result.exit_code}\n{result.output}"
    )
    return isolated_data_dir


TableRows = Callable[..., list[dict[str, Any]]]


@pytest.fixture
def table_rows(isolated_data_dir: Path) -> TableRows:
    def _rows(table_name: str, run_pk: int | None = None) -> list[dict[str, Any]]:
        table = Base.metadata.tables[table_name]
        stmt = select(table)
        if run_pk is not None:
            stmt = stmt.where(table.c.run_pk == run_pk)
        pk_columns = list(table.primary_key.columns) or [table.c[list(table.columns.keys())[0]]]
        stmt = stmt.order_by(*pk_columns)
        engine = engine_for(db_path_for(isolated_data_dir))
        try:
            with engine.connect() as conn:
                return [dict(row) for row in conn.execute(stmt).mappings().all()]
        finally:
            engine.dispose()

    return _rows
