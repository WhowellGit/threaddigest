"""SW-01, SW-02, SW-03, SW-07: the ``/new`` page loop, the stop rule, the watermark's
forward-only advance, overlap dedupe and the empty/zero-new shapes
(design-round5.md §6.2, §6.5, §16).

Most tests drive ``sweep._page_loop`` directly, which is where the stop rule and the
fetched-vs-absorbed page counts live (§6.2 note 2); the ones that assert a ``subreddits``
or terminal ``run_subreddits`` write go through ``sweep.sweep_subreddit`` (§6.3), because
that is the only function that opens T6.
"""

from __future__ import annotations

from typing import Any

from insightminer.core.budget import Budget
from insightminer.core.paging import StopReason
from insightminer.services import sweep

BASE = 1_757_700_000  # matches tests/conftest.py's ``seeded`` fixture


# --- SW-01: forward `after` paging only -------------------------------------------------------


def test_sweep_pages_forward_only_and_never_uses_before(
    fake: Any, add_source: Any, run_context: Any
) -> None:
    """Each fetch is a fresh ``iter_new_pages`` call threaded on the PREVIOUS page's ``after``;
    nothing ever asks for an earlier page (the port has no such parameter)."""
    fake.add_subreddit("premiere")
    for i in range(150):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    source = add_source("premiere")

    outcome, exc = sweep._page_loop(run_context, source, gateway=fake)

    assert exc is None
    assert outcome.stop_reason is StopReason.EXHAUSTED
    calls = [c for c in fake.calls if c.method == "iter_new_pages"]
    assert len(calls) == 2
    assert "before" not in calls[0].kwargs
    assert "before" not in calls[1].kwargs
    assert calls[0].kwargs["after"] is None
    assert calls[1].kwargs["after"] is not None
    assert calls[1].kwargs["after"] != calls[0].kwargs["after"]


def test_resume_uses_the_previous_after_cursor(
    seeded: Any, add_source: Any, run_context: Any
) -> None:
    """``seeded`` holds 250 posts (3 pages of 100/100/50): each fetch's ``after`` is exactly the
    PRECEDING fetch's returned cursor, never a stale or restarted one."""
    source = add_source("premiere")

    outcome, exc = sweep._page_loop(run_context, source, gateway=seeded)

    assert exc is None
    assert outcome.stop_reason is StopReason.EXHAUSTED
    assert outcome.pages_fetched == 3
    calls = [c for c in seeded.calls if c.method == "iter_new_pages"]
    afters = [c.kwargs["after"] for c in calls]
    assert afters[0] is None
    # each later call resumes from the one right before it: every non-initial cursor is
    # distinct, never `None` again and never a repeat of an earlier page's cursor.
    assert afters[1] is not None
    assert afters[2] is not None
    assert len({afters[1], afters[2]}) == 2


def test_all_removed_middle_page_does_not_end_the_sweep(
    fake: Any, add_source: Any, run_context: Any
) -> None:
    """The round-3 defect, reproduced and pinned (§6.2): a wholly-deleted middle page is EMPTY
    but not the end of the listing, because the port's ``after``/``complete`` disagree with
    ``plan_stop``'s EXHAUSTED. Trace: page1 len=10, page2 len=0 (ignored), page3 len=10/complete.
    """
    fake.add_subreddit("premiere")
    fullnames = [
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60) for i in range(30)
    ]
    fake.set_page_size("premiere", [10, 10, 10])
    for fn in fullnames[10:20]:
        fake.delete(fn)
    source = add_source("premiere")

    outcome, exc = sweep._page_loop(run_context, source, gateway=fake)

    assert exc is None
    assert outcome.stop_reason is StopReason.EXHAUSTED
    assert outcome.pages_fetched == 3  # HTTP pages: all three were fetched
    assert outcome.state.pages == 2  # absorbed pages: the empty one never counted
    assert run_context.counters.pages == 3


def test_a_page_ceiling_stops_the_subreddit_without_claiming_exhausted(
    fake: Any, add_source: Any, run_context: Any
) -> None:
    """Fail-closed guard 1 (§6.1, §6.2 note 3): a gateway that never ends the listing is
    bounded at ``MAX_PAGES_PER_SUBREDDIT`` and leaves ``stop_reason`` NULL, never EXHAUSTED."""
    fake.add_subreddit("premiere")
    for i in range(sweep.MAX_PAGES_PER_SUBREDDIT + 20):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    fake.set_page_size("premiere", [1] * (sweep.MAX_PAGES_PER_SUBREDDIT + 5))
    source = add_source("premiere")

    outcome, exc = sweep._page_loop(run_context, source, gateway=fake)

    assert exc is None
    assert outcome.stop_reason is None
    assert outcome.pages_fetched == sweep.MAX_PAGES_PER_SUBREDDIT
    assert any(w.name == "page_ceiling" for w in run_context.warnings)


def test_a_non_advancing_cursor_stops_the_subreddit(
    seeded: Any,
    add_source: Any,
    run_context: Any,
    notifier: Any,
    run_subreddit_rows: Any,
    subreddit_row: Any,
) -> None:
    """Fail-closed guard 2, corrected by round5-findings.json finding 1 (P0): a stalled cursor
    leaves ``stop_reason`` NULL -- interrupted, never EXHAUSTED -- so it can never fake
    complete coverage. A full ``sweep_subreddit`` proves the consequence: the watermark, the
    coverage stamp and a standing gap latch are all left exactly where they were."""
    prior_watermark = 1_000
    prior_gap_at = 2_000
    prior_complete_at = 3_000
    source = add_source(
        "premiere",
        watermark_created_utc=prior_watermark,
        gap_suspected_at=prior_gap_at,
        last_complete_poll_at=prior_complete_at,
    )
    seeded.set_overlap("premiere", n=100)  # full overlap of a 100-item page: `after` never moves

    result = sweep.sweep_subreddit(run_context, source, gateway=seeded, notifier=notifier)

    assert result.stop_reason is None
    assert any(w.name == "cursor_stalled" for w in run_context.warnings)
    rows = run_subreddit_rows(run_context.run_pk, source.pk)
    assert len(rows) == 1
    assert rows[0]["stop_reason"] is None
    after = subreddit_row(source.pk)
    assert after.watermark_created_utc == prior_watermark
    assert after.gap_suspected_at == prior_gap_at
    assert after.last_complete_poll_at == prior_complete_at


# --- SW-02: cap + gap + stickies ---------------------------------------------------------------


def test_cap_stop_sets_gap_suspected(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    """A capped sweep whose window does not reach the prior watermark is a real gap (§6.5)."""
    fake.add_subreddit("premiere")
    total = 1050
    for i in range(total):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    # The cap keeps only the newest 1000 posts (indices 50..1049); a prior watermark at index
    # 40 means the window did not reach back far enough -- a genuine gap.
    source = add_source("premiere", watermark_created_utc=BASE + 40 * 60)

    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert result.stop_reason is StopReason.CAP
    after = subreddit_row(source.pk)
    assert after.gap_suspected_at is not None
    assert any(w.name == "gap_suspected" for w in run_context.warnings)
    assert after.last_complete_poll_at is None  # coverage was NOT proven this run


def test_stickies_are_seen_but_excluded_from_the_window(
    fake: Any, add_source: Any, run_context: Any
) -> None:
    """A sticky is counted (seen, upserted) but never moves ``seen_min``/``seen_max`` (§6.2)."""
    fake.add_subreddit("premiere")
    ancient = BASE - 10_000_000
    fake.add_post("premiere", title="pinned", created_utc=ancient, stickied=True)
    for i in range(10):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    source = add_source("premiere")

    outcome, exc = sweep._page_loop(run_context, source, gateway=fake)

    assert exc is None
    assert outcome.state.unique_items == 11
    assert outcome.state.seen_min_created_utc == BASE
    assert outcome.state.seen_max_created_utc == BASE + 9 * 60
    assert run_context.counters.posts_new == 11  # the sticky was still upserted


def test_empty_sweep_leaves_a_prior_watermark_intact(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    """``advance_watermark`` is a no-op when ``seen_max_created_utc`` is None (§5.2, §6.5):
    an empty sweep of an otherwise-known source must never erase what was already known."""
    fake.add_subreddit("premiere")
    prior_watermark = 555_000
    source = add_source("premiere", watermark_created_utc=prior_watermark)

    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert result.stop_reason is StopReason.EXHAUSTED
    assert subreddit_row(source.pk).watermark_created_utc == prior_watermark


def test_a_source_at_the_cap_on_every_run_does_not_accumulate_a_standing_gap(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    """round-4 P0-1 regression: three consecutive capped sweeps with a healthy trickle of new
    posts between them never set a standing gap, because the watermark now advances on CAP
    too (§6.5) -- a capped source polled often enough to keep up must stay ``ok``, not amber."""
    fake.add_subreddit("premiere")
    for i in range(1005):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    source = add_source("premiere")

    from insightminer.services import runs

    ctx = run_context
    for extra in range(3):
        for i in range(5):
            fake.add_post(
                "premiere",
                title=f"trickle {extra}-{i}",
                created_utc=BASE + (1005 + extra * 5 + i) * 60,
            )
        result = sweep.sweep_subreddit(ctx, source, gateway=fake, notifier=notifier)
        assert result.stop_reason is StopReason.CAP
        assert subreddit_row(source.pk).gap_suspected_at is None
        assert not any(w.name == "gap_suspected" for w in ctx.warnings)
        source = subreddit_row(source.pk)
        ctx = runs.start_run(
            ctx.engine, kind="run", trigger="cli", clock=ctx.clock, settings=ctx.settings
        )


# --- SW-03: overlap dedupe ----------------------------------------------------------------------


def test_overlapping_pages_produce_one_row_each(
    seeded: Any, add_source: Any, run_context: Any, snapshot_tables: Any
) -> None:
    """Reddit re-delivers items that shifted between fetches (SW-03); the upsert dedupes them
    into one ``posts`` row each, however many times ``items_seen`` counted the listing slot."""
    seeded.set_overlap("premiere", n=5)
    source = add_source("premiere")

    outcome, exc = sweep._page_loop(run_context, source, gateway=seeded)

    assert exc is None
    assert outcome.stop_reason is StopReason.EXHAUSTED
    assert outcome.state.unique_items == 250
    assert outcome.state.items_seen > 250  # the overlap re-counted some listing slots
    assert snapshot_tables(["posts"])["posts"] == 250
    assert run_context.counters.posts_new == 250


# --- SW-07: empty / zero-new / exhausted shapes -------------------------------------------------


def test_empty_subreddit_is_ok_and_exhausted(
    fake: Any, add_source: Any, run_context: Any, notifier: Any
) -> None:
    fake.add_subreddit("premiere")
    source = add_source("premiere")

    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert result.stop_reason is StopReason.EXHAUSTED
    assert result.status == "ok"
    assert result.items_seen == 0
    assert result.pages == 1


def test_an_empty_subreddit_stamps_last_complete_poll_at(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    """round-5 P1-4: EXHAUSTED always proves coverage, including a listing with nothing (or
    nothing but stickies) to see -- the one case round 4 never stamped."""
    fake.add_subreddit("empty")
    empty_source = add_source("empty")
    result = sweep.sweep_subreddit(run_context, empty_source, gateway=fake, notifier=notifier)
    assert result.stop_reason is StopReason.EXHAUSTED
    assert subreddit_row(empty_source.pk).last_complete_poll_at is not None

    fake.add_subreddit("stickyonly")
    fake.add_post("stickyonly", title="pinned", created_utc=BASE, stickied=True)
    sticky_source = add_source("stickyonly")
    result = sweep.sweep_subreddit(run_context, sticky_source, gateway=fake, notifier=notifier)
    assert result.stop_reason is StopReason.EXHAUSTED
    assert subreddit_row(sticky_source.pk).last_complete_poll_at is not None


def test_fifty_post_subreddit_ends_exhausted(
    fake: Any, add_source: Any, run_context: Any, notifier: Any
) -> None:
    fake.add_subreddit("premiere")
    for i in range(50):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    source = add_source("premiere")

    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert result.stop_reason is StopReason.EXHAUSTED
    assert result.pages == 1
    assert result.items_seen == 50
    assert result.new_items == 50


def test_zero_new_run_records_zero_new_items(
    fake: Any,
    add_source: Any,
    run_context: Any,
    notifier: Any,
    subreddit_row: Any,
    engine: Any,
    clock: Any,
    settings: Any,
) -> None:
    from insightminer.services import runs

    fake.add_subreddit("premiere")
    for i in range(20):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    source = add_source("premiere")

    first = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)
    assert first.new_items == 20

    second_ctx = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)
    refreshed = subreddit_row(source.pk)
    second = sweep.sweep_subreddit(second_ctx, refreshed, gateway=fake, notifier=notifier)

    assert second.new_items == 0
    assert second.stop_reason is StopReason.EXHAUSTED


def test_healthy_sweep_writes_a_non_null_stop_reason(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, run_subreddit_rows: Any
) -> None:
    fake.add_subreddit("premiere")
    for i in range(20):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    source = add_source("premiere")

    sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    rows = run_subreddit_rows(run_context.run_pk, source.pk)
    assert len(rows) == 1
    assert rows[0]["stop_reason"] == "exhausted"


def test_an_interrupted_sweep_leaves_stop_reason_null_and_warns(
    seeded: Any, add_source: Any, run_context: Any, notifier: Any, run_subreddit_rows: Any
) -> None:
    """§19.4: budget exhaustion is one of the five things that leave ``stop_reason`` NULL."""
    source = add_source("premiere")
    run_context.budget = Budget(limit=2, hard_cap=5000)

    result = sweep.sweep_subreddit(run_context, source, gateway=seeded, notifier=notifier)

    assert result.stop_reason is None
    assert any(w.name == "budget_exhausted" for w in run_context.warnings)
    rows = run_subreddit_rows(run_context.run_pk, source.pk)
    assert len(rows) == 1
    assert rows[0]["stop_reason"] is None


def test_the_wall_clock_ceiling_stops_the_subreddit_without_a_stop_reason(
    seeded: Any, add_source: Any, run_context: Any, notifier: Any, run_subreddit_rows: Any
) -> None:
    """The first of §19.4's five NULL sources. A ceiling already spent stops the sweep before
    a single page is fetched, so the terminal row records interrupted, not exhausted."""
    source = add_source("premiere")
    run_context.deadline_at = run_context.clock.now()  # the ceiling is gone

    result = sweep.sweep_subreddit(run_context, source, gateway=seeded, notifier=notifier)

    assert result.stop_reason is None
    assert result.pages == 0
    assert any(w.name == "wall_clock_ceiling" for w in run_context.warnings)
    rows = run_subreddit_rows(run_context.run_pk, source.pk)
    assert len(rows) == 1
    assert rows[0]["stop_reason"] is None


# --- KI-018 (external round one): an end of listing on the tenth page is the cap --------------


def _capped_listing_with_removed_slots(fake: Any, *, total: int, removed: range) -> None:
    """``total`` posts, newest first; the newest thousand are reachable and ``removed`` of those
    are moderator-removed, so Reddit's cap is consumed by slots the listing never shows."""
    fake.add_subreddit("premiere")
    for i in range(total):
        extra = {"removed_by_category": "moderator"} if i in removed else {}
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60, **extra)


def test_a_listing_ending_at_the_cap_with_filtered_slots_is_a_cap_stop_not_exhausted(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    _capped_listing_with_removed_slots(fake, total=1050, removed=range(500, 600))
    source = add_source("premiere", watermark_created_utc=BASE + 10 * 60)  # far behind

    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    after = subreddit_row(source.pk)
    assert result.stop_reason is StopReason.CAP
    assert result.items_seen < 1000 and result.pages == 10
    assert after.last_complete_poll_at is None  # coverage not proven over a truncated window
    assert after.gap_suspected_at is not None


def test_a_listing_ending_before_its_tenth_page_is_still_exhausted(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    """The control: nine pages cannot be the cap, so the end is a real end."""
    _capped_listing_with_removed_slots(fake, total=850, removed=range(300, 400))
    source = add_source("premiere", watermark_created_utc=BASE + 10 * 60)

    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert result.stop_reason is StopReason.EXHAUSTED and result.pages == 9
    assert subreddit_row(source.pk).last_complete_poll_at is not None
