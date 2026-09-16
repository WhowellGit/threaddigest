"""GT-01 / G30: every invariant in ``INVARIANTS`` planted and observed through
``runs.status`` + ``runs.violations_json`` -- parametrized over the production tuple so an
invariant added without a control is a ``KeyError``, not a silent gap (design-round5.md
section 14.3, section 16).
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine, insert, select, update
from sqlalchemy.schema import DropTable
from typer.testing import CliRunner

from threaddigest import cli
from threaddigest.adapters.reddit_fake import FakeRedditGateway
from threaddigest.db import repo
from threaddigest.db.engine import db_path_for, engine_for
from threaddigest.db.schema import Base
from threaddigest.services import invariants as invariants_module


@dataclass
class Ctx:
    """Everything one planter needs: the harness, and the fixtures already wired up."""

    cli_runner: CliRunner
    gateway: FakeRedditGateway
    data_dir: Path
    fixture_path: Path
    table_rows: Callable[..., list[dict[str, Any]]]

    def invoke(self, *extra_args: str) -> Any:
        args = ["run", "--gateway", "fake", "--fixture", str(self.fixture_path), *extra_args]
        return self.cli_runner.invoke(cli.app, args)

    def engine(self) -> Engine:
        return engine_for(db_path_for(self.data_dir))


@pytest.fixture
def ctx(
    cli_runner: CliRunner,
    loaded_gateway: FakeRedditGateway,
    db_at_head: Path,
    demo_fixture_path: Path,
    table_rows: Callable[..., list[dict[str, Any]]],
) -> Ctx:
    return Ctx(cli_runner, loaded_gateway, db_at_head, demo_fixture_path, table_rows)


# --- planters (design-round5.md section 14.3's table, one function per invariant) -----------


def _plant_counters_equal_table_deltas(ctx: Ctx) -> Any:
    def _plant() -> None:
        engine = ctx.engine()
        try:
            with engine.connect() as conn:
                workspace_pk = repo.default_workspace_pk(conn)
                source = repo.enabled_subreddits(conn, workspace_pk)[0]
            with engine.begin() as conn:
                conn.execute(
                    insert(Base.metadata.tables["posts"]).values(
                        reddit_id="plantedgt01",
                        fullname="t3_plantedgt01",
                        subreddit_pk=source.pk,
                        author="planted",
                        author_fullname="t2_planted",
                        title="planted extra row",
                        selftext="",
                        url="https://example.com/planted",
                        permalink="/r/planted/comments/plantedgt01/",
                        created_utc=1_800_000_000,
                        first_seen_at=1_800_000_000,
                        last_fetched_at=1_800_000_000,
                        next_check_at=1_800_086_400,
                        source="subreddit_new",
                        normalizer_version=1,
                        raw_json="{}",
                        content_state="live",
                        removed_by_category=None,
                    )
                )
        finally:
            engine.dispose()

    ctx.gateway.on_call("page", 1, _plant)
    return ctx.invoke()


def _plant_no_other_running_rows(ctx: Ctx) -> Any:
    now = int(time.time())
    engine = ctx.engine()
    try:
        with engine.begin() as conn:
            other_pk = repo.insert_run(
                conn,
                repo.RunInsert(
                    kind="run",
                    trigger="cli",
                    status="running",
                    created_at=now,
                    started_at=now,
                    pid=1,
                    stage=None,
                    options_json=None,
                    app_version=None,
                    praw_version=None,
                    schema_rev=None,
                    settings_fingerprint=None,
                    log_path=None,
                ),
            )
            repo.touch_run(conn, run_pk=other_pk, heartbeat_at=now, stage=None)
    finally:
        engine.dispose()
    return ctx.invoke()


def _plant_fts_membership_equals_live(ctx: Ctx) -> Any:
    """Plants INSIDE one run, on a page-1 post, exactly matching that row's stored
    title/selftext/author (section 14.3's rebuilt DB-26 planter, round-4 P1-5).
    """
    planted: dict[str, Any] = {}

    def _plant() -> None:
        engine = ctx.engine()
        try:
            posts = Base.metadata.tables["posts"]
            with engine.connect() as conn:
                row = conn.execute(select(posts).limit(1)).mappings().first()
            assert row is not None, "no page-1 post committed yet"
            planted["pk"] = row["pk"]
            with engine.begin() as conn:
                conn.exec_driver_sql(
                    "INSERT INTO posts_fts(posts_fts, rowid, title, selftext, author) "
                    "VALUES ('delete', ?, ?, ?, ?)",
                    (row["pk"], row["title"], row["selftext"], row["author"]),
                )
        finally:
            engine.dispose()

    ctx.gateway.on_call("page", 2, _plant)
    return ctx.invoke()


def _plant_rows_carry_current_normalizer_version(ctx: Ctx) -> Any:
    def _plant() -> None:
        engine = ctx.engine()
        try:
            posts = Base.metadata.tables["posts"]
            with engine.connect() as conn:
                row = conn.execute(select(posts.c.pk).limit(1)).first()
            assert row is not None
            with engine.begin() as conn:
                conn.execute(update(posts).where(posts.c.pk == row.pk).values(normalizer_version=0))
        finally:
            engine.dispose()

    ctx.gateway.on_call("page", 2, _plant)
    return ctx.invoke()


def _plant_unknown_enum_values_are_counted(ctx: Ctx) -> Any:
    def _plant() -> None:
        engine = ctx.engine()
        try:
            posts = Base.metadata.tables["posts"]
            with engine.connect() as conn:
                row = conn.execute(select(posts.c.pk).limit(1)).first()
            assert row is not None
            with engine.begin() as conn:
                conn.execute(update(posts).where(posts.c.pk == row.pk).values(post_hint="hologram"))
        finally:
            engine.dispose()

    ctx.gateway.on_call("page", 2, _plant)
    return ctx.invoke()


def _plant_population_floors_hold(ctx: Ctx) -> Any:
    """``fake.remove_field("t3_<id>", "permalink")`` before the run: ``core.normalize``
    then yields ``permalink=None`` and the live row breaks the floor.
    """
    data = json.loads(ctx.fixture_path.read_text(encoding="utf-8"))
    target = next(
        post["name"]
        for post in data["posts"]
        if post.get("removed_by_category") != "deleted"
        and post.get("selftext") != "[deleted]"
        and not post.get("stickied")
        and "crosspost_parent" not in post
    )
    ctx.gateway.remove_field(target, "permalink")
    return ctx.invoke()


def _plant_per_source_freshness(ctx: Ctx) -> Any:
    """``fake.set_status("editors", "forbidden")``; invoke ``run`` twice -- the window
    includes the current run (section 14.2), so the SECOND run is where the violation
    appears.
    """
    ctx.gateway.set_status("editors", "forbidden")
    first = ctx.invoke()
    assert first.exit_code == 3, first.output
    return ctx.invoke()


def _plant_crashing_invariant(ctx: Ctx) -> Any:
    """Drops a table ``TRACKED_TABLES`` counts but tranche A never writes, so
    ``counters_equal_table_deltas``'s own ``repo.table_counts`` raises mid-invariant-pass
    (section 14.1, section 14.3's crashing-invariant control).
    """

    def _plant() -> None:
        engine = ctx.engine()
        try:
            with engine.begin() as conn:
                conn.execute(DropTable(Base.metadata.tables["post_themes"]))
        finally:
            engine.dispose()

    ctx.gateway.on_call("page", 1, _plant)
    return ctx.invoke()


PLANTERS: dict[str, Callable[[Ctx], Any]] = {
    "counters_equal_table_deltas": _plant_counters_equal_table_deltas,
    "no_other_running_rows": _plant_no_other_running_rows,
    "fts_membership_equals_live": _plant_fts_membership_equals_live,
    "rows_carry_current_normalizer_version": _plant_rows_carry_current_normalizer_version,
    "unknown_enum_values_are_counted": _plant_unknown_enum_values_are_counted,
    "population_floors_hold": _plant_population_floors_hold,
    "per_source_freshness": _plant_per_source_freshness,
}


@pytest.mark.gate("GT-01")
@pytest.mark.parametrize("invariant", invariants_module.INVARIANTS, ids=lambda fn: fn.__name__)
def test_planted_violation_flips_the_run(invariant: Any, ctx: Ctx) -> None:
    plant = PLANTERS[invariant.__name__]  # a missing entry is a KeyError, not a silent gap
    result = plant(ctx)
    assert result.exit_code in {1, 3}, result.output
    row = ctx.table_rows("runs")[-1]
    assert row["status"] != "ok"
    names = {v["invariant"] for v in json.loads(row["violations_json"])}
    assert invariant.__name__ in names


@pytest.mark.gate("G30")
def test_every_invariant_has_a_planter() -> None:
    assert {fn.__name__ for fn in invariants_module.INVARIANTS} == set(PLANTERS)


@pytest.mark.gate("GT-01")
def test_a_crashing_invariant_fails_the_run_rather_than_leaving_it_running(ctx: Ctx) -> None:
    """The crashing-invariant control plants a REAL crash (dropping ``post_themes`` mid-run),
    not a patched tuple: ``check_all``'s per-invariant catch must still close the run row
    through the ordinary ``finish_run`` path, ``failed``/exit 1, naming the crashed
    invariant (section 14.1, section 14.3).
    """
    result = _plant_crashing_invariant(ctx)
    assert result.exit_code == 1, result.output
    row = ctx.table_rows("runs")[-1]
    assert row["status"] == "failed"
    assert row["finished_at"] is not None
    violations = json.loads(row["violations_json"])
    crashed = next(v for v in violations if v["invariant"] == "counters_equal_table_deltas")
    assert "invariant crashed" in crashed["detail"]
    assert "OperationalError" in crashed["detail"]
