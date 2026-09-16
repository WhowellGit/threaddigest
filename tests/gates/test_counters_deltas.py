"""DB-54: the run's counters equal the tracked tables' row-count deltas, through a real
CLI run, with a planted control that fails it (design-round5.md section 13, section 16).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from sqlalchemy import insert

from threaddigest import cli
from threaddigest.adapters.reddit_fake import FakeRedditGateway
from threaddigest.db import repo
from threaddigest.db.engine import db_path_for, engine_for
from threaddigest.db.schema import Base


def _minimal_post_values(reddit_id: str, subreddit_pk: int, now: int) -> dict[str, object]:
    return {
        "reddit_id": reddit_id,
        "fullname": f"t3_{reddit_id}",
        "subreddit_pk": subreddit_pk,
        "author": "planted",
        "author_fullname": "t2_planted",
        "title": "planted extra row",
        "selftext": "",
        "url": "https://example.com/planted",
        "permalink": "/r/planted/comments/planted/",
        "created_utc": now,
        "first_seen_at": now,
        "last_fetched_at": now,
        "next_check_at": now + 86_400,
        "source": "subreddit_new",
        "normalizer_version": 1,
        "raw_json": "{}",
        "content_state": "live",
        "removed_by_category": None,
    }


@pytest.mark.gate("DB-54")
def test_counters_equal_table_deltas_on_a_clean_run(
    cli_runner,
    db_at_head: Path,
    loaded_gateway: FakeRedditGateway,
    demo_fixture_path: Path,
    table_rows,
) -> None:
    result = cli_runner.invoke(
        cli.app, ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
    )
    assert result.exit_code == 0, result.output
    run_row = table_rows("runs")[-1]
    counters = json.loads(run_row["counters_json"])
    assert counters["posts_new"] == len(table_rows("posts"))
    assert counters["rejects"] == len(table_rows("raw_rejects"))
    assert json.loads(run_row["violations_json"]) == []


@pytest.mark.gate("DB-54")
def test_planted_extra_row_fails_the_run(
    cli_runner,
    db_at_head: Path,
    cli_gateway: FakeRedditGateway,
    demo_fixture_path: Path,
    table_rows,
) -> None:
    """A second connection inserts one hand-made ``posts`` row at ``fake.on_call("page", 1)``
    (section 13.2's planted control): Δposts then exceeds ``posts_new`` and the run ends
    ``failed`` with ``counters_equal_table_deltas`` named in ``runs.violations_json``.
    """
    cli_gateway.load_fixture(str(demo_fixture_path))

    def _plant() -> None:
        engine = engine_for(db_path_for(db_at_head))
        try:
            with engine.connect() as conn:
                workspace_pk = repo.default_workspace_pk(conn)
                source = repo.enabled_subreddits(conn, workspace_pk)[0]
            with engine.begin() as conn:
                conn.execute(
                    insert(Base.metadata.tables["posts"]).values(
                        **_minimal_post_values("plantedrow1", source.pk, now=1_800_000_000)
                    )
                )
        finally:
            engine.dispose()

    cli_gateway.on_call("page", 1, _plant)

    result = cli_runner.invoke(
        cli.app, ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
    )
    assert result.exit_code == 1, result.output
    run_row = table_rows("runs")[-1]
    assert run_row["status"] == "failed"
    violations = json.loads(run_row["violations_json"])
    names = {v["invariant"] for v in violations}
    assert "counters_equal_table_deltas" in names
