"""SS-01, SS-03, SS-04, SS-05, SS-06: the per-subreddit status machine, auto-disable,
identity-abort-before-any-write, and the watermark/coverage/gap recovery split
(design-round5.md §6.3, §6.5, §6.9, §16).

Also carries the round-5-findings fixes that touch this step: finding 1 (P0, the stalled
cursor must never write ``stop_reason='exhausted'``) folded into the SS-01 parametrization,
and finding 4 (P1, a dry run must still warn about a per-source failure).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import select

from threaddigest.core.paging import StopReason
from threaddigest.db import repo
from threaddigest.db.schema import STOP_REASONS, SUBREDDIT_STATUSES, Base
from threaddigest.ports import (
    GatewayError,
    SubredditForbidden,
    SubredditNotFound,
    SubredditQuarantined,
    SubredditRedirected,
    TransientError,
)
from threaddigest.services import sweep

BASE = 1_757_700_000  # matches tests/conftest.py's ``seeded`` fixture


class _ProbingNotifier:
    """Records, for every ``notify()`` call, whether the source was ALREADY disabled in the
    database at that moment -- the round-4 P0-3 proof that the announcement follows the
    commit rather than racing it."""

    def __init__(self, engine: Any, subreddit_pk: int) -> None:
        self._engine = engine
        self._pk = subreddit_pk
        self.sent: list[tuple[str, str]] = []
        self.enabled_at_notify: list[bool] = []

    def notify(self, level: str, message: str) -> None:
        self.sent.append((level, message))
        subreddits = Base.metadata.tables["subreddits"]
        with self._engine.connect() as conn:
            enabled = conn.execute(
                select(subreddits.c.enabled).where(subreddits.c.pk == self._pk)
            ).scalar_one()
        self.enabled_at_notify.append(bool(enabled))


# --- SS-01: the status machine, and every outcome writes a terminal row ------------------------


def test_forbidden_marks_the_source_and_others_continue(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    fake.add_subreddit("editors")
    fake.set_status("editors", "forbidden")
    fake.add_subreddit("premiere")
    for i in range(5):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    add_source("editors")
    add_source("premiere")

    result = sweep.sweep_all(run_context, gateway=fake, notifier=notifier)

    assert result.terminal_status is None
    by_name = {s.name_lower: s for s in result.subreddits}
    assert by_name["editors"].status == "forbidden"
    assert by_name["editors"].error is not None
    assert by_name["editors"].disabled is False
    assert by_name["premiere"].status == "ok"
    assert any(w.name == "subreddit_error" for w in run_context.warnings)
    # `forbidden` alone does not notify (§8's table has no "notify" for this row -- unlike
    # `not_found`, `redirect`/`quarantined` at their disable threshold, or an identity
    # mismatch); the warning is the whole signal until/unless the source is disabled.
    assert notifier.sent == []


CASES = (
    "clean",
    "forbidden",
    "not_found",
    "redirect",
    "quarantined",
    "transient_giveup",
    "identity_mismatch",
    "cap",
    "stalled_cursor",
)


@pytest.mark.parametrize("case", CASES)
def test_every_sweep_outcome_writes_a_terminal_run_subreddit_row(
    case: str,
    fake: Any,
    add_source: Any,
    run_context: Any,
    notifier: Any,
    run_subreddit_rows: Any,
) -> None:
    """§6.3's closure: EVERY exit attempts the terminal row, and NULL occurs only on the
    interrupted path (``stalled_cursor``, since round5-findings.json finding 1 -- never on a
    per-source failure, which always writes ``stop_reason='error'``)."""
    fake.add_subreddit("premiere")
    expected_stop_reason: StopReason | None
    expect_error = False

    if case == "clean":
        for i in range(5):
            fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
        source = add_source("premiere")
        expected_stop_reason = StopReason.EXHAUSTED
    elif case in ("forbidden", "not_found", "redirect", "quarantined"):
        fake.set_status("premiere", case)
        source = add_source("premiere")
        expected_stop_reason = StopReason.ERROR
        expect_error = True
    elif case == "transient_giveup":
        fake.add_post("premiere", title="one", created_utc=BASE)
        fake.fail_page("premiere", 1, TransientError("boom"), times=None)
        source = add_source("premiere")
        expected_stop_reason = StopReason.ERROR
        expect_error = True
    elif case == "identity_mismatch":
        fake.add_subreddit("premiere", t5="t5_real")
        fake.add_post("premiere", title="one", created_utc=BASE)
        source = add_source("premiere", subreddit_id="t5_stored")
        expected_stop_reason = StopReason.ERROR
        expect_error = True
    elif case == "cap":
        for i in range(1005):
            fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
        source = add_source("premiere")
        expected_stop_reason = StopReason.CAP
    else:  # stalled_cursor
        for i in range(150):
            fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
        fake.set_overlap("premiere", n=100)
        source = add_source("premiere")
        expected_stop_reason = None

    sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    rows = run_subreddit_rows(run_context.run_pk, source.pk)
    assert len(rows) == 1
    expected = None if expected_stop_reason is None else expected_stop_reason.value
    assert rows[0]["stop_reason"] == expected
    assert (rows[0]["error"] is not None) == expect_error


# --- SS-03: redirect auto-disable, loud, and only after the commit -----------------------------


def test_redirect_auto_disables_after_three_runs_with_an_alert(
    fake: Any,
    add_source: Any,
    engine: Any,
    clock: Any,
    settings: Any,
    notifier: Any,
    subreddit_row: Any,
) -> None:
    from threaddigest.services import runs

    fake.add_subreddit("premiere")
    fake.set_status("premiere", "redirect")
    source = add_source("premiere")

    results = []
    for _ in range(sweep.REDIRECT_DISABLE_AFTER):
        ctx = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)
        results.append(sweep.sweep_subreddit(ctx, source, gateway=fake, notifier=notifier))
        source = subreddit_row(source.pk)

    assert [r.disabled for r in results] == [False] * (sweep.REDIRECT_DISABLE_AFTER - 1) + [True]
    assert source.enabled is False
    assert source.status == "redirect"
    assert any(level == "error" for level, _ in notifier.sent)
    assert any(w.name == "source_auto_disabled" for w in ctx.warnings)


def test_the_disable_warning_is_emitted_only_after_the_transaction_commits(
    fake: Any, add_source: Any, engine: Any, clock: Any, settings: Any, subreddit_row: Any
) -> None:
    from threaddigest.services import runs

    fake.add_subreddit("premiere")
    fake.set_status("premiere", "quarantined")  # QUARANTINE_DISABLE_AFTER=1: disables immediately
    source = add_source("premiere")
    probe = _ProbingNotifier(engine, source.pk)
    ctx = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)

    result = sweep.sweep_subreddit(ctx, source, gateway=fake, notifier=probe)

    assert result.disabled is True
    assert probe.sent  # the disable notification actually fired
    assert probe.enabled_at_notify  # and it observed the database at least once
    assert all(observed is False for observed in probe.enabled_at_notify)


# --- SS-04: quarantine disables on the first occurrence -----------------------------------------


def test_quarantined_is_disabled_with_an_alert(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    fake.add_subreddit("premiere")
    fake.set_status("premiere", "quarantined")
    source = add_source("premiere")

    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert result.status == "quarantined"
    assert result.disabled is True
    assert subreddit_row(source.pk).enabled is False
    assert any(level == "error" for level, _ in notifier.sent)
    assert any(w.name == "source_auto_disabled" for w in run_context.warnings)


# --- SS-05: identity, checked on name_lower, aborted before any write --------------------------


def test_casing_merges_to_one_row(fake: Any, engine: Any, run_context: Any, notifier: Any) -> None:
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    with engine.connect() as conn:
        workspace_pk = repo.default_workspace_pk(conn)
    with engine.begin() as conn:
        first = repo.seed_subreddits(conn, workspace_pk=workspace_pk, names=["Premiere"], now=BASE)
    with engine.begin() as conn:
        second = repo.seed_subreddits(conn, workspace_pk=workspace_pk, names=["PREMIERE"], now=BASE)
    assert (first, second) == (1, 0)  # the second spelling collapsed onto the same row

    with engine.connect() as conn:
        rows = repo.enabled_subreddits(conn, workspace_pk)
    assert len(rows) == 1

    result = sweep.sweep_subreddit(run_context, rows[0], gateway=fake, notifier=notifier)
    assert result.stop_reason is StopReason.EXHAUSTED


def test_t5_mismatch_aborts_the_subreddit_before_any_row_is_written(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, run_subreddit_rows: Any
) -> None:
    fake.add_subreddit("premiere", t5="t5_real")
    fake.add_post("premiere", title="one", created_utc=BASE)
    source = add_source("premiere", subreddit_id="t5_stored")

    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert result.status == "error"
    assert result.stop_reason is StopReason.ERROR
    posts = Base.metadata.tables["posts"]
    with run_context.engine.connect() as conn:
        count = conn.execute(select(posts.c.pk)).all()
    assert count == []  # ZERO rows written for this source
    rows = run_subreddit_rows(run_context.run_pk, source.pk)
    assert len(rows) == 1
    assert rows[0]["stop_reason"] == "error"
    assert any(level == "error" for level, _ in notifier.sent)


def test_a_null_stored_identity_is_adopted_in_the_terminal_transaction(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    fake.add_subreddit("premiere", t5="t5_known")
    fake.add_post("premiere", title="one", created_utc=BASE)
    source = add_source("premiere")
    assert source.subreddit_id is None

    sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert subreddit_row(source.pk).subreddit_id == "t5_known"


# --- SS-06: recovery, the watermark and the coverage split (§6.5) -------------------------------


def test_complete_sweep_clears_status_failures_last_error_and_gap(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, engine: Any, subreddit_row: Any
) -> None:
    fake.add_subreddit("premiere")
    for i in range(5):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    source = add_source("premiere", gap_suspected_at=BASE - 1000)
    with engine.begin() as conn:
        repo.record_subreddit_failure(
            conn, subreddit_pk=source.pk, status="error", error="boom", now=BASE, disable_at=None
        )
        repo.record_subreddit_failure(
            conn,
            subreddit_pk=source.pk,
            status="error",
            error="boom again",
            now=BASE,
            disable_at=None,
        )
    source = subreddit_row(source.pk)
    assert source.consecutive_failures == 2

    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert result.stop_reason is StopReason.EXHAUSTED
    after = subreddit_row(source.pk)
    assert after.status == "ok"
    assert after.consecutive_failures == 0
    assert after.gap_suspected_at is None
    subreddits = Base.metadata.tables["subreddits"]
    with engine.connect() as conn:
        last_error = conn.execute(
            select(subreddits.c.last_error).where(subreddits.c.pk == source.pk)
        ).scalar_one()
    assert last_error is None


def test_cap_stop_with_no_gap_advances_the_watermark_and_stamps_last_complete_poll_at(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    fake.add_subreddit("premiere")
    total = 1005
    for i in range(total):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    seen_min_index = total - 1000  # the cap keeps only the newest 1000
    prior_watermark = BASE + (seen_min_index + 5) * 60  # comfortably past `seen_min`
    source = add_source("premiere", watermark_created_utc=prior_watermark)

    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert result.stop_reason is StopReason.CAP
    after = subreddit_row(source.pk)
    assert after.watermark_created_utc == BASE + (total - 1) * 60  # advanced to the newest post
    assert after.last_complete_poll_at is not None
    assert after.gap_suspected_at is None
    assert not any(w.name == "gap_suspected" for w in run_context.warnings)


def test_cap_stop_with_a_gap_advances_the_watermark_but_not_last_complete_poll_at(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any
) -> None:
    fake.add_subreddit("premiere")
    total = 1050
    for i in range(total):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    source = add_source("premiere", watermark_created_utc=BASE + 40 * 60)  # far behind `seen_min`

    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert result.stop_reason is StopReason.CAP
    after = subreddit_row(source.pk)
    assert after.watermark_created_utc == BASE + (total - 1) * 60  # still advances
    assert after.last_complete_poll_at is None  # coverage NOT proven
    assert after.gap_suspected_at is not None


def test_exhausted_sweep_advances_the_watermark_forward_only(
    fake: Any,
    add_source: Any,
    run_context: Any,
    notifier: Any,
    engine: Any,
    clock: Any,
    settings: Any,
    subreddit_row: Any,
) -> None:
    from threaddigest.services import runs

    fake.add_subreddit("premiere")
    for i in range(5):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    source = add_source("premiere")
    sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)
    assert subreddit_row(source.pk).watermark_created_utc == BASE + 4 * 60

    # A later watermark is already on record (as an out-of-order write might leave it);
    # this sweep's own `seen_max` is OLDER, so the column must not regress.
    ahead = BASE + 100 * 60
    with engine.begin() as conn:
        repo.advance_watermark(conn, subreddit_pk=source.pk, seen_max_created_utc=ahead)
    assert subreddit_row(source.pk).watermark_created_utc == ahead

    ctx2 = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)
    result = sweep.sweep_subreddit(ctx2, subreddit_row(source.pk), gateway=fake, notifier=notifier)

    assert result.stop_reason is StopReason.EXHAUSTED
    assert subreddit_row(source.pk).watermark_created_utc == ahead  # never moved backward


def test_a_first_capped_sweep_does_not_claim_complete_coverage(
    fake: Any,
    add_source: Any,
    run_context: Any,
    notifier: Any,
    engine: Any,
    clock: Any,
    settings: Any,
    subreddit_row: Any,
) -> None:
    """round-5 P1-4: a first capped sweep (no prior watermark) proves nothing; a second capped
    sweep with a healthy, contiguous trickle DOES, once there is known territory to reach."""
    from threaddigest.services import runs

    fake.add_subreddit("premiere")
    first_total = 1005
    for i in range(first_total):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    source = add_source("premiere")
    assert source.watermark_created_utc is None

    result1 = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)
    assert result1.stop_reason is StopReason.CAP
    after1 = subreddit_row(source.pk)
    assert after1.last_complete_poll_at is None
    assert after1.watermark_created_utc is not None

    for i in range(5):
        fake.add_post("premiere", title=f"trickle {i}", created_utc=BASE + (first_total + i) * 60)
    ctx2 = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)
    result2 = sweep.sweep_subreddit(ctx2, after1, gateway=fake, notifier=notifier)

    assert result2.stop_reason is StopReason.CAP
    after2 = subreddit_row(source.pk)
    assert after2.last_complete_poll_at is not None  # NOW coverage is proven


# --- round-5-findings.json finding 4 (P1): a dry run still warns about a per-source failure ----


def test_a_dry_run_still_warns_about_a_forbidden_source(
    fake: Any, add_source: Any, engine: Any, clock: Any, settings: Any, notifier: Any
) -> None:
    from threaddigest.services import runs

    fake.add_subreddit("premiere")
    fake.set_status("premiere", "forbidden")
    source = add_source("premiere")
    ctx = runs.dry_context(engine, kind="run", trigger="cli", clock=clock, settings=settings)

    result = sweep.sweep_subreddit(ctx, source, gateway=fake, notifier=notifier)

    assert any(w.name == "subreddit_error" for w in ctx.warnings)
    assert notifier.sent == []  # a dry run must never notify (only the real thing does)
    assert result.status == source.status  # nothing was written; status unchanged
    with engine.connect() as conn:
        assert repo.table_counts(conn, ("run_subreddits",)) == {"run_subreddits": 0}


def test_a_dry_run_over_a_healthy_source_writes_nothing_and_reports_zero_new(
    fake: Any,
    add_source: Any,
    engine: Any,
    clock: Any,
    settings: Any,
    notifier: Any,
    snapshot_tables: Any,
) -> None:
    """§11.4: a dry run skips ``write_page`` and the terminal transaction, so the HTTP cost is
    real and every table is untouched. ``new_items`` is therefore structurally 0 whatever the
    listing holds, which is why the printed summary has to label it."""
    from threaddigest.services import runs

    fake.add_subreddit("premiere")
    for i in range(5):
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60)
    source = add_source("premiere")
    before = snapshot_tables(list(runs.TRACKED_TABLES))
    ctx = runs.dry_context(engine, kind="run", trigger="cli", clock=clock, settings=settings)

    result = sweep.sweep_subreddit(ctx, source, gateway=fake, notifier=notifier)

    assert result.stop_reason is StopReason.EXHAUSTED
    assert result.items_seen == 5  # the listing really was read
    assert result.new_items == 0  # ... and nothing was written, by construction
    assert fake.requests_made > 0
    assert snapshot_tables(list(runs.TRACKED_TABLES)) == before
    with engine.connect() as conn:
        assert repo.table_counts(conn, ("run_subreddits",)) == {"run_subreddits": 0}


# --- round5-findings.json finding 8 (P2): StopReason / SUBREDDIT_STATUSES pinned to their ------
# --- producers, so a `_classify_failure` typo is a red test rather than a silent T6 failure ----


def test_stop_reason_values_match_the_stored_check_constraint() -> None:
    assert {r.value for r in StopReason} == set(STOP_REASONS)


_DUMMY_SOURCE = repo.SubredditRow(
    pk=1,
    workspace_pk=1,
    name_lower="premiere",
    display_name="premiere",
    subreddit_id=None,
    enabled=True,
    status="ok",
    consecutive_failures=0,
    watermark_created_utc=None,
    last_complete_poll_at=None,
    gap_suspected_at=None,
)

_EVERY_MAPPED_EXCEPTION = (
    SubredditForbidden("403"),
    SubredditNotFound("404"),
    SubredditRedirected("/subreddits/search"),
    SubredditQuarantined("403"),
    TransientError("500 after the ladder gave up"),
    GatewayError("anything else"),
)


def test_classify_failure_statuses_are_all_valid_subreddit_statuses() -> None:
    """§8's exception -> status mapping can never emit a value the CHECK constraint would
    reject; a typo in ``_classify_failure`` must be a red test, not a T6 ``IntegrityError``
    a warning quietly swallows."""
    statuses = {
        sweep._classify_failure(exc, _DUMMY_SOURCE).status for exc in _EVERY_MAPPED_EXCEPTION
    }
    identity = sweep.SubredditIdentityError(name_lower="x", stored="t5_a", observed="t5_b")
    statuses.add(sweep._classify_failure(identity, _DUMMY_SOURCE).status)
    assert statuses <= set(SUBREDDIT_STATUSES)
