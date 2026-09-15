"""CF-01's e2e half: a dry run still pays for the HTTP it makes, even though it writes
nothing (design-round5.md section 11.4, section 16).
"""

from __future__ import annotations

from pathlib import Path

from tests.db.sqlhelp import table_digest

from insightminer import cli
from insightminer.adapters.reddit_fake import FakeRedditGateway
from insightminer.db.engine import db_path_for, engine_for
from insightminer.db.schema import Base


def test_dry_run_counts_http(
    cli_runner, db_at_head: Path, loaded_gateway: FakeRedditGateway, demo_fixture_path: Path
) -> None:
    """A dry run opens a ``mode=ro`` engine and makes zero writes, but the sweep still
    fetches every page: ``fake.requests_made`` is non-zero and the printed summary names
    the same count (section 11.4's last bullet, CF-01's assertion list).
    """
    result = cli_runner.invoke(
        cli.app, ["run", "--dry-run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
    )
    assert result.exit_code == 0, result.output
    assert loaded_gateway.requests_made > 0
    assert str(loaded_gateway.requests_made) in result.output


def test_dry_run_summary_claims_no_rows_written_not_nothing_at_all(
    cli_runner, db_at_head: Path, loaded_gateway: FakeRedditGateway, demo_fixture_path: Path
) -> None:
    """Finding 12 (external round one): the command creates the data directories and the
    read-only engine's sidecar files, so the summary must claim only that no database rows
    were written, never that nothing was written at all."""
    result = cli_runner.invoke(
        cli.app, ["run", "--dry-run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
    )
    assert result.exit_code == 0, result.output
    assert "no database rows written" in result.output
    assert "nothing was written" not in result.output


def test_a_dry_run_whose_source_is_forbidden_exits_3_and_writes_nothing(
    cli_runner, db_at_head: Path, loaded_gateway: FakeRedditGateway, demo_fixture_path: Path
) -> None:
    """round5-findings.json ``P1-dry-run-swallows-failures``, and CF-01's added assertion.

    A dry run's status comes from the SAME warning ledger a real run uses: a source that
    403s is a fact about a fetch the dry run really performed, so the command must exit 3
    and name the source, not report a clean ``ok``. The rest of CF-01 still holds on the
    same invocation -- every table's content hash is unchanged, ``runs`` included.
    """
    loaded_gateway.set_status("editors", "forbidden")
    engine = engine_for(db_path_for(db_at_head))
    try:
        with engine.connect() as conn:
            before = {t: table_digest(conn, t) for t in Base.metadata.tables}
        result = cli_runner.invoke(
            cli.app,
            ["run", "--dry-run", "--gateway", "fake", "--fixture", str(demo_fixture_path)],
        )
        with engine.connect() as conn:
            after = {t: table_digest(conn, t) for t in Base.metadata.tables}
    finally:
        engine.dispose()

    assert result.exit_code == 3, result.output
    assert "editors" in result.output
    assert [t for t in before if before[t] != after[t]] == [], "a dry run wrote to the database"
