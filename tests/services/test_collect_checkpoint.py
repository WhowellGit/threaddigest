"""KI-013: the end-of-run checkpoint cannot truncate the write-ahead log while a reader holds a
snapshot, and the web UI is a reader by design. The run retries briefly, then records a
warning and closes ``partial`` instead of silently leaving the pages it wrote, a scrub's
included, in a log ``secure_delete`` does not cover.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import Engine

from threaddigest.core.retry import RunStatus
from threaddigest.db.engine import checkpoint_truncate
from threaddigest.services import collect, runs

BASE = 1_757_700_000


def _wal_size(db_path: Path) -> int:
    wal = db_path.with_name(db_path.name + "-wal")
    return wal.stat().st_size if wal.exists() else 0


def test_a_reader_during_the_final_checkpoint_leaves_a_warning_and_a_partial_run(
    fake: Any,
    add_source: Any,
    engine: Engine,
    db_path: Path,
    clock: Any,
    settings: Any,
    notifier: Any,
) -> None:
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    add_source("premiere")
    slept_before = clock.total_slept

    reader = engine.connect().execution_options(isolation_level="AUTOCOMMIT")
    try:
        reader.exec_driver_sql("BEGIN")
        reader.exec_driver_sql("SELECT count(*) FROM posts").all()  # a snapshot the log must keep
        outcome = collect.collect(
            engine, settings=settings, clock=clock, gateway=fake, notifier=notifier
        )
        assert _wal_size(db_path) > 0  # the log could not be truncated under the reader
    finally:
        reader.exec_driver_sql("ROLLBACK")
        reader.close()

    assert outcome.status == RunStatus.PARTIAL
    assert clock.total_slept - slept_before == pytest.approx(
        collect.CHECKPOINT_RETRY_SECONDS * (collect.CHECKPOINT_ATTEMPTS - 1)
    )
    with engine.connect() as conn:
        status, counters_json = conn.exec_driver_sql(
            "SELECT status, counters_json FROM runs WHERE pk = ?", (outcome.run_pk,)
        ).one()
    assert status == "partial"
    assert runs.Counters.from_json(counters_json).warnings == 1

    # The control: with the reader gone the same checkpoint truncates the log.
    busy, _, _ = checkpoint_truncate(engine)
    assert busy == 0
    assert _wal_size(db_path) == 0
