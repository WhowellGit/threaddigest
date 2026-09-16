"""GT-02 / DB-20: three reruns through the CLI over an unchanged fixture leave every
post's ``pk`` and ``first_seen_at`` unchanged (design-round5.md section 14.2, section 16).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from threaddigest import cli
from threaddigest.adapters.reddit_fake import FakeRedditGateway


@pytest.mark.gate("GT-02")
def test_three_reruns_keep_pk_and_first_seen_at(
    cli_runner,
    db_at_head: Path,
    loaded_gateway: FakeRedditGateway,
    demo_fixture_path: Path,
    table_rows,
) -> None:
    args = ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]

    first = cli_runner.invoke(cli.app, args)
    assert first.exit_code == 0, first.output
    snapshot = {row["reddit_id"]: (row["pk"], row["first_seen_at"]) for row in table_rows("posts")}
    assert snapshot, "no posts written by the first run"

    for attempt in range(2, 4):
        result = cli_runner.invoke(cli.app, args)
        assert result.exit_code == 0, f"run #{attempt}: {result.output}"
        again = {row["reddit_id"]: (row["pk"], row["first_seen_at"]) for row in table_rows("posts")}
        assert again == snapshot, f"pk/first_seen_at drifted on run #{attempt}"
