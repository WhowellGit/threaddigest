"""Fixtures for the web suite: a temp database at head, the application over it, and a client.

**No server is started, here or anywhere in the suite.** Starlette's ``TestClient`` routes
through ``_TestClientTransport``, an ``httpx.BaseTransport`` whose ``handle_request`` builds
the ASGI scope and calls the application in this process; no socket is opened, so
``--block-network`` (guard G06) is satisfied with no escape, and ``uvicorn.run`` is never
reached by a test.

**The client is bound to a loopback host on purpose.** ``TestClient``'s default base URL is
``http://testserver``, which the ``Host`` check refuses -- correctly, because that is not a
name this server answers to. Every fixture below therefore asks for ``127.0.0.1``, and the
default is left for ``test_app.py`` to use as the natural control for spec row UI-22.

**The seeded fixtures are module-scoped.** Nothing in this package writes, so one history is
built once per module rather than once per test; it also lets a ``@given`` test name a
module-scoped fixture, which hypothesis allows, rather than suppressing its
function-scoped-fixture health check.

**Isolation.** ``isolated_data_dir`` (autouse, ``tests/conftest.py``) clears every
``THREADDIGEST_*`` variable and points the process at a temp directory; the settings built
here name their own temp directory explicitly as well, so no path in this package can resolve
to the real data directory (guard G19).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from fastapi import FastAPI
from sqlalchemy import Engine
from starlette.testclient import TestClient

from threaddigest.db import repo
from threaddigest.db.engine import db_path_for, engine_for
from threaddigest.db.schema_dump import migrate_to_head
from threaddigest.services.runs import Counters
from threaddigest.settings import Settings
from threaddigest.web.app import create_app
from threaddigest.web.routes.runs import PAGE_SIZE

#: The loopback origin every client uses. A port is present on purpose: the Host check must
#: accept one, because an operator may serve on any port.
LOOPBACK_ORIGIN = "http://127.0.0.1:8765"

#: 2026-09-13 06:30 and 06:41 UTC, the pair ``tests/services/test_report_service.py`` uses,
#: so a failure here lines up against the digest's own fixtures.
STARTED = int(datetime(2026, 9, 13, 6, 30, tzinfo=UTC).timestamp())
FINISHED = int(datetime(2026, 9, 13, 6, 41, tzinfo=UTC).timestamp())

#: The local day every planted run starts on, which is the date ``/reports/{date}`` answers
#: for this history. The shipped ``display_timezone`` is UTC, so the local day is the UTC day;
#: a test that needed another zone would have to say so when it built its settings.
REPORT_DATE = date(2026, 9, 13)

#: Enough dull rows that the four interesting runs fill the first page and a second one
#: exists, so the pager has something to link to and "newest first" is visible.
FILLER_RUNS = PAGE_SIZE - 1

WARNING_INVARIANT = "per_source_freshness"
WARNING_DETAIL = "r/editors has not been fetched for 3 runs"
FAILURE_INVARIANT = "counters_equal_table_deltas"
FAILURE_DETAIL = "posts grew by 13 while counters.posts_new said 12"
RUN_ERROR = "database is locked"

#: The partial run counted three warnings; the invariants named one of them.
UNNAMED_WARNINGS = 2


@dataclass(frozen=True)
class History:
    """What :func:`build_history` planted, named so a test asserts on a row, not a number."""

    ok_pk: int
    partial_pk: int
    failed_pk: int
    running_pk: int
    oldest_on_first_page_pk: int
    premiere_pk: int
    editors_pk: int
    total_runs: int


def _progress(
    *,
    pages: int = 3,
    items_seen: int = 60,
    new_items: int = 12,
    updated_items: int = 40,
    stop_reason: str | None = "exhausted",
    error: str | None = None,
) -> repo.SweepProgress:
    return repo.SweepProgress(
        pages=pages,
        items_seen=items_seen,
        new_items=new_items,
        updated_items=updated_items,
        stop_reason=stop_reason,
        error=error,
    )


def _insert_run(
    engine: Engine,
    *,
    status: str,
    trigger: str = "schedule",
    counters: Counters | None = None,
    api_requests: int = 312,
    budget_limit: int | None = 1500,
    violations_json: str | None = "[]",
    error: str | None = None,
    finished: bool = True,
    outcomes: dict[int, repo.SweepProgress] | None = None,
) -> int:
    """Plant one run row through ``db/repo.py`` -- the functions the collector writes with."""
    options_json = (
        None
        if budget_limit is None
        else json.dumps({"gateway": "fake", "budget": {"limit": budget_limit}})
    )
    with engine.begin() as conn:
        run_pk = repo.insert_run(
            conn,
            repo.RunInsert(
                kind="run",
                trigger=trigger,
                status="running",
                created_at=STARTED,
                started_at=STARTED,
                pid=None,
                stage="sweep",
                options_json=options_json,
                app_version="0.1.0",
                praw_version=None,
                schema_rev="0004",
                settings_fingerprint="9f2c" * 4,
                log_path=None,
            ),
        )
        for subreddit_pk, progress in (outcomes or {}).items():
            repo.upsert_run_subreddit(
                conn, run_pk=run_pk, subreddit_pk=subreddit_pk, progress=progress
            )
        if finished:
            repo.finish_run(
                conn,
                run_pk=run_pk,
                status=status,
                finished_at=FINISHED,
                counters_json=(counters or Counters()).to_json(),
                api_requests=api_requests,
                error=error,
                violations_json=violations_json,
                warnings_json=None,
            )
    return run_pk


def build_history(engine: Engine) -> History:
    """A history with one run of each verdict a reader has to be able to tell apart.

    The filler rows are planted first, so the four interesting runs are the newest, the first
    page is full, and the second page is not empty.
    """
    with engine.connect() as conn:
        workspace_pk = repo.default_workspace_pk(conn)
    with engine.begin() as conn:
        repo.seed_subreddits(
            conn, workspace_pk=workspace_pk, names=["premiere", "editors"], now=STARTED
        )
    with engine.connect() as conn:
        sources = {row.name_lower: row.pk for row in repo.enabled_subreddits(conn, workspace_pk)}
    premiere_pk, editors_pk = sources["premiere"], sources["editors"]

    filler_pks = [
        _insert_run(engine, status="ok", counters=Counters(posts_new=1, api_requests=9))
        for _ in range(FILLER_RUNS)
    ]
    ok_pk = _insert_run(
        engine,
        status="ok",
        counters=Counters(
            posts_new=12, posts_updated=40, rejects=1, pages=3, api_requests=312, warnings=0
        ),
        outcomes={
            premiere_pk: _progress(),
            editors_pk: _progress(pages=1, items_seen=20, new_items=2, updated_items=8),
        },
    )
    partial_pk = _insert_run(
        engine,
        status="partial",
        trigger="cli",
        counters=Counters(
            posts_new=4, posts_updated=2, pages=1, api_requests=44, warnings=UNNAMED_WARNINGS
        ),
        violations_json=json.dumps(
            [{"invariant": WARNING_INVARIANT, "severity": "warning", "detail": WARNING_DETAIL}]
        ),
        outcomes={premiere_pk: _progress(pages=1, items_seen=6, new_items=4, updated_items=2)},
    )
    failed_pk = _insert_run(
        engine,
        status="failed",
        counters=Counters(api_requests=7),
        violations_json=json.dumps(
            [{"invariant": FAILURE_INVARIANT, "severity": "failure", "detail": FAILURE_DETAIL}]
        ),
        error=RUN_ERROR,
        outcomes={
            premiere_pk: _progress(
                pages=0,
                items_seen=0,
                new_items=0,
                updated_items=0,
                stop_reason="error",
                error=RUN_ERROR,
            )
        },
    )
    running_pk = _insert_run(engine, status="running", finished=False, budget_limit=None)
    total = len(filler_pks) + 4
    return History(
        ok_pk=ok_pk,
        partial_pk=partial_pk,
        failed_pk=failed_pk,
        running_pk=running_pk,
        # Rows come newest first, so the first page ends `total - PAGE_SIZE` rows above the
        # oldest filler; that row's pk is the cursor the pager has to offer.
        oldest_on_first_page_pk=filler_pks[total - PAGE_SIZE],
        premiere_pk=premiere_pk,
        editors_pk=editors_pk,
        total_runs=total,
    )


def database_at_head(directory: Path) -> Engine:
    """A fresh database at head inside ``directory``; the caller disposes the engine."""
    directory.mkdir(parents=True, exist_ok=True)
    engine = engine_for(db_path_for(directory))
    migrate_to_head(engine)
    return engine


@pytest.fixture(scope="module")
def seeded_data_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("web") / "data"


@pytest.fixture(scope="module")
def seeded_engine(seeded_data_dir: Path) -> Iterator[Engine]:
    """A temp database at head, shared by one module's tests because none of them writes."""
    engine = database_at_head(seeded_data_dir)
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture(scope="module")
def history(seeded_engine: Engine) -> History:
    return build_history(seeded_engine)


@pytest.fixture(scope="module")
def seeded_app(seeded_engine: Engine, seeded_data_dir: Path) -> FastAPI:
    """The application over the seeded database, with the engine injected by the test."""
    return create_app(settings=Settings(data_dir=seeded_data_dir), engine=seeded_engine)


@pytest.fixture(scope="module")
def client(seeded_app: FastAPI, history: History) -> Iterator[TestClient]:
    """A started client on the seeded application."""
    del history  # ordering only: the rows must exist before any request reads them
    with TestClient(seeded_app, base_url=LOOPBACK_ORIGIN) as started:
        yield started


@pytest.fixture
def empty_app(tmp_path: Path) -> Iterator[FastAPI]:
    """An application over an empty database at head: the other half of spec row UI-01."""
    data_dir = tmp_path / "empty"
    engine = database_at_head(data_dir)
    try:
        yield create_app(settings=Settings(data_dir=data_dir), engine=engine)
    finally:
        engine.dispose()


@pytest.fixture
def empty_client(empty_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(empty_app, base_url=LOOPBACK_ORIGIN) as started:
        yield started
