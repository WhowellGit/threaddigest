"""CF-01 / CF-02: a dry run cannot be tricked into writing, the budget cannot exceed the
hard cap, a bypass flag always records its reason, and the fake gateway is refused against
the real data directory (design-round5.md section 11.3-11.5, section 16).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from tests.db.sqlhelp import table_digest

from insightminer import cli
from insightminer.adapters.reddit_fake import FakeRedditGateway
from insightminer.db.engine import db_path_for, engine_for
from insightminer.db.schema import Base


@pytest.mark.gate("CF-01")
def test_dry_run_writes_nothing_anywhere(
    cli_runner, db_at_head: Path, loaded_gateway: FakeRedditGateway, demo_fixture_path: Path
) -> None:
    """Every table's content hash -- ``runs`` included -- is unchanged by a dry run, and
    the sweep still made real HTTP calls against the fake (section 11.4).
    """
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
    assert result.exit_code == 0, result.output
    changed = [t for t in before if before[t] != after.get(t)]
    assert changed == [], f"dry run wrote to: {changed}"
    assert loaded_gateway.requests_made > 0


@pytest.mark.gate("CF-02")
def test_budget_is_clamped_to_the_hard_cap(
    cli_runner,
    db_at_head: Path,
    loaded_gateway: FakeRedditGateway,
    demo_fixture_path: Path,
    table_rows,
) -> None:
    """``--budget 999999`` must not crash ``Budget.__post_init__`` and must not let the run
    spend past ``static.budget.hard_cap`` (5000 in ``config/settings.yaml``); the clamp is
    visible in ``options_json`` (section 11.5).
    """
    result = cli_runner.invoke(
        cli.app,
        ["run", "--budget", "999999", "--gateway", "fake", "--fixture", str(demo_fixture_path)],
    )
    assert result.exit_code == 0, result.output
    row = table_rows("runs")[-1]
    assert row["api_requests"] <= 5000
    assert row["options_json"] is not None
    assert "5000" in row["options_json"]


@pytest.mark.gate("CF-02")
def test_no_comments_requires_a_reason_and_records_it(
    cli_runner,
    db_at_head: Path,
    loaded_gateway: FakeRedditGateway,
    demo_fixture_path: Path,
    table_rows,
) -> None:
    """``--no-comments`` without ``--reason`` is a Typer usage error; with one, both land
    verbatim in ``runs.options_json`` (section 11.3).
    """
    missing_reason = cli_runner.invoke(
        cli.app,
        ["run", "--no-comments", "--gateway", "fake", "--fixture", str(demo_fixture_path)],
    )
    assert missing_reason.exit_code == 2, missing_reason.output

    result = cli_runner.invoke(
        cli.app,
        [
            "run",
            "--no-comments",
            "--reason",
            "testing CF-02",
            "--gateway",
            "fake",
            "--fixture",
            str(demo_fixture_path),
        ],
    )
    assert result.exit_code == 0, result.output
    row = table_rows("runs")[-1]
    options = json.loads(row["options_json"])
    assert options["no_comments"] is True
    assert options["reason"] == "testing CF-02"


@pytest.mark.gate("CF-02")
def test_fake_gateway_refused_against_the_default_data_dir(
    cli_runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """section 11.3 step 2 (D-10): ``--gateway fake`` is refused when ``settings.data_dir``
    resolves to the REAL default directory -- distinct from ``Settings``' own pytest
    refusal, so ``INSIGHTMINER_ALLOW_REAL_DATA_DIR`` is set here to isolate it.
    """
    monkeypatch.setenv("INSIGHTMINER_ALLOW_REAL_DATA_DIR", "1")
    monkeypatch.delenv("INSIGHTMINER_DATA_DIR", raising=False)
    result = cli_runner.invoke(cli.app, ["run", "--gateway", "fake"])
    assert result.exit_code == 78
