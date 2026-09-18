"""The tree stage: the due queue, the skip, the stub accounting, the budget and the failures
(M1b design memo § C.1-C.8; TR-01, TR-02 and TR-04 of ``docs/TEST_STRATEGY.md``).

Every test drives the fake gateway against a temp database migrated to head by the
``engine`` fixture, and every post is planted through the real sweep rather than by hand:
the tree stage reads what the sweep wrote (``num_comments``, ``created_utc``,
``check_stage``), so a hand-planted row would test the stage against a shape production
never produces.

The budget is set explicitly after the sweep, as ``--budget N`` does
(``services/collect.py``), and always as *the requests the sweep already spent* plus the
spendable ones this test wants: ``runs.sync_budget`` reads the gateway's own counter, so a
budget written as a bare number would silently include the sweep's page.
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from threaddigest.core.budget import DEFAULT_HARD_CAP, Budget
from threaddigest.core.retry import RunStatus
from threaddigest.db.engine import engine_for
from threaddigest.db.schema import Base
from threaddigest.ports import TransientError
from threaddigest.services import runs, sweep, trees
from threaddigest.settings import Settings

BASE = 1_757_700_000  # matches tests/conftest.py's ``seeded`` fixture
DAY = 86_400


def _reddit_id(fullname: str) -> str:
    """Strip the ``t3_``/``t1_`` prefix a ``fake.add_post``/``add_comment`` call returns."""
    return fullname.split("_", 1)[1]


def _post_row(engine: Any, reddit_id: str) -> dict[str, Any]:
    posts = Base.metadata.tables["posts"]
    with engine.connect() as conn:
        row = conn.execute(select(posts).where(posts.c.reddit_id == reddit_id)).mappings().one()
    return dict(row)


def _comments_of(engine: Any, post_pk: int) -> list[str]:
    comments = Base.metadata.tables["comments"]
    with engine.connect() as conn:
        return [
            str(body)
            for body in conn.execute(
                select(comments.c.body).where(comments.c.post_pk == post_pk)
            ).scalars()
        ]


def _more_rows(engine: Any, post_pk: int) -> list[dict[str, Any]]:
    more = Base.metadata.tables["comment_more"]
    with engine.connect() as conn:
        rows = conn.execute(select(more).where(more.c.post_pk == post_pk)).mappings().all()
    return [dict(row) for row in rows]


def _author_row(engine: Any, name: str) -> dict[str, Any]:
    authors = Base.metadata.tables["authors"]
    with engine.connect() as conn:
        row = conn.execute(select(authors).where(authors.c.name == name)).mappings().one()
    return dict(row)


def _comment_settings(monkeypatch: pytest.MonkeyPatch, **overrides: int) -> Settings:
    """Settings with ``comments.*`` overridden through the environment, as § 11.5 resolves it."""
    for key, value in overrides.items():
        monkeypatch.setenv(f"THREADDIGEST_STATIC__COMMENTS__{key.upper()}", str(value))
    return Settings()


def _budget(fake: Any, *, spendable: int, reserve: int = 0) -> Budget:
    """A budget leaving exactly ``spendable`` requests above ``reserve``, from here on."""
    return Budget(
        limit=fake.requests_made + spendable + reserve, reserve=reserve, hard_cap=DEFAULT_HARD_CAP
    )


def _swept(ctx: Any, fake: Any, add_source: Any, notifier: Any) -> None:
    """Sweep r/premiere into the database so its posts are stored, due and countable."""
    source = add_source("premiere")
    sweep.sweep_subreddit(ctx, source, gateway=fake, notifier=notifier)


def _two_stubs(fake: Any, *, title: str = "busy", created_utc: int = BASE) -> str:
    """A post with two visible top comments, each hiding one reply behind its own stub."""
    fullname = fake.add_post("premiere", title=title, created_utc=created_utc)
    for n in ("one", "two"):
        top = fake.add_comment(
            fullname, body=f"visible {n}", author=f"talker{n}", created_utc=created_utc + 1
        )
        hidden = fake.add_comment(
            fullname,
            parent=top,
            body=f"hidden {n}",
            author=f"quiet{n}",
            created_utc=created_utc + 2,
        )
        fake.add_more(fullname, top, 1, [hidden])
    return fullname


def _names(ctx: Any) -> list[str]:
    return [warning.name for warning in ctx.warnings]


# --- TR-04: the queue's order and the reserve ----------------------------------------------


def test_the_queue_drains_newest_first_and_stops_at_the_reserve(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, engine: Any
) -> None:
    """TR-04, memo § C.1: ``repo.due_posts`` is ordered by ``created_utc`` descending, and the
    stage stops while the reserve is still untouched, leaving the rest of the queue due."""
    fake.add_subreddit("premiere")
    ids: dict[str, str] = {}
    for name, offset in (("oldest", 0), ("middle", 60), ("newest", 120)):
        fullname = fake.add_post("premiere", title=name, created_utc=BASE + offset)
        fake.add_comment(fullname, body=f"reply to {name}", created_utc=BASE + offset + 1)
        ids[name] = _reddit_id(fullname)
    _swept(run_context, fake, add_source, notifier)

    run_context.budget = _budget(fake, spendable=2, reserve=1)
    result = trees.collect_trees(run_context, gateway=fake, settings=run_context.settings)

    assert fake.fullnames_requested("fetch_tree") == [
        f"t3_{ids['newest']}",
        f"t3_{ids['middle']}",
    ]
    assert [outcome.reddit_id for outcome in result.trees] == [ids["newest"], ids["middle"]]
    assert result.stop_reason == "budget"
    assert "tree_budget_exhausted" in _names(run_context)
    assert run_context.budget.spendable == 0  # the reserve is still whole
    assert run_context.budget.used == run_context.budget.limit - 1
    oldest = _post_row(engine, ids["oldest"])
    assert oldest["comments_fetched_at"] is None
    assert oldest["check_stage"] == 0  # untouched, so the next run picks it up
    assert run_context.counters.trees_fetched == 2


# --- TR-01: a post with no comments ---------------------------------------------------------


def test_a_post_with_no_comments_skips_the_fetch_and_still_advances_the_ladder(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, engine: Any
) -> None:
    """TR-01, memo § C.2 and § C.3: no request is spent, the ladder still moves (or the post
    stays due forever), and ``comments_complete`` stays false because no tree was read."""
    fake.add_subreddit("premiere")
    quiet = _reddit_id(fake.add_post("premiere", title="nobody replied", created_utc=BASE))
    _swept(run_context, fake, add_source, notifier)
    spent_by_the_sweep = fake.requests_made

    result = trees.collect_trees(run_context, gateway=fake, settings=run_context.settings)

    assert fake.count("fetch_tree") == 0
    assert fake.requests_made == spent_by_the_sweep
    row = _post_row(engine, quiet)
    assert row["comments_fetched_at"] is None
    assert row["comments_captured"] == 0
    assert row["comments_complete"] == 0
    assert row["check_stage"] == 1
    assert row["next_check_at"] == BASE + 3 * DAY  # the second rung, not the first again
    assert run_context.counters.trees_skipped_empty == 1
    assert run_context.counters.trees_fetched == 0
    assert result.trees[0].skipped is True
    assert _names(run_context) == []  # a quiet post is not a warning


# --- TR-02: the stubs, their reason, and which bound stopped the expansion -------------------


def test_unexpanded_stubs_land_in_comment_more_with_their_reason(
    fake: Any,
    add_source: Any,
    notifier: Any,
    engine: Any,
    clock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TR-02, memo § C.4 and § C.5: what one pass could not expand is written to
    ``comment_more`` with ``more_skipped_reason`` naming the bound that stopped it."""
    settings = _comment_settings(monkeypatch, replace_more_limit=1, per_post_expansion_cap=40)
    ctx = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)
    fake.add_subreddit("premiere")
    post_id = _reddit_id(_two_stubs(fake))
    _swept(ctx, fake, add_source, notifier)
    before = fake.requests_made

    ctx.budget = _budget(fake, spendable=50)
    trees.collect_trees(ctx, gateway=fake, settings=settings)

    row = _post_row(engine, post_id)
    assert fake.requests_made - before == 2  # the base fetch plus the one expansion allowed
    assert sorted(_comments_of(engine, row["pk"])) == ["hidden one", "visible one", "visible two"]
    stubs = _more_rows(engine, row["pk"])
    assert [stub["count"] for stub in stubs] == [1]
    assert stubs[0]["parent_comment_pk"] is not None  # the stub hangs off a comment we hold
    assert row["more_skipped"] == 1
    assert row["more_skipped_count"] == 1
    assert row["more_skipped_reason"] == "limit"
    assert row["comments_complete"] == 0
    assert row["comments_captured"] == 3
    assert row["comments_fetched_at"] == clock.now()
    assert ctx.counters.more_stubs == 1
    assert ctx.counters.comments_new == 3
    assert "tree_incomplete_cap" in _names(ctx)
    # The commenters are people this run saw for the first time: identity and counts both.
    assert _author_row(engine, "quietone")["comment_count"] == 1


def test_the_per_post_cap_stops_expansion_before_replace_more_limit(
    fake: Any,
    add_source: Any,
    notifier: Any,
    engine: Any,
    clock: Any,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """TR-02, ruled per fetch by D-41: with the cap below ``replace_more_limit`` it is the cap
    that binds, and ``more_skipped_reason`` says so rather than blaming the limit."""
    settings = _comment_settings(monkeypatch, replace_more_limit=16, per_post_expansion_cap=1)
    ctx = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)
    fake.add_subreddit("premiere")
    post_id = _reddit_id(_two_stubs(fake))
    _swept(ctx, fake, add_source, notifier)
    before = fake.requests_made

    ctx.budget = _budget(fake, spendable=50)
    trees.collect_trees(ctx, gateway=fake, settings=settings)

    row = _post_row(engine, post_id)
    assert fake.requests_made - before == 2  # one expansion, although the limit allowed sixteen
    assert row["more_skipped_reason"] == "cap"
    assert row["more_skipped_count"] == 1
    assert row["comments_complete"] == 0


# --- the budget, mid-tree and at the hard cap ------------------------------------------------


def test_a_budget_stop_mid_tree_commits_what_was_fetched(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, engine: Any
) -> None:
    """Memo § C.4: one transaction per tree bounds the *write*, not the fetch. What the budget
    paid for is committed, with the rest recorded as stubs reasoned ``budget``."""
    fake.add_subreddit("premiere")
    post_id = _reddit_id(_two_stubs(fake))
    _swept(run_context, fake, add_source, notifier)

    run_context.budget = _budget(fake, spendable=2)  # the base fetch plus one expansion
    result = trees.collect_trees(run_context, gateway=fake, settings=run_context.settings)

    row = _post_row(engine, post_id)
    assert sorted(_comments_of(engine, row["pk"])) == ["hidden one", "visible one", "visible two"]
    assert row["more_skipped_reason"] == "budget"
    assert row["more_skipped_count"] == 1
    assert row["comments_fetched_at"] == run_context.clock.now()
    assert row["check_stage"] == 1  # the fetch succeeded, so the ladder advanced
    assert run_context.counters.comments_new == 3
    assert run_context.counters.trees_fetched == 1
    assert run_context.counters.trees_complete == 0
    assert result.trees[0].more_skipped_reason == "budget"
    assert "tree_budget_exhausted" in _names(run_context)


def test_the_hard_cap_is_never_crossed_by_the_tree_stage(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, engine: Any
) -> None:
    """N-06: the hard cap bounds a requested limit, so no budget a flag can ask for lets the
    stage spend past it -- and the stage stops on the budget it was given, not its own count."""
    fake.add_subreddit("premiere")
    for n in range(3):
        _two_stubs(fake, title=f"busy {n}", created_utc=BASE + n * 60)
    _swept(run_context, fake, add_source, notifier)
    cap = fake.requests_made + 4

    run_context.budget = Budget(limit=9_999, reserve=0, hard_cap=cap)
    result = trees.collect_trees(run_context, gateway=fake, settings=run_context.settings)

    assert run_context.budget.limit == cap  # the asked-for 9,999 was clamped on construction
    assert fake.requests_made <= cap
    assert run_context.budget.used <= cap
    assert run_context.budget.overspent == 0
    assert result.stop_reason == "budget"
    assert len(result.trees) < 3  # something was left due rather than fetched past the cap


# --- failures: one tree, and the whole stage -------------------------------------------------


def test_a_transient_tree_failure_warns_and_leaves_the_post_due(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, engine: Any
) -> None:
    """The 30/120/300 ladder runs per tree; when it is exhausted the post stays due, the run
    records the failure by name, and the next post is still collected."""
    fake.add_subreddit("premiere")
    broken = fake.add_post("premiere", title="broken", created_utc=BASE + 60)
    fake.add_comment(broken, body="unreachable", created_utc=BASE + 61)
    fine = fake.add_post("premiere", title="fine", created_utc=BASE)
    fake.add_comment(fine, body="reachable", created_utc=BASE + 1)
    _swept(run_context, fake, add_source, notifier)
    fake.fail_tree(broken, TransientError("upstream 503"), times=None)

    run_context.budget = _budget(fake, spendable=50)
    result = trees.collect_trees(run_context, gateway=fake, settings=run_context.settings)

    assert run_context.clock.sleeps == [30.0, 120.0, 300.0]
    failures = [w for w in run_context.warnings if w.name == "tree_fetch_failed"]
    assert len(failures) == 1
    assert _reddit_id(broken) in failures[0].detail
    still_due = _post_row(engine, _reddit_id(broken))
    assert still_due["comments_fetched_at"] is None
    assert still_due["check_stage"] == 0  # a transient failure does NOT advance the ladder
    assert _post_row(engine, _reddit_id(fine))["comments_fetched_at"] == run_context.clock.now()
    assert run_context.counters.trees_fetched == 1
    assert [outcome.error is None for outcome in result.trees] == [False, True]


def test_a_rate_limited_tree_stops_the_stage(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, engine: Any
) -> None:
    """A second 429 on one tree ends the stage with ``rate_limited`` rather than hammering; the
    stage returns it as ``collect`` reads it and never lets it escape (the one catch site)."""
    fake.add_subreddit("premiere")
    first = fake.add_post("premiere", title="first", created_utc=BASE + 60)
    fake.add_comment(first, body="one", created_utc=BASE + 61)
    second = fake.add_post("premiere", title="second", created_utc=BASE)
    fake.add_comment(second, body="two", created_utc=BASE + 1)
    _swept(run_context, fake, add_source, notifier)
    fake.rate_limit_next(retry_after=10.0, times=2)

    run_context.budget = _budget(fake, spendable=50)
    result = trees.collect_trees(run_context, gateway=fake, settings=run_context.settings)

    assert result.terminal_status is RunStatus.RATE_LIMITED
    assert run_context.clock.sleeps == [10.0]  # waited once, then gave the run up
    assert fake.fullnames_requested("fetch_tree") == [f"t3_{_reddit_id(first)}"] * 2
    assert _post_row(engine, _reddit_id(second))["comments_fetched_at"] is None
    assert run_context.counters.trees_fetched == 0


def test_the_counters_are_folded_only_from_committed_writes(
    fake: Any,
    add_source: Any,
    notifier: Any,
    engine: Any,
    db_path: Any,
    clock: Any,
    settings: Any,
    snapshot_tables: Any,
) -> None:
    """P0-2, memo § C.6: a tree whose transaction is refused moves no counter and leaves no
    row, so ``counters_equal_table_deltas`` cannot fire against the collector itself."""
    fake.add_subreddit("premiere")
    post_id = _reddit_id(_two_stubs(fake))
    writer = engine_for(db_path, busy_timeout_ms=300)
    try:
        ctx = runs.start_run(writer, kind="run", trigger="cli", clock=clock, settings=settings)
        _swept(ctx, fake, add_source, notifier)
        before = snapshot_tables(list(runs.TRACKED_TABLES))
        spent = fake.requests_made
        ctx.budget = _budget(fake, spendable=50)
        # The lock is taken from inside the gateway, at the start of the tree fetch, so it is
        # held across the tree's own transaction only -- the loop's heartbeat sits outside the
        # per-post handler (the sweep's § 6.2 note 8) and has already been written.
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock_conn:
            fake.on_call("tree", 1, lambda: lock_conn.exec_driver_sql("BEGIN IMMEDIATE"))
            result = trees.collect_trees(ctx, gateway=fake, settings=settings)
            lock_conn.exec_driver_sql("ROLLBACK")
    finally:
        writer.dispose()

    after = snapshot_tables(list(runs.TRACKED_TABLES))
    assert fake.requests_made > spent  # the tree WAS fetched; only its write was refused
    assert after == before  # nothing committed, so every delta is zero
    assert ctx.counters.comments_new == after["comments"] - before["comments"] == 0
    assert ctx.counters.comments_updated == 0
    assert ctx.counters.more_stubs == 0
    assert ctx.counters.trees_fetched == 0
    assert _post_row(engine, post_id)["comments_fetched_at"] is None
    assert isinstance(result.trees[0].error, str)
    assert "tree_write_failed" in _names(ctx)


def test_a_fatal_tree_error_is_recorded_once_and_never_retried(
    fake: Any, add_source: Any, run_context: Any, notifier: Any
) -> None:
    """The control for the ladder test: a failure ``core.retry.classify`` calls fatal is
    recorded and the stage moves on, without spending the ladder's 450 seconds on it.

    ``fetch_tree`` on a post the world no longer holds raises the gateway's base error, which
    is the shape a post deleted between the sweep and the tree stage arrives in.
    """
    fake.add_subreddit("premiere")
    fullname = fake.add_post("premiere", title="vanishes", created_utc=BASE)
    fake.add_comment(fullname, body="gone by then", created_utc=BASE + 1)
    _swept(run_context, fake, add_source, notifier)
    fake.vanish(fullname)

    run_context.budget = _budget(fake, spendable=50)
    result = trees.collect_trees(run_context, gateway=fake, settings=run_context.settings)

    assert [w.name for w in run_context.warnings] == ["tree_fetch_failed"]
    assert run_context.clock.sleeps == []  # a fatal error is never retried on the ladder
    assert result.trees[0].error is not None
    assert run_context.counters.trees_fetched == 0


# --- the malformed item, the ceiling and the dry run ------------------------------------------


def test_a_malformed_comment_is_rejected_and_the_tree_still_commits(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, engine: Any, snapshot_tables: Any
) -> None:
    """NM-01's tree half: one unnormalizable comment costs its own row and nothing else.

    The reject is stored *and* counted inside the tree's own transaction, because
    ``counters.rejects`` is tied to the ``raw_rejects`` delta by a FAILURE invariant: storing
    it without counting it, or counting it without storing it, reports the collector broken.
    """
    fake.add_subreddit("premiere")
    fullname = fake.add_post("premiere", title="one good one bad", created_utc=BASE)
    fake.add_comment(fullname, body="well formed", created_utc=BASE + 1)
    broken = fake.add_comment(fullname, body="malformed", created_utc=BASE + 2)
    fake.remove_field(broken, "created_utc")  # a required key of every comment
    _swept(run_context, fake, add_source, notifier)
    before = snapshot_tables(["raw_rejects"])

    run_context.budget = _budget(fake, spendable=50)
    trees.collect_trees(run_context, gateway=fake, settings=run_context.settings)

    row = _post_row(engine, _reddit_id(fullname))
    assert _comments_of(engine, row["pk"]) == ["well formed"]
    assert snapshot_tables(["raw_rejects"])["raw_rejects"] - before["raw_rejects"] == 1
    assert run_context.counters.rejects == 1
    assert run_context.counters.comments_new == 1
    assert row["comments_captured"] == 1  # what was written, never what the wire held
    assert row["comments_complete"] == 1  # a reject is not an unexpanded stub


def test_the_wall_clock_ceiling_stops_the_stage_before_the_next_tree(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, engine: Any
) -> None:
    """The run's ceiling ends the stage after the current tree, recorded under the sweep's own
    warning name: one ceiling reached is one fact about the run, whichever stage reaches it."""
    fake.add_subreddit("premiere")
    fullname = fake.add_post("premiere", title="late", created_utc=BASE)
    fake.add_comment(fullname, body="never read", created_utc=BASE + 1)
    _swept(run_context, fake, add_source, notifier)
    run_context.budget = _budget(fake, spendable=50)
    run_context.clock.advance(4 * 3600)  # past the three-hour ceiling start_run computed

    result = trees.collect_trees(run_context, gateway=fake, settings=run_context.settings)

    assert result.stop_reason == "ceiling"
    assert fake.count("fetch_tree") == 0
    assert "wall_clock_ceiling" in _names(run_context)
    assert _post_row(engine, _reddit_id(fullname))["comments_fetched_at"] is None


def test_a_dry_run_fetches_no_tree_and_writes_nothing(
    fake: Any, add_source: Any, notifier: Any, engine: Any, clock: Any, settings: Any
) -> None:
    """§11.4: a dry run writes nothing, so a tree it fetched could not be committed -- budget
    spent for nothing, and a read-only engine would turn every tree into a write failure."""
    fake.add_subreddit("premiere")
    fullname = fake.add_post("premiere", title="quiet dry run", created_utc=BASE)
    fake.add_comment(fullname, body="unread", created_utc=BASE + 1)
    ctx = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)
    _swept(ctx, fake, add_source, notifier)
    spent = fake.requests_made

    dry = runs.dry_context(engine, kind="run", trigger="cli", clock=clock, settings=settings)
    result = trees.collect_trees(dry, gateway=fake, settings=settings)

    assert result.stop_reason == "dry_run"
    assert result.trees == ()
    assert fake.count("fetch_tree") == 0
    assert fake.requests_made == spent
    assert dry.counters.trees_fetched == 0
    assert _post_row(engine, _reddit_id(fullname))["comments_fetched_at"] is None
