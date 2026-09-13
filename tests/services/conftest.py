"""Shared fixtures for ``tests/services/``: a head DB at a temp path, the fake clock and
notifier, and small helpers for planting rows and diffing table state directly through
``db/repo.py`` (design-round5.md §2.2, §16).

Nothing here imports ``sqlalchemy.text`` or ``create_engine`` (§2.3): the engine is built
through ``db.engine.engine_for`` exactly as ``tests/db/conftest.py`` does, and every helper
below is either that, or plain SQLAlchemy Core over ``Base.metadata.tables[...]``.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Sequence
from pathlib import Path

import pytest
from sqlalchemy import Engine, func, select

from insightminer.adapters.clock import FakeClock
from insightminer.adapters.notify import FakeNotifier
from insightminer.db import repo
from insightminer.db.engine import engine_for
from insightminer.db.schema import Base
from insightminer.db.schema_dump import migrate_to_head
from insightminer.settings import Settings

#: A fixed epoch second, well inside the project's lifetime -- matches tests/db/conftest.py's
#: convention so a failure's timestamp is easy to eyeball across both packages.
NOW = 1_800_000_000


@pytest.fixture
def now() -> int:
    return NOW


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "insightminer.db"


@pytest.fixture
def engine(db_path: Path) -> Iterator[Engine]:
    """A read-write engine on a temp database migrated to head (one engine per test, §3.2)."""
    eng = engine_for(db_path)
    try:
        migrate_to_head(eng)
        yield eng
    finally:
        eng.dispose()


@pytest.fixture
def clock() -> FakeClock:
    """A clock that never sleeps for real; starts at :data:`NOW`."""
    return FakeClock(start=NOW)


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


PlantRun = Callable[..., int]


@pytest.fixture
def plant_run(engine: Engine) -> PlantRun:
    """Insert one ``runs`` row directly through ``db/repo.py``, bypassing ``runs.start_run``.

    Service-level lifecycle tests need rows in states ``start_run`` never produces on its
    own (a stale heartbeat, a dead pid, an orphaned ``queued`` row), so this plants the row
    with ``repo.insert_run`` and then, when ``heartbeat_at`` is given, stamps it with a
    second statement through ``repo.touch_run`` -- the same two functions the production
    lifecycle uses, never a raw ``UPDATE``. Returns the new row's pk.
    """

    def _plant(
        *,
        status: str = "running",
        pid: int | None = None,
        created_at: int = NOW,
        started_at: int | None = NOW,
        heartbeat_at: int | None = None,
        stage: str | None = None,
        kind: str = "run",
        trigger: str = "cli",
    ) -> int:
        run = repo.RunInsert(
            kind=kind,
            trigger=trigger,
            status=status,
            created_at=created_at,
            started_at=started_at,
            pid=pid,
            stage=stage,
            options_json=None,
            app_version=None,
            praw_version=None,
            schema_rev=None,
            settings_fingerprint=None,
            log_path=None,
        )
        with engine.begin() as conn:
            pk = repo.insert_run(conn, run)
            if heartbeat_at is not None:
                repo.touch_run(conn, run_pk=pk, heartbeat_at=heartbeat_at, stage=stage)
        return pk

    return _plant


SnapshotTables = Callable[[Sequence[str]], dict[str, int]]


@pytest.fixture
def snapshot_tables(engine: Engine) -> SnapshotTables:
    """Row counts for the named tables, taken in one connection (DB-54's baseline shape)."""

    def _snapshot(tables: Sequence[str]) -> dict[str, int]:
        with engine.connect() as conn:
            return {
                name: int(
                    conn.execute(
                        select(func.count()).select_from(Base.metadata.tables[name])
                    ).scalar_one()
                )
                for name in tables
            }

    return _snapshot


@pytest.fixture
def run_context(engine: Engine, clock: FakeClock, settings: Settings):
    """A persisted ``RunContext`` built the production way: ``runs.start_run`` (T2 + T3).

    Imported lazily so this fixture's own collection failure (the module does not exist
    yet) is the honest ``ImportError`` rather than a fixture-setup error unrelated to the
    step being tested.
    """
    from insightminer.services import runs

    return runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)
