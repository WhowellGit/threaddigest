"""DB-08: the four hot reads use the declared indexes (``EXPLAIN QUERY PLAN``).

design-round5.md §5.3, §16. A statement-capturing engine listener records the exact SQL
and parameters ``db.repo`` issues, and ``EXPLAIN QUERY PLAN`` on that same text is what
proves the index is actually used rather than merely declared.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from sqlalchemy import Engine, event

from threaddigest.core.models import PostRow
from threaddigest.db.ownership import IngestPath
from threaddigest.db.repo import (
    PostWrite,
    due_posts,
    known_posts_in_window,
    live_counts,
    recount_authors,
    upsert_posts,
)

_POST_KWARGS: dict[str, Any] = {
    "subreddit": "premiere",
    "subreddit_id": None,
    "author": "editorguy",
    "author_fullname": "t2_planquery",
    "author_flair_text": None,
    "author_is_bot": False,
    "title": "title",
    "selftext": "",
    "selftext_html": "",
    "url": None,
    "domain": None,
    "permalink": "/r/premiere/comments/plan/",
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


def _write(reddit_id: str, subreddit_pk: int, now: int, **overrides: Any) -> PostWrite:
    row = PostRow(
        **_POST_KWARGS, reddit_id=reddit_id, fullname=f"t3_{reddit_id}", created_utc=now - 60
    )
    return PostWrite(
        row=row,
        subreddit_pk=subreddit_pk,
        first_seen_at=now,
        last_fetched_at=now,
        next_check_at=overrides.get("next_check_at", now + 86_400),
        check_stage=0,
        content_state=overrides.get("content_state", "live"),
        author_state="known",
        misses=0,
        raw_json="{}",
    )


class _StatementCapture:
    """Records the last statement/parameters SQLAlchemy sends to the DBAPI cursor."""

    def __init__(self) -> None:
        self.statement: str | None = None
        self.parameters: Any = None

    def __call__(
        self,
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        self.statement = statement
        self.parameters = parameters


@pytest.fixture
def capture(engine: Engine) -> Iterator[_StatementCapture]:
    cap = _StatementCapture()
    event.listen(engine, "before_cursor_execute", cap)
    try:
        yield cap
    finally:
        event.remove(engine, "before_cursor_execute", cap)


def _plan(conn: Any, cap: _StatementCapture) -> str:
    params = cap.parameters
    if isinstance(params, list | tuple) and params and isinstance(params[0], list | tuple | dict):
        params = params[0]
    rows = conn.exec_driver_sql(f"EXPLAIN QUERY PLAN {cap.statement}", params or {}).all()
    return " | ".join(str(r) for r in rows)


def test_due_posts_uses_next_check_at_index(
    engine: Engine, subreddit_pk: int, now: int, capture: _StatementCapture
) -> None:
    """The due read is a range from the index plus a sort, and both halves are asserted.

    The queue is ordered ``created_utc DESC`` (newest discussion first, plan § Collector
    algorithm step 2), which is not the column the ``next_check_at <= now`` range is served
    from, so SQLite sorts the range in a temporary b-tree. That sort is the accepted cost of
    the order the plan asks for -- at the few thousand posts this store holds it is nothing,
    and paying for a second index to remove it would be paying for the wrong thing -- so it
    is asserted rather than tolerated: a plan that stopped using the index *or* one that
    silently grew a second sort is a change this test must show. Before 2026-09-17 the read
    ordered by ``next_check_at``, which needed no sort and drained the queue oldest first
    (KI-044).
    """
    with engine.begin() as conn:
        upsert_posts(conn, [_write("due1", subreddit_pk, now)], path=IngestPath.SUBREDDIT_NEW)

    with engine.connect() as conn:
        due_posts(conn, now=now + 999_999, limit=10)
        plan = _plan(conn, capture)
    assert "ix_posts_next_check_at" in plan
    assert "USE TEMP B-TREE FOR ORDER BY" in plan


def test_window_query_uses_subreddit_created_index(
    engine: Engine, subreddit_pk: int, now: int, capture: _StatementCapture
) -> None:
    with engine.begin() as conn:
        upsert_posts(conn, [_write("win1", subreddit_pk, now)], path=IngestPath.SUBREDDIT_NEW)

    with engine.connect() as conn:
        known_posts_in_window(conn, subreddit_pk=subreddit_pk, since_created_utc=0)
        plan = _plan(conn, capture)
    assert "ix_posts_subreddit_pk_created_utc" in plan


def test_author_query_uses_author_index(
    engine: Engine, subreddit_pk: int, now: int, capture: _StatementCapture
) -> None:
    with engine.begin() as conn:
        upsert_posts(conn, [_write("auth1", subreddit_pk, now)], path=IngestPath.SUBREDDIT_NEW)

    with engine.begin() as conn:
        recount_authors(conn, ["t2_planquery"])
        plan = _plan(conn, capture)
    assert "ix_posts_author_fullname" in plan


def test_live_feed_uses_content_state_index(
    engine: Engine, subreddit_pk: int, now: int, capture: _StatementCapture
) -> None:
    with engine.begin() as conn:
        upsert_posts(conn, [_write("live1", subreddit_pk, now)], path=IngestPath.SUBREDDIT_NEW)

    with engine.connect() as conn:
        live_counts(conn)
        plan = _plan(conn, capture)
    assert "ix_posts_content_state" in plan
