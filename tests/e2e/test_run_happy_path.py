"""The definition of done for ``insightminer run``: a first run, a rerun, the counters,
the ``run_subreddits`` rows, ``api_requests``, exit 0, DB-17's WAL truncation and SW-04's
in-process crash recovery (design-round5.md section 16, section 17 step 7, section 11.7).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from insightminer import cli
from insightminer.adapters.reddit_fake import FakeRedditGateway
from insightminer.db.engine import db_path_for

SEED_FILE = Path(__file__).resolve().parents[2] / "config" / "seed.yaml"


def _visible_post_count(fixture_path: Path) -> int:
    """Posts a ``/new`` listing would show: every post minus the fixture's one deleted
    post (section 11.7) -- the fake gateway excludes a deleted post from its listing.
    """
    data = json.loads(fixture_path.read_text(encoding="utf-8"))
    return sum(
        1
        for post in data["posts"]
        if post.get("removed_by_category") != "deleted" and post.get("selftext") != "[deleted]"
    )


def test_every_seeded_source_is_present_in_the_demo_fixture(demo_fixture_path: Path) -> None:
    """section 11.7: the sweep drives off ``config/seed.yaml``; the fake gateway is built
    from the generated demo corpus. The two name lists must agree, restating neither.

    This reads the *generated file*; ``tests/tools/test_make_demo_fixture.py`` reads the
    generator's constants. Both, because a generator that agrees with the seed and a file
    that does not would mean the file came from somewhere else.
    """
    seed = yaml.safe_load(SEED_FILE.read_text(encoding="utf-8"))
    fixture = json.loads(demo_fixture_path.read_text(encoding="utf-8"))
    seed_names = {name.lower() for name in seed["subreddits"]}
    fixture_names = {sub["display_name"].lower() for sub in fixture["subreddits"]}
    assert seed_names == fixture_names


def test_first_run_writes_the_definition_of_done(
    cli_runner, db_at_head, loaded_gateway: FakeRedditGateway, demo_fixture_path: Path, table_rows
) -> None:
    """A clean first run over the demo fixture: exit 0, ``ok``, non-zero ``api_requests``,
    every counter matching what was actually written, and one terminal ``run_subreddits``
    row per seeded source with a non-NULL ``stop_reason``.
    """
    result = cli_runner.invoke(
        cli.app, ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
    )
    assert result.exit_code == 0, result.output

    runs = table_rows("runs")
    run_row = runs[-1]
    assert run_row["status"] == "ok"
    assert run_row["finished_at"] is not None
    assert run_row["api_requests"] > 0
    assert run_row["api_requests"] == loaded_gateway.requests_made

    counters = json.loads(run_row["counters_json"])
    expected_new = _visible_post_count(demo_fixture_path)
    assert counters["posts_new"] == expected_new
    assert counters["rejects"] == 0
    assert counters["warnings"] == 0

    posts = table_rows("posts")
    assert len(posts) == expected_new

    rs_rows = [row for row in table_rows("run_subreddits") if row["run_pk"] == run_row["pk"]]
    by_source = {}
    for row in rs_rows:
        by_source.setdefault(row["subreddit_pk"], []).append(row)
    # exactly one TERMINAL row (stop_reason not NULL) per seeded source, of the three.
    terminal_rows = [row for row in rs_rows if row["stop_reason"] is not None]
    assert len({row["subreddit_pk"] for row in terminal_rows}) == 3
    for row in terminal_rows:
        assert row["stop_reason"] in {"exhausted", "cap"}
        assert row["error"] is None


def test_rerun_after_a_clean_run_reports_zero_new_items(
    cli_runner, db_at_head, loaded_gateway: FakeRedditGateway, demo_fixture_path: Path, table_rows
) -> None:
    """Nothing changed on Reddit between the two invocations, so the rerun writes zero new
    posts and still ends ``ok`` (part of the definition of done).
    """
    args = ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
    first = cli_runner.invoke(cli.app, args)
    assert first.exit_code == 0, first.output
    second = cli_runner.invoke(cli.app, args)
    assert second.exit_code == 0, second.output

    # `db_at_head` runs `db init`, which writes its own `kind='db_init'` run row (T13), so
    # the collection runs are the `kind='run'` rows -- not every row in the table.
    collection_runs = [row for row in table_rows("runs") if row["kind"] == "run"]
    assert len(collection_runs) == 2
    second_counters = json.loads(collection_runs[-1]["counters_json"])
    assert second_counters["posts_new"] == 0


def test_wal_is_truncated_at_end_of_run(
    cli_runner, db_at_head, loaded_gateway: FakeRedditGateway, demo_fixture_path: Path
) -> None:
    """DB-17: ``db.engine.checkpoint_truncate`` runs, outside any transaction, at the end
    of a successful run, so the ``-wal`` sidecar is truncated rather than growing forever.
    """
    result = cli_runner.invoke(
        cli.app, ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
    )
    assert result.exit_code == 0, result.output
    wal_path = db_path_for(db_at_head).with_name(db_path_for(db_at_head).name + "-wal")
    assert not wal_path.exists() or wal_path.stat().st_size == 0


def test_crash_between_pages_commits_earlier_pages_and_rerun_completes(
    cli_runner, db_at_head, loaded_gateway: FakeRedditGateway, demo_fixture_path: Path, table_rows
) -> None:
    """SW-04: ``CrashInjected`` must escape uncaught, **page 1's writes must survive it**,
    and the SECOND run's stale sweep (section 12.2 clause 4: our own pid) stamps the first
    run's row ``crashed`` in-process before completing its own sweep cleanly.

    The first half is the half SW-04 exists for and the half this test used to leave
    untested (round5-findings.json panel P1): asserting only the two run statuses stays green
    against a ``write_page`` whose transaction is widened across pages, or one that rolls the
    last committed page back -- the exact defect. The committed evidence is asserted directly:
    rows in ``posts``, one ``post_sources`` row each, and a ``run_subreddits`` row for run 1
    whose counters equal what is on disk.

    **Not asserted: a ``stop_reason IS NULL`` row.** The panel asked for one, and the demo
    fixture cannot produce it: every seeded source fits in a single ``/new`` page (39 posts for
    the first), so the source that completes before the crash writes its TERMINAL row at
    section 6.3's end-of-loop and the source the crash lands in has written nothing yet. The
    claim SW-04 actually makes -- an earlier page's writes are committed and survive an
    uncaught crash -- is what the counters below pin, and it fails against a widened
    transaction exactly as a NULL-stop_reason assertion would.
    """
    loaded_gateway.crash_after("page", 1)
    args = ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]

    first = cli_runner.invoke(cli.app, args)
    assert first.exit_code != 0 or first.exception is not None

    crashed_run = next(row for row in table_rows("runs") if row["kind"] == "run")
    assert crashed_run["status"] == "running", "CrashInjected was swallowed somewhere"
    posts_from_page_one = table_rows("posts")
    assert len(posts_from_page_one) > 0, "page 1's writes did not survive CrashInjected"
    assert len(table_rows("post_sources")) == len(posts_from_page_one)
    progress = [row for row in table_rows("run_subreddits") if row["run_pk"] == crashed_run["pk"]]
    assert progress, "the crashed run committed no per-source progress"
    assert sum(row["new_items"] for row in progress) == len(posts_from_page_one)
    assert len(posts_from_page_one) < _visible_post_count(demo_fixture_path), (
        "the crash did not stop the sweep early, so nothing about surviving writes is proven"
    )

    second = cli_runner.invoke(cli.app, args)
    assert second.exit_code == 0, second.output

    collection_runs = [row for row in table_rows("runs") if row["kind"] == "run"]
    assert len(collection_runs) == 2
    assert collection_runs[0]["status"] == "crashed"
    assert collection_runs[0]["finished_at"] is not None
    assert collection_runs[1]["status"] == "ok"

    # The rerun adds the posts the crash never reached, and keeps the ones it did.
    posts_after_rerun = table_rows("posts")
    assert len(posts_after_rerun) == _visible_post_count(demo_fixture_path)
    assert len(posts_after_rerun) > len(posts_from_page_one)
    survived = {row["reddit_id"] for row in posts_from_page_one}
    assert survived <= {row["reddit_id"] for row in posts_after_rerun}


def test_keyboard_interrupt_exits_130_and_finishes_the_run_cancelled(
    cli_runner, db_at_head, loaded_gateway: FakeRedditGateway, demo_fixture_path: Path, table_rows
) -> None:
    """section 9: 130 is produced by us, not inherited from click.

    An *uncaught* ``KeyboardInterrupt`` inside a command already yields exit 130 under
    ``CliRunner`` -- and would leave the run row ``running``, which is the failure the
    round-3 finding describes. ``collect`` therefore catches it around the sweep and only
    around the sweep, finishes the row ``cancelled`` with the counters gathered so far and a
    NULL ``violations_json`` (the invariants did not run), and the CLI exits through its
    ordinary ``typer.Exit``. Both halves are asserted here.
    """
    loaded_gateway.fail_next(KeyboardInterrupt)
    result = cli_runner.invoke(
        cli.app, ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
    )
    assert result.exit_code == 130, result.output

    collection_runs = [row for row in table_rows("runs") if row["kind"] == "run"]
    assert len(collection_runs) == 1
    assert collection_runs[0]["status"] == "cancelled"
    assert collection_runs[0]["finished_at"] is not None
    assert collection_runs[0]["violations_json"] is None
