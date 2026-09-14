"""TE-01, TE-02, RL-07(a): the retry ladder, the 429 wait/abort rules, the preflight auth
ping, and what a locked write does to a page and to the terminal transaction
(design-round5.md §6.7, §6.8, §7 T5/T6, §16).

Also carries round5-findings.json finding 3 (P1: a heartbeat failure during a retry pause
must never be blamed on the source it happened to be retrying) and finding 4 (P1: the
design's own mechanism for the T6-lock test cannot be produced by the fake -- verified here
via the finding's own alternative, since T5 never touches ``subreddits``).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select
from sqlalchemy.exc import OperationalError, ProgrammingError

from insightminer.core.budget import Budget
from insightminer.core.paging import StopReason
from insightminer.core.retry import RunStatus, exit_code
from insightminer.db import repo
from insightminer.db.engine import engine_for
from insightminer.db.schema import Base
from insightminer.ports import (
    AuthFailed,
    GatewayError,
    HtmlBlocked,
    RateLimited,
    TransientError,
)
from insightminer.services import sweep
from insightminer.services.runs import RunTerminalError

BASE = 1_757_700_000  # matches tests/conftest.py's ``seeded`` fixture


# --- TE-01: the transient ladder ----------------------------------------------------------------


def test_transient_page_error_walks_the_30_120_300_ladder(
    fake: Any, add_source: Any, run_context: Any, clock: Any
) -> None:
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    fake.fail_page("premiere", 1, TransientError("500"), times=3)  # exactly the ladder's length
    source = add_source("premiere")

    outcome, exc = sweep._page_loop(run_context, source, gateway=fake)

    assert exc is None
    assert outcome.stop_reason is StopReason.EXHAUSTED
    assert clock.sleeps == [30.0, 120.0, 300.0]


def test_ladder_exhaustion_fails_only_that_subreddit(
    fake: Any, add_source: Any, run_context: Any, notifier: Any
) -> None:
    fake.add_subreddit("broken")
    fake.add_post("broken", title="one", created_utc=BASE)
    fake.fail_page("broken", 1, TransientError("500"), times=None)  # never recovers
    fake.add_subreddit("healthy")
    fake.add_post("healthy", title="one", created_utc=BASE)
    add_source("broken")
    add_source("healthy")

    result = sweep.sweep_all(run_context, gateway=fake, notifier=notifier)

    assert result.terminal_status is None
    by_name = {s.name_lower: s for s in result.subreddits}
    assert by_name["broken"].status == "error"
    assert by_name["broken"].stop_reason is StopReason.ERROR
    assert by_name["healthy"].status == "ok"
    assert by_name["healthy"].stop_reason is StopReason.EXHAUSTED


def test_a_subreddit_whose_pages_all_fail_still_spends_budget(
    fake: Any, add_source: Any, run_context: Any
) -> None:
    """``--budget 2`` against a subreddit whose every page 500s must stop on budget, not run
    the ladder forever (§6.6): the ladder is bounded by ``RetryPolicy`` regardless of budget,
    and every attempt it made really cost a request."""
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    fake.fail_page("premiere", 1, TransientError("500"), times=None)
    source = add_source("premiere")
    run_context.budget = Budget(limit=2, hard_cap=5000)

    outcome, exc = sweep._page_loop(run_context, source, gateway=fake)

    assert exc is not None
    assert outcome.stop_reason is None
    assert fake.requests_made == 4  # the ladder's 4 attempts, well past the budget's limit of 2
    assert run_context.budget.used == 4


# --- TE-02: 429s, auth, HTML 403 and the preflight -----------------------------------------------


def test_rate_limited_waits_then_retries_once(
    fake: Any, add_source: Any, run_context: Any, clock: Any
) -> None:
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    fake.rate_limit_next(retry_after=37.0, times=1)
    source = add_source("premiere")

    outcome, exc = sweep._page_loop(run_context, source, gateway=fake)

    assert exc is None
    assert outcome.stop_reason is StopReason.EXHAUSTED
    assert clock.sleeps == [37.0]


def test_second_rate_limit_ends_the_run_rate_limited(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, clock: Any
) -> None:
    """§6.8's one-retry rule: a second 429 on the SAME page means Reddit is not honouring the
    window, so the run ends ``rate_limited`` rather than burning the ceiling.

    The 429 is planted on the page rather than on "the next request of any kind", because the
    preflight ping (§6.7) is the first request of the run and would otherwise consume it --
    which proves §8's preflight row, not this one.
    """
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    fake.fail_page("premiere", 1, RateLimited(10.0), times=2)
    add_source("premiere")

    result = sweep.sweep_all(run_context, gateway=fake, notifier=notifier)

    assert result.terminal_status is RunStatus.RATE_LIMITED
    assert result.exit_code_override is None  # `core.retry.exit_code` supplies 4
    assert clock.sleeps == [10.0, 10.0]  # it really waited the first time, and once more


def test_wait_beyond_the_ceiling_ends_the_run(
    fake: Any, add_source: Any, run_context: Any, notifier: Any
) -> None:
    """A wait that does not fit the remaining wall-clock ceiling ends the run instead of
    sleeping into it. Planted on the page for the same reason as the test above."""
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    fake.fail_page("premiere", 1, RateLimited(300.0), times=1)
    add_source("premiere")
    run_context.deadline_at = run_context.clock.now() + 5  # far less than the 300s wait

    result = sweep.sweep_all(run_context, gateway=fake, notifier=notifier)

    assert result.terminal_status is RunStatus.RATE_LIMITED
    assert run_context.clock.sleeps == []  # never actually waited into the ceiling


def test_auth_failed_aborts_the_run_with_78(
    fake: Any, add_source: Any, run_context: Any, notifier: Any
) -> None:
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    fake.set_auth_failed(times=None)
    add_source("premiere")

    result = sweep.sweep_all(run_context, gateway=fake, notifier=notifier)

    assert result.terminal_status is RunStatus.FAILED
    assert result.exit_code_override == 78


def test_html_403_aborts_the_run_not_the_subreddit(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    fake.set_html_403(times=1)
    source = add_source("premiere")

    result = sweep.sweep_all(run_context, gateway=fake, notifier=notifier)

    assert result.terminal_status is RunStatus.FAILED
    assert result.exit_code_override is None  # exit 1, not the auth override
    assert subreddit_row(source.pk).status == "ok"  # the abort is run-level, not the source's


def test_preflight_swallows_a_per_source_403(fake: Any, add_source: Any, run_context: Any) -> None:
    fake.add_subreddit("premiere")
    fake.set_status("premiere", "forbidden")
    source = add_source("premiere")

    sweep.preflight(run_context, gateway=fake, source=source)  # must not raise

    assert run_context.warnings == []  # nothing to record: the sweep proper reports it


def test_preflight_transient_takes_one_attempt_and_warns(
    fake: Any, add_source: Any, run_context: Any, clock: Any
) -> None:
    fake.add_subreddit("premiere")
    fake.fail_next(TransientError("500"), times=None)
    source = add_source("premiere")

    sweep.preflight(run_context, gateway=fake, source=source)

    assert clock.sleeps == []  # no ladder here: one attempt only
    assert any(w.name == "preflight_transient" for w in run_context.warnings)


# --- RL-07(a): a locked write, and a locked terminal transaction -------------------------------


def test_db_locked_write_fails_the_page_with_nothing_committed(
    fake: Any,
    add_source: Any,
    engine: Any,
    db_path: Any,
    clock: Any,
    settings: Any,
    snapshot_tables: Any,
) -> None:
    from insightminer.services import runs

    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    source = add_source("premiere")
    before = snapshot_tables(list(runs.TRACKED_TABLES))

    writer = engine_for(db_path, busy_timeout_ms=300)
    try:
        ctx = runs.start_run(writer, kind="run", trigger="cli", clock=clock, settings=settings)
        page = next(iter(fake.iter_new_pages("premiere", max_pages=1)))
        prepared = sweep._prepare_page(page, source_name="premiere")
        progress = repo.SweepProgress(
            pages=1, items_seen=0, new_items=0, updated_items=0, stop_reason=None, error=None
        )
        # The holder speaks to the driver in AUTOCOMMIT because ``engine_for`` emits its own
        # ``BEGIN`` from the ``begin`` event, and ``BEGIN IMMEDIATE`` inside that is "cannot
        # start a transaction within a transaction" (the DB-14 pattern,
        # tests/db/test_repo_busy_timeout.py).
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock_conn:
            lock_conn.exec_driver_sql("BEGIN IMMEDIATE")
            with pytest.raises(OperationalError, match="database is locked"):
                sweep.write_page(ctx, source, prepared, progress_before=progress)
            lock_conn.exec_driver_sql("ROLLBACK")
    finally:
        writer.dispose()

    assert snapshot_tables(list(runs.TRACKED_TABLES)) == before  # nothing committed


def test_counters_equal_table_deltas_after_a_db_locked_page(
    fake: Any,
    add_source: Any,
    engine: Any,
    db_path: Any,
    clock: Any,
    settings: Any,
    snapshot_tables: Any,
) -> None:
    from insightminer.services import runs

    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    source = add_source("premiere")
    before = snapshot_tables(list(runs.TRACKED_TABLES))

    writer = engine_for(db_path, busy_timeout_ms=300)
    try:
        ctx = runs.start_run(writer, kind="run", trigger="cli", clock=clock, settings=settings)
        # The lock is taken from inside the gateway, at the START of page 1, so it is held
        # across T5 only: the loop's own heartbeat (§6.2 note 8) sits OUTSIDE the per-source
        # handler, so a lock held before it would end the run rather than fail the page --
        # which is the shape round5-findings.json's `P1-heartbeat-inside-per-source-try`
        # exists to keep.
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as lock_conn:
            fake.on_call("page", 1, lambda: lock_conn.exec_driver_sql("BEGIN IMMEDIATE"))
            outcome, exc = sweep._page_loop(ctx, source, gateway=fake)
            lock_conn.exec_driver_sql("ROLLBACK")
    finally:
        writer.dispose()

    assert outcome.pages_fetched == 1  # the page was fetched; only its write was refused
    assert exc is not None
    assert isinstance(exc, OperationalError)
    after = snapshot_tables(list(runs.TRACKED_TABLES))
    assert after == before  # nothing committed, so every delta is zero
    assert ctx.counters.posts_new == (after["posts"] - before["posts"])
    assert ctx.counters.rejects == (after["raw_rejects"] - before["raw_rejects"])


def test_a_locked_terminal_transaction_warns_and_leaves_the_run_partial(
    fake: Any,
    add_source: Any,
    run_context: Any,
    notifier: Any,
    engine: Any,
    run_subreddit_rows: Any,
    subreddit_row: Any,
) -> None:
    """round5-findings.json ``P1-t6-test-mechanism``. The design's own mechanism -- holding a
    write lock across T6 only -- cannot be produced against this fake: every hook fires when a
    gateway *operation* begins, and between the last page's commit and T6 there is no gateway
    call, so a lock taken at the last page is held across T5 too and the test would pass by
    proving the pre-existing RL-07(a) behaviour instead of the new handler.

    This uses the finding's named alternative: T5 never touches ``subreddits``, so renaming
    that table away lets every page commit and fails T6, and only T6. What the handler owns is
    what is asserted -- the source's status, failure streak and ``last_error`` untouched,
    exactly one ``run_subreddits`` row still reading interrupted, exactly one
    ``subreddit_finish_failed`` warning and no announcement of a failure or a disable, the run
    ``partial``/exit 3, and the next source still swept.
    """
    from insightminer.services import runs

    fake.add_subreddit("first")
    fake.add_post("first", title="one", created_utc=BASE)
    fake.add_subreddit("second")
    fake.add_post("second", title="one", created_utc=BASE)
    source_a = add_source("first")
    source_b = add_source("second")

    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE subreddits RENAME TO subreddits_hidden")
    result_a = sweep.sweep_subreddit(run_context, source_a, gateway=fake, notifier=notifier)
    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE subreddits_hidden RENAME TO subreddits")

    assert result_a.status == source_a.status  # unchanged: T6 never committed
    after_a = subreddit_row(source_a.pk)
    assert after_a.status == source_a.status
    assert after_a.consecutive_failures == source_a.consecutive_failures
    subreddits = Base.metadata.tables["subreddits"]
    with engine.connect() as conn:
        last_error = conn.execute(
            select(subreddits.c.last_error).where(subreddits.c.pk == source_a.pk)
        ).scalar_one()
    assert last_error is None
    assert [w.name for w in run_context.warnings].count("subreddit_finish_failed") == 1
    assert not any(
        w.name in ("subreddit_error", "source_auto_disabled") for w in run_context.warnings
    )
    assert notifier.sent == []  # the announcements follow the commit, and there was none
    rows_a = run_subreddit_rows(run_context.run_pk, source_a.pk)
    assert len(rows_a) == 1
    assert rows_a[0]["stop_reason"] is None  # the per-page progress row stands, interrupted
    status = runs.resolve_status(None, (), run_context.warnings)
    assert status is RunStatus.PARTIAL
    assert exit_code(status) == 3  # the run is amber, never `failed` on lock contention

    result_b = sweep.sweep_subreddit(run_context, source_b, gateway=fake, notifier=notifier)

    assert result_b.stop_reason is StopReason.EXHAUSTED  # the next source is still swept
    rows_b = run_subreddit_rows(run_context.run_pk, source_b.pk)
    assert len(rows_b) == 1
    assert rows_b[0]["stop_reason"] == "exhausted"


# --- round5-findings.json finding 3 (P1): a heartbeat failure is never the source's fault -------


def test_a_failing_heartbeat_during_a_retry_ends_the_run_and_does_not_blame_the_source(
    fake: Any, add_source: Any, engine: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    """§6.2 note 8 / §7: every heartbeat call site must be outside the per-source handler --
    including the ladder's ``retry:...`` beat inside ``fetch_page``, not only the one at the
    top of ``_page_loop``'s iteration. Renaming ``runs`` away exactly when the ladder needs to
    write that beat must propagate out of ``sweep_all`` untouched, never converted into a
    per-source failure."""
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    fake.fail_page("premiere", 1, TransientError("500"), times=1)

    def _hide_runs() -> None:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE runs RENAME TO runs_hidden")

    fake.on_call("page", 1, _hide_runs)
    source = add_source("premiere")

    try:
        with pytest.raises(OperationalError):
            sweep.sweep_all(run_context, gateway=fake, notifier=notifier)
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE runs_hidden RENAME TO runs")

    after = subreddit_row(source.pk)
    assert after.status == "ok"
    assert after.consecutive_failures == 0


class _ConnectionRefusedGatewayError(GatewayError):
    """A gateway error ``core.retry.classify`` reads as an outage by name (its rule 3).

    The catch-all ``except GatewayError`` in §6.7 has to tell an outage from anything else,
    and every *named* ``ports`` class reaches an earlier clause, so the branch needs a class
    that is neither ``TransientError`` nor one of the per-source 4xx types.
    """


def test_a_page_html_403_aborts_the_run_not_the_subreddit(
    fake: Any, add_source: Any, run_context: Any
) -> None:
    """§6.8: ``HtmlBlocked`` is converted inside ``fetch_page``, so ``_page_loop``'s
    ``except GatewayError`` can never swallow a run-level abort (§6.2 note 7)."""
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    fake.fail_page("premiere", 1, HtmlBlocked("cloudflare"), times=1)
    source = add_source("premiere")

    with pytest.raises(RunTerminalError) as caught:
        sweep._page_loop(run_context, source, gateway=fake)

    assert caught.value.status is RunStatus.FAILED
    assert caught.value.exit_code is None  # exit 1, not the auth override


def test_a_mid_run_auth_failure_aborts_the_run_with_78(
    fake: Any, add_source: Any, run_context: Any
) -> None:
    """§9's one override: the run row already exists, so the status is ``failed`` and only the
    process exit code is 78."""
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    fake.fail_page("premiere", 1, AuthFailed("401"), times=1)
    source = add_source("premiere")

    with pytest.raises(RunTerminalError) as caught:
        sweep._page_loop(run_context, source, gateway=fake)

    assert caught.value.status is RunStatus.FAILED
    assert caught.value.exit_code == 78


def test_a_network_outage_walks_the_ladder_then_ends_the_run_network(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, clock: Any
) -> None:
    """§8: an outage is not the source's fault. The ladder still runs -- an outage can end
    within 30 s -- and only when it is exhausted does the run end ``network`` (exit 5),
    leaving the subreddit's status untouched."""
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    fake.fail_page(
        "premiere", 1, TransientError("connection refused", ConnectionRefusedError()), times=None
    )
    add_source("premiere")

    result = sweep.sweep_all(run_context, gateway=fake, notifier=notifier)

    assert result.terminal_status is RunStatus.NETWORK
    assert result.exit_code_override is None  # `core.retry.exit_code` supplies 5
    assert clock.sleeps == [30.0, 120.0, 300.0]


def test_preflight_rate_limit_ends_the_run(fake: Any, add_source: Any, run_context: Any) -> None:
    """§8's preflight 429 row: no wait and no ladder at the ping; the run ends ``rate_limited``
    before a single page is fetched."""
    fake.add_subreddit("premiere")
    fake.rate_limit_next(retry_after=5.0, times=1)
    source = add_source("premiere")

    with pytest.raises(RunTerminalError) as caught:
        sweep.preflight(run_context, gateway=fake, source=source)

    assert caught.value.status is RunStatus.RATE_LIMITED
    assert run_context.clock.sleeps == []


def test_preflight_network_outage_ends_the_run(
    fake: Any, add_source: Any, run_context: Any
) -> None:
    fake.add_subreddit("premiere")
    fake.fail_next(_ConnectionRefusedGatewayError("no route to reddit"), times=1)
    source = add_source("premiere")

    with pytest.raises(RunTerminalError) as caught:
        sweep.preflight(run_context, gateway=fake, source=source)

    assert caught.value.status is RunStatus.NETWORK


def test_preflight_records_any_other_gateway_error_and_continues(
    fake: Any, add_source: Any, run_context: Any
) -> None:
    """Nothing is swallowed silently: the ping returns, but the run can no longer be ``ok``."""
    fake.add_subreddit("premiere")
    fake.fail_next(GatewayError("unrecognised gateway failure"), times=1)
    source = add_source("premiere")

    sweep.preflight(run_context, gateway=fake, source=source)  # must not raise

    assert any(w.name == "preflight_error" for w in run_context.warnings)


def test_an_unreadable_source_list_fails_the_run_before_anything_is_swept(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, engine: Any
) -> None:
    """§6.8: a ``DatabaseError`` reading the source list is a run-level failure with a message
    rather than a traceback, and the gateway is never touched."""
    fake.add_subreddit("premiere")
    add_source("premiere")

    with engine.begin() as conn:
        conn.exec_driver_sql("ALTER TABLE subreddits RENAME TO subreddits_hidden")
    try:
        result = sweep.sweep_all(run_context, gateway=fake, notifier=notifier)
    finally:
        with engine.begin() as conn:
            conn.exec_driver_sql("ALTER TABLE subreddits_hidden RENAME TO subreddits")

    assert result.terminal_status is RunStatus.FAILED
    assert result.terminal_error is not None
    assert result.terminal_error.startswith("database: ")
    assert result.subreddits == ()
    assert fake.requests_made == 0  # not even the preflight ping


def test_a_run_with_no_enabled_sources_skips_the_preflight_entirely(
    fake: Any, run_context: Any, notifier: Any
) -> None:
    """§6.7: the auth ping is one call on the FIRST enabled source, and is skipped when there
    is none -- a workspace with nothing to sweep must make zero requests."""
    result = sweep.sweep_all(run_context, gateway=fake, notifier=notifier)

    assert result.subreddits == ()
    assert result.terminal_status is None
    assert fake.requests_made == 0


def test_a_spent_budget_stops_the_run_before_the_next_source(
    fake: Any, add_source: Any, run_context: Any, notifier: Any
) -> None:
    """The run-level boundary in ``sweep_all``: a budget with nothing left stops the loop with
    a warning instead of opening a sweep it cannot pay for."""
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    add_source("premiere")
    run_context.budget = Budget(limit=0, hard_cap=5000)

    result = sweep.sweep_all(run_context, gateway=fake, notifier=notifier)

    assert result.subreddits == ()
    assert result.terminal_status is None
    assert any(w.name == "run_budget_or_ceiling" for w in run_context.warnings)


def test_a_database_error_that_is_not_lock_contention_ends_the_run_failed(
    fake: Any, add_source: Any, run_context: Any, notifier: Any
) -> None:
    """§6.8's clause order, with a positive control.

    ``OperationalError`` and ``IntegrityError`` are handled where they can legitimately arise
    and are **re-raised** here, so the ``except DatabaseError`` clause means corruption or
    disk I/O only -- and it must report that as a run-level ``failed`` rather than as any
    source's fault. Corruption cannot be provoked against a healthy temp database, so the
    class is planted from the gateway's ``on_call`` hook, which fires inside ``fetch_page``:
    exactly the position an escaping database error would arrive from. Reversing the two
    clauses, or widening the narrowed one, is what this test exists to catch.
    """
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    add_source("premiere")
    corrupt = ProgrammingError("SELECT 1", None, RuntimeError("disk image is malformed"))

    def _corrupt() -> None:
        raise corrupt

    fake.on_call("page", 1, _corrupt)

    result = sweep.sweep_all(run_context, gateway=fake, notifier=notifier)

    assert result.terminal_status is RunStatus.FAILED
    assert result.terminal_error is not None
    assert result.terminal_error.startswith("database: ")
    assert result.subreddits == ()
    assert result.exit_code_override is None  # exit 1
