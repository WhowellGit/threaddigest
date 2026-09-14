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
from insightminer.db import repo
from insightminer.db.engine import db_path_for, engine_for
from insightminer.db.schema import Base
from insightminer.settings import default_data_dir


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

    **Asserted structurally, on the recorded limit** (round5-findings.json panel P1). The old
    assertions were ``api_requests <= 5000`` -- trivially true, the demo run spends about ten --
    and ``"5000" in options_json``, which ``budget.hard_cap`` satisfies on its own whatever
    ``limit`` holds. Deleting ``cli._budget_for``'s ``min(max(limit, 0), hard_cap)`` left both
    green, so CF-02's gate proved nothing: the clamp would have been enforced only by
    ``Budget.__post_init__``, which is the behaviour this gate exists to prove INDEPENDENTLY.
    The in-range invocation is the contrast case that stops ``limit == 5000`` from passing for
    a constant. 1000 is deliberately neither the hard cap (5000) nor the configured default
    (``per_run_requests``, 1500), and it leaves the demo sweep (about ten requests) affordable
    after the reserve, so the run still ends ``ok``.
    """
    clamped = cli_runner.invoke(
        cli.app,
        ["run", "--budget", "999999", "--gateway", "fake", "--fixture", str(demo_fixture_path)],
    )
    assert clamped.exit_code == 0, clamped.output
    budget = json.loads(table_rows("runs")[-1]["options_json"])["budget"]
    assert budget["limit"] == 5000, "the requested 999999 was not clamped to the hard cap"
    assert budget["hard_cap"] == 5000
    assert budget["reserve"] <= budget["limit"]

    in_range = cli_runner.invoke(
        cli.app,
        ["run", "--budget", "1000", "--gateway", "fake", "--fixture", str(demo_fixture_path)],
    )
    assert in_range.exit_code == 0, in_range.output
    unclamped = json.loads(table_rows("runs")[-1]["options_json"])["budget"]
    assert unclamped["limit"] == 1000, "an in-range --budget must be recorded as asked"
    assert unclamped["hard_cap"] == 5000


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


REFUSAL_SENTENCE = "--gateway fake is refused against the default data directory"


def _default_data_dir_state() -> tuple[bool, int, int] | None:
    """``(exists, size, mtime_ns)`` of the REAL default database, or ``None`` when absent.

    Stat, never open: this is the developer's own ``./data``, and a gate must not read, write
    or create anything in it. Any run against it -- a run row, a seeded source stamped
    ``not_found`` -- changes the file's size or mtime, and a created file changes ``None`` into
    a tuple, so one comparison covers both machines: the one where the shipped default
    database exists and CI, where it does not.
    """
    db_path = db_path_for(default_data_dir().resolve())
    if not db_path.is_file():
        return None
    stat = db_path.stat()
    return True, stat.st_size, stat.st_mtime_ns


@pytest.mark.gate("CF-02")
def test_fake_gateway_refused_against_the_default_data_dir(
    cli_runner, monkeypatch: pytest.MonkeyPatch
) -> None:
    """section 11.3 step 2 (D-10): ``--gateway fake`` is refused when ``settings.data_dir``
    resolves to the REAL default directory -- distinct from ``Settings``' own pytest
    refusal, so ``INSIGHTMINER_ALLOW_REAL_DATA_DIR`` is set here to isolate it.

    **The message, not just the code** (round5-findings.json panel P1). This is the one test
    that runs with the data-directory safety net switched off, and it asserted only
    ``exit_code == 78`` -- which step 4's missing-database precondition also returns. On CI,
    where no default database exists, it therefore passed whether or not ``_guard_gateway``
    existed at all; on a machine where the shipped ``./data/insightminer.db`` does exist, a
    regression in the guard would have driven a real fake-gateway run against live data (a run
    row, and every seeded source stamped ``not_found`` with ``consecutive_failures``
    incremented) and the test would still have gone green. Asserting the sentence
    discriminates the guard from the precondition, and the stat comparison proves nothing was
    written or created either way.
    """
    monkeypatch.setenv("INSIGHTMINER_ALLOW_REAL_DATA_DIR", "1")
    monkeypatch.delenv("INSIGHTMINER_DATA_DIR", raising=False)
    before = _default_data_dir_state()

    result = cli_runner.invoke(cli.app, ["run", "--gateway", "fake"])

    assert result.exit_code == 78, result.output
    assert REFUSAL_SENTENCE in result.output, result.output
    assert _default_data_dir_state() == before, "the refused run touched the real data dir"


@pytest.mark.gate("CF-02")
def test_fake_gateway_refused_against_a_database_holding_real_runs(
    cli_runner, db_at_head: Path, loaded_gateway: FakeRedditGateway, demo_fixture_path: Path
) -> None:
    """The content half of D-10 (round5-findings.json panel P1).

    ``_guard_gateway`` refused the fake only when ``settings.data_dir`` IS the default
    directory, so every relocated data directory -- which doctor's own
    ``data_dir_outside_tcc`` check pushes operators towards -- was unprotected, and nothing
    else in the database distinguished fabricated rows from real ones. The guard is
    content-based now: a ``kind='run'`` row whose recorded gateway is not ``fake`` means this
    database holds real data, and the fake is refused against it wherever it lives.

    Planted through ``repo.insert_run`` with a praw-shaped ``options_json``, which is exactly
    what ``cli._options_json`` writes for a real run.
    """
    engine = engine_for(db_path_for(db_at_head))
    try:
        with engine.begin() as conn:
            repo.insert_run(
                conn,
                repo.RunInsert(
                    kind="run",
                    trigger="cli",
                    status="ok",
                    created_at=1,
                    started_at=1,
                    pid=None,
                    stage=None,
                    options_json=json.dumps({"gateway": "praw", "dry_run": False}),
                    app_version=None,
                    praw_version=None,
                    schema_rev=None,
                    settings_fingerprint=None,
                    log_path=None,
                ),
            )
    finally:
        engine.dispose()

    args = ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
    refused = cli_runner.invoke(cli.app, args)

    assert refused.exit_code == 78, refused.output
    assert "already holds real collection runs" in refused.output
    assert "praw" in refused.output
    assert loaded_gateway.factory_calls == [], "the gateway was constructed before the refusal"
    assert loaded_gateway.requests_made == 0

    # The opt-in exists, needs a reason, and is recorded like every other bypass flag.
    missing_reason = cli_runner.invoke(cli.app, [*args, "--allow-fake-against-real-data"])
    assert missing_reason.exit_code == 2, missing_reason.output

    allowed = cli_runner.invoke(
        cli.app, [*args, "--allow-fake-against-real-data", "--reason", "restoring a demo"]
    )
    assert allowed.exit_code == 0, allowed.output
