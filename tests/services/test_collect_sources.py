"""KI-017 (external round one): a run with no enabled source collects nothing and must say so.
It closes ``partial`` with a ``no_enabled_sources`` warning; the hourly ``doctor`` carries the
alert through ``check_enabled_sources``, because ``partial`` never notifies on its own.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine

from threaddigest.core.retry import RunStatus
from threaddigest.services import collect, runs

BASE = 1_757_700_000


def test_a_run_with_no_enabled_source_is_partial_not_ok(
    fake: Any, add_source: Any, engine: Engine, clock: Any, settings: Any, notifier: Any
) -> None:
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", created_utc=BASE)
    add_source("premiere")
    fake.set_status("premiere", "quarantined")  # disabled on first sight (SS-04)

    first = collect.collect(engine, settings=settings, clock=clock, gateway=fake, notifier=notifier)
    second = collect.collect(
        engine, settings=settings, clock=clock, gateway=fake, notifier=notifier
    )

    assert first.status is not RunStatus.OK
    assert second.counters.pages == 0 and second.sweep.subreddits == ()  # nothing fetched
    assert second.status is RunStatus.PARTIAL, (
        f"a run that swept nothing closed {second.status.value!r}"
    )
    with engine.connect() as conn:
        status, counters_json = conn.exec_driver_sql(
            "SELECT status, counters_json FROM runs WHERE pk = ?", (second.run_pk,)
        ).one()
    assert status == "partial"
    assert runs.Counters.from_json(counters_json).warnings == 1
