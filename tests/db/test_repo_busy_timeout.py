"""DB-14: a writer holding ``BEGIN IMMEDIATE`` makes a competing transaction wait up to its
own ``busy_timeout_ms`` and then fail cleanly with nothing committed.

design-round5.md §10.5. This is one of the two documented, bounded exceptions to "tests
never sleep": the *SQLite driver* waits on a real write lock, bounded by
``engine_for(..., busy_timeout_ms=300)``, not a ``time.sleep`` and not an injectable clock.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError

from insightminer.core.models import PostRow
from insightminer.db.engine import engine_for
from insightminer.db.ownership import IngestPath
from insightminer.db.repo import PostWrite, RunInsert, insert_run, upsert_posts
from insightminer.db.schema import Base

_POST_KWARGS: dict[str, Any] = {
    "subreddit": "premiere",
    "subreddit_id": None,
    "author": "editorguy",
    "author_fullname": "t2_abcd12",
    "author_flair_text": None,
    "author_is_bot": False,
    "title": "title",
    "selftext": "",
    "selftext_html": "",
    "url": None,
    "domain": None,
    "permalink": "/r/premiere/comments/lockme/",
    "edited_utc": None,
    "score": 1,
    "upvote_ratio": None,
    "num_comments": 0,
    "link_flair_text": None,
    "over_18": False,
    "spoiler": False,
    "is_self": True,
    "is_video": False,
    "is_gallery": False,
    "post_hint": None,
    "locked": False,
    "stickied": False,
    "archived": False,
    "distinguished": None,
    "crosspost_parent": None,
    "num_crossposts": 0,
    "removed_by_category": None,
    "source": "subreddit_new",
}


def _write(subreddit_pk: int, now: int) -> PostWrite:
    row = PostRow(**_POST_KWARGS, reddit_id="lockme", fullname="t3_lockme", created_utc=now - 60)
    return PostWrite(
        row=row,
        subreddit_pk=subreddit_pk,
        first_seen_at=now,
        last_fetched_at=now,
        next_check_at=now + 86_400,
        check_stage=0,
        content_state="live",
        author_state="known",
        misses=0,
        raw_json="{}",
    )


def _run_insert(now: int) -> RunInsert:
    return RunInsert(
        kind="run",
        trigger="cli",
        status="running",
        created_at=now,
        started_at=now,
        pid=None,
        stage=None,
        options_json=None,
        app_version=None,
        praw_version=None,
        schema_rev=None,
        settings_fingerprint=None,
        log_path=None,
    )


def test_second_writer_waits_then_page_fails_with_nothing_committed(
    db_path: Path, engine: Any, subreddit_pk: int, now: int
) -> None:
    """Two halves, because SQLite does not invoke the busy handler for every shape.

    * **The wait.** A transaction whose *first* statement is a write -- the shape T6's
      terminal transaction and every heartbeat have -- really pays ``busy_timeout_ms``
      before it gives up. Measured with ``time.monotonic`` against the configured value.
    * **The page.** ``upsert_posts`` classifies with a ``SELECT`` before it writes
      (design-round5.md §5.2 step 1), so its transaction is already a *read* transaction
      when the upsert asks for the write lock. SQLite returns ``SQLITE_BUSY`` immediately in
      that shape rather than invoking the busy handler, because it cannot prove the wait
      would not deadlock (btree.c: the handler runs only while
      ``pBt->inTransaction == TRANS_NONE``). So the page does not wait -- and everything
      DB-14 is actually about still holds and is asserted here: the failure is
      ``database is locked``, and **nothing** from that page is committed.

    Both halves run against one held ``BEGIN IMMEDIATE``. The holder speaks to the driver in
    AUTOCOMMIT because ``engine_for`` emits its own ``BEGIN`` from the ``begin`` event, and
    ``BEGIN IMMEDIATE`` inside that is "cannot start a transaction within a transaction".
    """
    holder = engine_for(db_path)
    writer = engine_for(db_path, busy_timeout_ms=300)
    try:
        with holder.connect().execution_options(isolation_level="AUTOCOMMIT") as hconn:
            hconn.exec_driver_sql("BEGIN IMMEDIATE")
            hconn.exec_driver_sql(
                "INSERT INTO ui_state (key, value, updated_at) VALUES ('lock-probe', 'x', 0)"
            )

            start = time.monotonic()
            with pytest.raises(OperationalError, match="database is locked"):
                with writer.begin() as wconn:
                    insert_run(wconn, _run_insert(now))
            elapsed = time.monotonic() - start
            assert elapsed >= 0.3, "a write-first transaction must wait out busy_timeout_ms"

            with pytest.raises(OperationalError, match="database is locked"):
                with writer.begin() as wconn:
                    upsert_posts(wconn, [_write(subreddit_pk, now)], path=IngestPath.SUBREDDIT_NEW)

            hconn.exec_driver_sql("ROLLBACK")
    finally:
        writer.dispose()
        holder.dispose()

    posts = Base.metadata.tables["posts"]
    runs = Base.metadata.tables["runs"]
    with engine.connect() as conn:
        committed = conn.execute(select(posts).where(posts.c.reddit_id == "lockme")).all()
        run_rows = conn.execute(select(func.count()).select_from(runs)).scalar_one()
    assert committed == [], "the failed page must leave nothing committed"
    assert run_rows == 0, "the failed write-first transaction must leave nothing committed"
