"""The invariant contract and the M1a invariant list, at the unit grain
(design-round5.md §14, §16 test-map rows DB-50/DB-51/NM-03a, FR-01, DB-54, DB-26, DB-48,
GT-01/G30 unit halves).

Every test here calls an invariant (or ``check_all``) directly against a hand-built
database, to pin its detail strings and boundary arithmetic. The *positive controls* that
prove each invariant actually flips ``runs.status`` through a real ``run`` invocation live
in ``tests/gates/test_invariants_planted.py`` and land in step 7 -- this file is the S
half the test map promises, not the gate.

Posts are inserted through plain SQLAlchemy Core (``insert(Base.metadata.tables["posts"])``),
never through ``text()`` (§2.3): this package is not on the ``TID251`` ignore list.
"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Connection, Engine, delete, insert, select
from sqlalchemy.schema import DropTable

from threaddigest.core.models import NORMALIZER_VERSION
from threaddigest.core.retry import ExitCode, RunStatus, exit_code
from threaddigest.db import repo
from threaddigest.db.schema import RUN_STATUSES, Base
from threaddigest.services import collect, invariants, runs
from threaddigest.settings import Settings

# --- small local builders (§2.3: Core only, no text()) -----------------------------------


def _insert_bare_post(
    engine: Engine,
    *,
    reddit_id: str,
    subreddit_pk: int,
    created_utc: int,
    first_seen_at: int,
    last_fetched_at: int,
    normalizer_version: int = NORMALIZER_VERSION,
    post_hint: str | None = None,
    permalink: str | None = "/r/premiere/comments/x/",
    author_state: str = "known",
    content_state: str = "live",
) -> tuple[int, str, str, str]:
    """Insert one minimal ``posts`` row through Core; returns ``(pk, title, selftext,
    author)`` for callers that need the row's exact values back (the FTS planter, §14.3)."""
    posts = Base.metadata.tables["posts"]
    title = f"title {reddit_id}"
    selftext = f"body {reddit_id}"
    author = "someone"
    values = {
        "reddit_id": reddit_id,
        "fullname": f"t3_{reddit_id}",
        "subreddit_pk": subreddit_pk,
        "author": author,
        "author_fullname": "t2_someone",
        "author_state": author_state,
        "title": title,
        "selftext": selftext,
        "url": f"https://www.reddit.com/r/premiere/comments/{reddit_id}/",
        "permalink": permalink,
        "created_utc": created_utc,
        "first_seen_at": first_seen_at,
        "last_fetched_at": last_fetched_at,
        "next_check_at": last_fetched_at + 86_400,
        "source": "subreddit_new",
        "normalizer_version": normalizer_version,
        "raw_json": "{}",
        "content_state": content_state,
        "post_hint": post_hint,
    }
    with engine.begin() as conn:
        result = conn.execute(insert(posts).values(**values))
        pk = int(result.inserted_primary_key[0])
    return pk, title, selftext, author


def _inv_ctx(
    conn: Connection,
    ctx: runs.RunContext,
    *,
    terminal_status: RunStatus | None = None,
    normalizer_version: int = NORMALIZER_VERSION,
) -> invariants.InvariantContext:
    return invariants.InvariantContext(
        conn=conn,
        run_pk=ctx.run_pk,
        run_started_at=ctx.started_at,
        now=ctx.clock.now(),
        counters=ctx.counters,
        baseline_counts=ctx.baseline_counts,
        normalizer_version=normalizer_version,
        settings=ctx.settings,
        terminal_status=terminal_status,
    )


# --- the contract: Severity, INVARIANTS, Violation, to_json, render, check_all -----------


def test_severity_values_match_runs_severity_carrier_vocabulary() -> None:
    """``services.runs`` never imports this module (§12.5); it spells the vocabulary as
    plain strings instead. This pins the two halves to the same values."""
    assert invariants.Severity.WARNING == runs.SEVERITY_WARNING
    assert invariants.Severity.FAILURE == runs.SEVERITY_FAILURE
    assert invariants.Severity.WARNING.value == "warning"
    assert invariants.Severity.FAILURE.value == "failure"


def test_invariants_tuple_matches_the_spec_order() -> None:
    assert [fn.__name__ for fn in invariants.INVARIANTS] == [
        "counters_equal_table_deltas",
        "no_other_running_rows",
        "fts_membership_equals_live",
        "rows_carry_current_normalizer_version",
        "unknown_enum_values_are_counted",
        "population_floors_hold",
        "per_source_freshness",
    ]


def test_freshness_statuses_is_every_terminal_status_except_queued_running_skipped_locked() -> None:
    assert invariants.FRESHNESS_STATUSES == set(RUN_STATUSES) - {
        "queued",
        "running",
        "skipped_locked",
    }


def test_violation_as_dict_has_exactly_invariant_severity_and_detail() -> None:
    violation = invariants.Violation(
        invariant="x", severity=invariants.Severity.WARNING, detail="d"
    )
    assert violation.as_dict() == {"invariant": "x", "severity": "warning", "detail": "d"}


def test_to_json_of_no_violations_is_the_literal_empty_array() -> None:
    assert invariants.to_json(()) == "[]"


def test_to_json_round_trips_through_json_loads() -> None:
    violation = invariants.Violation(
        invariant="x", severity=invariants.Severity.FAILURE, detail="d"
    )
    payload = invariants.to_json((violation,))
    assert json.loads(payload) == [{"invariant": "x", "severity": "failure", "detail": "d"}]


def test_render_names_every_violation_in_one_line() -> None:
    violations = (
        invariants.Violation(invariant="a", severity=invariants.Severity.FAILURE, detail="one"),
        invariants.Violation(invariant="b", severity=invariants.Severity.WARNING, detail="two"),
    )
    assert invariants.render(violations) == "2 invariant violations: a: one; b: two"


def test_check_all_returns_violations_in_invariants_order(
    run_context: runs.RunContext, add_source: Any, plant_run: Any, engine: Engine, now: int
) -> None:
    """Three of the seven invariants fire; the list must read in ``INVARIANTS`` order, not
    insertion order -- ``fts_membership_equals_live`` (index 2) stays clean and must not
    appear between the two that do."""
    source = add_source("premiere")
    _insert_bare_post(
        engine,
        reddit_id="p1",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
        normalizer_version=0,
    )
    plant_run(status="running", pid=999_999, heartbeat_at=now)
    with engine.connect() as conn:
        violations = invariants.check_all(_inv_ctx(conn, run_context))
    assert [v.invariant for v in violations] == [
        "counters_equal_table_deltas",
        "no_other_running_rows",
        "rows_carry_current_normalizer_version",
    ]


def test_check_all_catches_a_raising_invariant_as_a_failure_violation_naming_it(
    run_context: runs.RunContext, engine: Engine
) -> None:
    """Dropping a tracked table (§14.3's crashing-invariant control) makes
    ``counters_equal_table_deltas`` raise a real ``OperationalError``; ``check_all`` must
    catch it per-invariant and name it, never let it escape or crash the whole pass."""
    with engine.begin() as conn:
        conn.execute(DropTable(Base.metadata.tables["post_themes"]))
    with engine.connect() as conn:
        violations = invariants.check_all(_inv_ctx(conn, run_context))
    assert len(violations) == 1
    violation = violations[0]
    assert violation.invariant == "counters_equal_table_deltas"
    assert violation.severity == invariants.Severity.FAILURE
    assert "invariant crashed" in violation.detail
    assert "OperationalError" in violation.detail


# --- counters_equal_table_deltas (DB-54, unit half) ---------------------------------------


def test_counters_equal_table_deltas_passes_on_a_clean_run(
    run_context: runs.RunContext, engine: Engine
) -> None:
    with engine.connect() as conn:
        assert invariants.counters_equal_table_deltas(_inv_ctx(conn, run_context)) is None


def test_counters_equal_table_deltas_flags_a_table_whose_delta_disagrees_with_its_counter(
    run_context: runs.RunContext, add_source: Any, engine: Engine, now: int
) -> None:
    source = add_source("premiere")
    _insert_bare_post(
        engine,
        reddit_id="p1",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
    )
    # ``run_context.counters.posts_new`` stays 0: the row was written outside the counted
    # path, exactly the shape the planted DB-54 control uses (§13.2).
    with engine.connect() as conn:
        violation = invariants.counters_equal_table_deltas(_inv_ctx(conn, run_context))
    assert violation is not None
    assert violation.severity == invariants.Severity.FAILURE
    assert "posts" in violation.detail
    assert "posts_new" in violation.detail


def test_counters_equal_table_deltas_flags_a_decrease_in_an_untracked_table(
    engine: Engine, clock: Any, settings: Any, now: int
) -> None:
    """Only ``posts``/``comments``/``raw_rejects`` have a counter to match; every other
    tracked table (here ``authors``) must merely not *decrease* (§13.2 step 4)."""
    with engine.begin() as conn:
        repo.upsert_authors(
            conn, [repo.AuthorWrite(author_fullname="t2_seed", name="seed", seen_at=now)]
        )
    ctx = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)
    authors = Base.metadata.tables["authors"]
    with engine.begin() as conn:
        conn.execute(delete(authors).where(authors.c.author_fullname == "t2_seed"))
    with engine.connect() as conn:
        violation = invariants.counters_equal_table_deltas(_inv_ctx(conn, ctx))
    assert violation is not None
    assert violation.severity == invariants.Severity.FAILURE
    assert "authors" in violation.detail


# --- no_other_running_rows -----------------------------------------------------------------


def test_no_other_running_rows_passes_when_alone(
    run_context: runs.RunContext, engine: Engine
) -> None:
    with engine.connect() as conn:
        assert invariants.no_other_running_rows(_inv_ctx(conn, run_context)) is None


def test_no_other_running_rows_flags_a_concurrent_running_row(
    run_context: runs.RunContext, plant_run: Any, engine: Engine, now: int
) -> None:
    plant_run(status="running", pid=999_999, heartbeat_at=now)
    with engine.connect() as conn:
        violation = invariants.no_other_running_rows(_inv_ctx(conn, run_context))
    assert violation is not None
    assert violation.severity == invariants.Severity.FAILURE


# --- fts_membership_equals_live (DB-26, unit half) ----------------------------------------


def test_fts_membership_equals_live_passes_when_the_index_matches_live_rows(
    run_context: runs.RunContext, add_source: Any, engine: Engine, now: int
) -> None:
    source = add_source("premiere")
    _insert_bare_post(
        engine,
        reddit_id="p1",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
    )
    with engine.connect() as conn:
        assert invariants.fts_membership_equals_live(_inv_ctx(conn, run_context)) is None


def test_fts_membership_equals_live_flags_a_membership_mismatch(
    run_context: runs.RunContext, add_source: Any, engine: Engine, now: int
) -> None:
    """The DB-26 plant, rebuilt per round-4 P1-5 (§14.3): a bare FTS ``'delete'`` command
    for a live row, passed that row's exact ``title``/``selftext``/``author`` so the index
    is merely wrong rather than corrupted."""
    source = add_source("premiere")
    pk, title, selftext, author = _insert_bare_post(
        engine,
        reddit_id="p1",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
    )
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "INSERT INTO posts_fts(posts_fts, rowid, title, selftext, author) "
            "VALUES ('delete', ?, ?, ?, ?)",
            (pk, title, selftext, author),
        )
    with engine.connect() as conn:
        violation = invariants.fts_membership_equals_live(_inv_ctx(conn, run_context))
    assert violation is not None
    assert violation.severity == invariants.Severity.FAILURE
    assert "posts" in violation.detail


def test_fts_membership_equals_live_flags_an_equal_count_substitution(
    run_context: runs.RunContext, add_source: Any, engine: Engine, now: int
) -> None:
    """KI-022 (external round one): swap one live row's index entry for a phantom, keeping the
    count constant. The membership count still matches, so only the content check
    (``integrity-check`` at ``rank = 1``) catches it. Search would return the phantom, not the
    post, while the old count-only invariant reported nothing."""
    source = add_source("premiere")
    pk, title, selftext, author = _insert_bare_post(
        engine,
        reddit_id="p1",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
    )
    with engine.begin() as conn:
        # Remove the real entry with its exact values, then add a phantom: count unchanged.
        conn.exec_driver_sql(
            "INSERT INTO posts_fts(posts_fts, rowid, title, selftext, author) "
            "VALUES ('delete', ?, ?, ?, ?)",
            (pk, title, selftext, author),
        )
        conn.exec_driver_sql(
            "INSERT INTO posts_fts(rowid, title, selftext, author) "
            "VALUES (?, 'phantomcanary', 'wrongbody', 'wrongauthor')",
            (pk + 9000,),
        )
    with engine.connect() as conn:
        # The count-only half is satisfied; the content check must still object.
        from threaddigest.db import fts as _fts

        assert _fts.fts_membership_count(conn, "posts_fts") == 1
        violation = invariants.fts_membership_equals_live(_inv_ctx(conn, run_context))
        phantom = list(
            conn.exec_driver_sql(
                "SELECT rowid FROM posts_fts WHERE posts_fts MATCH 'phantomcanary'"
            ).scalars()
        )
    assert violation is not None
    assert violation.severity == invariants.Severity.FAILURE
    assert "does not match its content rows" in violation.detail
    assert phantom == [pk + 9000]  # the substitution was real: search finds the phantom


# --- rows_carry_current_normalizer_version (DB-48, unit half) ----------------------------


def test_rows_carry_current_normalizer_version_passes_when_all_rows_are_current(
    run_context: runs.RunContext, add_source: Any, engine: Engine, now: int
) -> None:
    source = add_source("premiere")
    _insert_bare_post(
        engine,
        reddit_id="p1",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
    )
    with engine.connect() as conn:
        assert invariants.rows_carry_current_normalizer_version(_inv_ctx(conn, run_context)) is None


def test_rows_carry_current_normalizer_version_flags_a_stale_row_written_this_run(
    run_context: runs.RunContext, add_source: Any, engine: Engine, now: int
) -> None:
    source = add_source("premiere")
    _insert_bare_post(
        engine,
        reddit_id="p1",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
        normalizer_version=0,
    )
    with engine.connect() as conn:
        violation = invariants.rows_carry_current_normalizer_version(_inv_ctx(conn, run_context))
    assert violation is not None
    assert violation.severity == invariants.Severity.WARNING
    assert "posts" in violation.detail


# --- unknown_enum_values_are_counted -------------------------------------------------------


def test_unknown_enum_values_are_counted_passes_when_the_db_and_the_counter_agree(
    run_context: runs.RunContext, add_source: Any, engine: Engine, now: int
) -> None:
    source = add_source("premiere")
    _insert_bare_post(
        engine,
        reddit_id="p1",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
        post_hint="hologram",
    )
    run_context.counters.unknown_enum_values = 1
    with engine.connect() as conn:
        assert invariants.unknown_enum_values_are_counted(_inv_ctx(conn, run_context)) is None


def test_unknown_enum_values_are_counted_flags_a_value_the_counter_never_saw(
    run_context: runs.RunContext, add_source: Any, engine: Engine, now: int
) -> None:
    source = add_source("premiere")
    _insert_bare_post(
        engine,
        reddit_id="p1",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
        post_hint="hologram",
    )
    # ``run_context.counters.unknown_enum_values`` stays 0: a writer other than the sweep.
    with engine.connect() as conn:
        violation = invariants.unknown_enum_values_are_counted(_inv_ctx(conn, run_context))
    assert violation is not None
    assert violation.severity == invariants.Severity.WARNING
    assert "hologram" in violation.detail


# --- population_floors_hold (DB-50 / DB-51 / NM-03a, S half) -----------------------------


def test_empty_population_with_writes_is_a_violation(
    run_context: runs.RunContext, add_source: Any, engine: Engine, now: int
) -> None:
    """DB-51: the qualifying population (live, ``author_state='known'``) is empty, but
    ``counters`` says posts were written this run -- a floor over zero rows is inert, so
    this must fire rather than pass by vacuous truth."""
    source = add_source("premiere")
    _insert_bare_post(
        engine,
        reddit_id="p1",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
        author_state="account_deleted",
        permalink=None,
    )
    run_context.counters.posts_new = 1
    with engine.connect() as conn:
        violation = invariants.population_floors_hold(_inv_ctx(conn, run_context))
    assert violation is not None
    assert violation.invariant == "population_floors_hold"
    assert violation.severity == invariants.Severity.WARNING


def test_floor_is_scoped_by_normalizer_version(
    run_context: runs.RunContext, add_source: Any, engine: Engine, now: int
) -> None:
    """DB-50: a NULL in a floored column on a row written by an older normalizer must not
    fire -- the qualifying population is scoped to ``ctx.normalizer_version`` -- but the
    identical NULL on a current-version row must."""
    source = add_source("premiere")
    _insert_bare_post(
        engine,
        reddit_id="old",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
        normalizer_version=0,
        permalink=None,
    )
    with engine.connect() as conn:
        assert invariants.population_floors_hold(_inv_ctx(conn, run_context)) is None

    _insert_bare_post(
        engine,
        reddit_id="new",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
        normalizer_version=NORMALIZER_VERSION,
        permalink=None,
    )
    with engine.connect() as conn:
        violation = invariants.population_floors_hold(_inv_ctx(conn, run_context))
    assert violation is not None
    assert "permalink" in violation.detail


# --- per_source_freshness (FR-01, S half) --------------------------------------------------


def test_freshness_skips_runs_that_swept_nothing(
    engine: Engine, clock: Any, settings: Any, add_source: Any, plant_run: Any, now: int
) -> None:
    """A ``skipped_locked`` run between two real sweeping runs writes no ``run_subreddits``
    row and must not occupy a window slot. If it wrongly displaced the older, successful
    run from the two-run window, the source would read unfetched here; it must not."""
    source = add_source("editors")
    run_a = plant_run(status="partial", created_at=now - 300, started_at=now - 300)
    with engine.begin() as conn:
        repo.upsert_run_subreddit(
            conn,
            run_pk=run_a,
            subreddit_pk=source.pk,
            progress=repo.SweepProgress(
                pages=1,
                items_seen=5,
                new_items=5,
                updated_items=0,
                stop_reason="exhausted",
                error=None,
            ),
        )
    plant_run(status="skipped_locked", created_at=now - 100, started_at=now - 100)

    ctx = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)
    with engine.begin() as conn:
        repo.upsert_run_subreddit(
            conn,
            run_pk=ctx.run_pk,
            subreddit_pk=source.pk,
            progress=repo.SweepProgress(
                pages=1,
                items_seen=0,
                new_items=0,
                updated_items=0,
                stop_reason="error",
                error="403 forbidden",
            ),
        )
    with engine.connect() as conn:
        violation = invariants.per_source_freshness(_inv_ctx(conn, ctx))
    assert violation is None


def test_freshness_stands_down_on_a_terminal_run(
    engine: Engine, clock: Any, settings: Any, add_source: Any, plant_run: Any, now: int
) -> None:
    """Pins both halves in one shot: ``None`` with a terminal status, a violation on the
    identical database without one (round-4 P2, §14.2)."""
    source = add_source("editors")
    run_a = plant_run(status="partial", created_at=now - 300, started_at=now - 300)
    with engine.begin() as conn:
        repo.upsert_run_subreddit(
            conn,
            run_pk=run_a,
            subreddit_pk=source.pk,
            progress=repo.SweepProgress(
                pages=1,
                items_seen=0,
                new_items=0,
                updated_items=0,
                stop_reason="error",
                error="403 forbidden",
            ),
        )
    ctx = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)
    with engine.begin() as conn:
        repo.upsert_run_subreddit(
            conn,
            run_pk=ctx.run_pk,
            subreddit_pk=source.pk,
            progress=repo.SweepProgress(
                pages=1,
                items_seen=0,
                new_items=0,
                updated_items=0,
                stop_reason="error",
                error="403 forbidden",
            ),
        )

    with engine.connect() as conn:
        stood_down = invariants.per_source_freshness(
            _inv_ctx(conn, ctx, terminal_status=RunStatus.RATE_LIMITED)
        )
    assert stood_down is None

    with engine.connect() as conn:
        violation = invariants.per_source_freshness(_inv_ctx(conn, ctx, terminal_status=None))
    assert violation is not None
    assert "editors" in violation.detail


# --- the round-5 P2: a FAILURE violation outranks a terminal status ------------------------


def test_a_failure_violation_outranks_a_rate_limited_terminal_status(
    run_context: runs.RunContext, add_source: Any, engine: Engine, now: int
) -> None:
    """round5-findings.json ``resolve_status_precedence``, asserted end to end rather than
    left emergent (§12.1, §14.1, §11.9, §9).

    ``tests/services/test_runs_lifecycle.py::test_a_failure_violation_outranks_a_terminal_status``
    pins the ordering against a stub carrying ``severity="failure"``. This half pins the
    owner's decision against the **real** ``Violation`` a shipped invariant produces, and
    against the row that decision is about: a rate-limited run whose ``counters_equal_table_deltas``
    also disagrees with the database ends ``failed`` / exit 1, ``runs.error`` still carries the
    terminal message (the 429), and ``violations_json`` still carries the violation -- so
    neither half of the story is lost to the other.
    """
    source = add_source("premiere")
    _insert_bare_post(
        engine,
        reddit_id="p1",
        subreddit_pk=source.pk,
        created_utc=now - 10,
        first_seen_at=now,
        last_fetched_at=now,
    )
    with engine.connect() as conn:
        violations = invariants.check_all(_inv_ctx(conn, run_context))
    assert [v.invariant for v in violations] == ["counters_equal_table_deltas"]
    assert violations[0].severity == invariants.Severity.FAILURE

    terminal_message = "rate limited: a second 429 on r/premiere"
    status = runs.resolve_status(RunStatus.RATE_LIMITED, violations, run_context.warnings)
    assert status is RunStatus.FAILED
    assert exit_code(status) == int(ExitCode.FAILED) == 1

    runs.finish_run_from(
        run_context,
        status=status,
        violations_json=invariants.to_json(violations),
        error=terminal_message,
    )

    runs_table = Base.metadata.tables["runs"]
    with engine.connect() as conn:
        row = (
            conn.execute(select(runs_table).where(runs_table.c.pk == run_context.run_pk))
            .mappings()
            .one()
        )
    assert row["status"] == "failed"
    assert row["error"] == terminal_message
    assert json.loads(row["violations_json"]) == [
        {
            "invariant": "counters_equal_table_deltas",
            "severity": "failure",
            "detail": violations[0].detail,
        }
    ]


# --- the round-5 P1: collect's ordering, at the seam the invariant reads ---------------------


def test_unknown_enum_counter_is_final_before_the_invariants_run(
    engine: Engine,
    settings: Settings,
    clock: Any,
    notifier: Any,
    fake: Any,
    add_source: Any,
    now: int,
) -> None:
    """round5-findings.json ``P1-collect-ordering-unknown-enum``, closed at the seam it is
    about (§11.10's ordered body, §13.1, §14.2).

    ``collect`` materializes ``counters.unknown_enum_values = len(ctx.unknown_enum_keys)``
    **before** it builds the ``InvariantContext``. Written the other way round -- alongside
    ``api_requests`` in the finish block, which is how §6.6 reads -- the counter would still
    be 0 when ``unknown_enum_values_are_counted`` compares it against the database, so a
    single unknown ``post_hint`` (the demo fixture ships exactly one) would turn every
    healthy run ``partial``. Driven through ``collect`` rather than by calling the invariant,
    because the ordering IS the thing under test.
    """
    add_source("premiere")
    fake.add_subreddit("premiere")
    fake.add_post(
        "premiere",
        title="a poll about rendering",
        selftext="which one do you use?",
        author="u1",
        created_utc=now - 3600,
        post_hint="hologram",
    )
    outcome = collect.collect(
        engine, settings=settings, clock=clock, gateway=fake, notifier=notifier
    )
    assert outcome.counters.posts_new == 1
    assert outcome.counters.unknown_enum_values == 1
    assert [v.invariant for v in outcome.violations] == []
    assert outcome.status is RunStatus.OK
    assert outcome.exit_code == 0
