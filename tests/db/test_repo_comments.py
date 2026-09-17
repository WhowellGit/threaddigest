"""The comment-tree write surface of ``db/repo.py``: DB-24, and the tree stamp's immutables.

M1b's database layer. The upsert follows ``upsert_posts``' classify-upsert-read-back shape,
so the tests here are about what is *different* about a tree: parents resolved after the
insert rather than during it (DB-24), a post's ``comment_more`` stubs replaced wholesale
because a skipped stub is not addressable later, a stamp that may move the coverage and
ladder columns and nothing else, and a terminal deletion state the upsert may never write
content over (the state DB-22 enforces at M1c, which this write must not hand it undone).

``test_the_due_queue_is_newest_first_among_due_posts`` is the order half of the queue fix;
the plan half is ``tests/db/test_query_plans.py::test_due_posts_uses_next_check_at_index``.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import Engine, select

from threaddigest.core.models import CommentRow, PostRow
from threaddigest.db.ownership import IngestPath
from threaddigest.db.repo import (
    CommentWrite,
    MoreWrite,
    PostWrite,
    TreeStamp,
    due_posts,
    replace_comment_more,
    stamp_tree_on_post,
    upsert_comments,
    upsert_posts,
)
from threaddigest.db.schema import Base

POST_KWARGS: dict[str, Any] = {
    "subreddit": "premiere",
    "subreddit_id": "t5_2s9fq",
    "author": "editorguy",
    "author_fullname": "t2_abcd12",
    "author_flair_text": None,
    "author_is_bot": False,
    "title": "a title",
    "selftext": "a body",
    "selftext_html": "<p>a body</p>",
    "url": None,
    "domain": None,
    "permalink": "/r/premiere/comments/abc123/",
    "edited_utc": None,
    "score": 1,
    "upvote_ratio": 0.9,
    "num_comments": 2,
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
    "source": IngestPath.SUBREDDIT_NEW.value,
}

COMMENT_KWARGS: dict[str, Any] = {
    "author": "helpful",
    "author_fullname": "t2_helper",
    "author_is_bot": False,
    "body_html": "<p>try the GPU renderer</p>",
    "edited_utc": None,
    "score": 4,
    "depth": 0,
    "permalink": "/r/premiere/comments/abc123/_/c1/",
    "is_submitter": False,
    "stickied": False,
    "distinguished": None,
    "source": IngestPath.COMMENTS.value,
}


def _post_write(reddit_id: str, subreddit_pk: int, now: int, *, created_utc: int) -> PostWrite:
    row = PostRow(
        **POST_KWARGS,
        reddit_id=reddit_id,
        fullname=f"t3_{reddit_id}",
        created_utc=created_utc,
    )
    return PostWrite(
        row=row,
        subreddit_pk=subreddit_pk,
        first_seen_at=now,
        last_fetched_at=now,
        next_check_at=created_utc + 86_400,
        check_stage=0,
        content_state="live",
        author_state="known",
        misses=0,
        raw_json="{}",
    )


def _seed_post(engine: Engine, reddit_id: str, subreddit_pk: int, now: int, *, created: int) -> int:
    with engine.begin() as conn:
        outcome = upsert_posts(
            conn,
            [_post_write(reddit_id, subreddit_pk, now, created_utc=created)],
            path=IngestPath.SUBREDDIT_NEW,
        )
    return outcome.pks[reddit_id]


def _comment(
    reddit_id: str, *, post_reddit_id: str, parent_fullname: str, **overrides: Any
) -> CommentRow:
    kwargs = {**COMMENT_KWARGS, "body": "a reply", **overrides}
    return CommentRow(
        **kwargs,
        reddit_id=reddit_id,
        fullname=f"t1_{reddit_id}",
        post_reddit_id=post_reddit_id,
        parent_fullname=parent_fullname,
        created_utc=1_800_000_100,
    )


def _write(row: CommentRow, post_pk: int, *, raw: str = '{"wire":"json"}') -> CommentWrite:
    return CommentWrite(row=row, post_pk=post_pk, raw_json=raw)


def _stored(engine: Engine, reddit_id: str) -> Any:
    comments = Base.metadata.tables["comments"]
    with engine.connect() as conn:
        return (
            conn.execute(comments.select().where(comments.c.reddit_id == reddit_id))
            .mappings()
            .one()
        )


# --- the due queue ---------------------------------------------------------------------------


def test_the_due_queue_is_newest_first_among_due_posts(
    engine: Engine, subreddit_pk: int, now: int
) -> None:
    """The backfill's point is to reach the newest discussion first (plan § Collector step 2).

    Every post sits at stage 0 during the first backfill, so ``next_check_at`` is
    ``created_utc`` plus a day for all of them and ordering by it is ordering by age: the
    oldest post in the store would be collected first and the newest last. Seeded oldest-due
    first on purpose, so a queue that kept the shipped order would return exactly the reverse
    of what this asserts.
    """
    _seed_post(engine, "oldest", subreddit_pk, now, created=now - 30 * 86_400)
    _seed_post(engine, "middle", subreddit_pk, now, created=now - 10 * 86_400)
    _seed_post(engine, "newest", subreddit_pk, now, created=now - 2 * 86_400)
    _seed_post(engine, "not_due", subreddit_pk, now, created=now)

    with engine.connect() as conn:
        due = due_posts(conn, now=now, limit=10)

    assert [reddit_id for _pk, reddit_id in due] == ["newest", "middle", "oldest"]


# --- the comment upsert ----------------------------------------------------------------------


def test_upsert_comments_reports_new_and_updated(
    engine: Engine, subreddit_pk: int, now: int
) -> None:
    """Classify-upsert-read-back, as ``upsert_posts`` does it: the counts a run row folds in."""
    post_pk = _seed_post(engine, "abc123", subreddit_pk, now, created=now - 86_400)
    first = _comment("c1", post_reddit_id="abc123", parent_fullname="t3_abc123")
    with engine.begin() as conn:
        opening = upsert_comments(conn, [_write(first, post_pk)], now=now)

    second = _comment("c2", post_reddit_id="abc123", parent_fullname="t3_abc123")
    with engine.begin() as conn:
        again = upsert_comments(
            conn, [_write(first, post_pk), _write(second, post_pk)], now=now + 60
        )

    assert opening.new_ids == ("c1",)
    assert opening.updated_ids == ()
    assert set(again.new_ids) == {"c2"}
    assert set(again.updated_ids) == {"c1"}
    assert set(again.pks) == {"c1", "c2"}
    assert again.pks["c1"] == opening.pks["c1"]
    assert _stored(engine, "c1")["first_seen_at"] == now
    assert _stored(engine, "c1")["last_fetched_at"] == now + 60


def test_a_comment_whose_parent_is_behind_a_stub_keeps_a_null_parent_pk(
    engine: Engine, subreddit_pk: int, now: int
) -> None:
    """DB-24. ``parent_comment_pk`` carries no foreign key by design: a tree arrives with its
    parents hidden behind ``more`` stubs, and a comment whose parent we do not hold must still
    be stored, at the depth Reddit gave it, rather than rejected or reparented.

    Both directions in one test: the reply whose parent *is* in the store resolves, so a NULL
    cannot be bought by resolving nothing at all.
    """
    post_pk = _seed_post(engine, "abc123", subreddit_pk, now, created=now - 86_400)
    top = _comment("c1", post_reddit_id="abc123", parent_fullname="t3_abc123")
    held = _comment("c2", post_reddit_id="abc123", parent_fullname="t1_c1")
    orphan = _comment("c3", post_reddit_id="abc123", parent_fullname="t1_hidden")
    with engine.begin() as conn:
        outcome = upsert_comments(
            conn,
            [_write(top, post_pk), _write(held, post_pk), _write(orphan, post_pk)],
            now=now,
        )

    assert _stored(engine, "c1")["parent_comment_pk"] is None  # its parent is the post
    assert _stored(engine, "c2")["parent_comment_pk"] == outcome.pks["c1"]
    assert _stored(engine, "c3")["parent_comment_pk"] is None
    assert _stored(engine, "c3")["parent_fullname"] == "t1_hidden"


def test_a_terminal_deletion_state_is_never_overwritten_with_content(
    engine: Engine, subreddit_pk: int, now: int
) -> None:
    """``deleted_by_author`` is terminal (``core.deletion.decide`` rule 1), so the row's content
    is terminal with it: the statement's ``SET`` clause holds the stored value on a row already
    in that state, whatever the caller passes.

    Enforced in the SQL rather than in the values the caller builds, because the state is what
    M1c's scrub acts on: a tree re-fetch that wrote a body back over a scrubbed row would undo
    a deletion the store had already honoured (DB-22).
    """
    post_pk = _seed_post(engine, "abc123", subreddit_pk, now, created=now - 86_400)
    row = _comment("c1", post_reddit_id="abc123", parent_fullname="t3_abc123")
    deleted = _comment(
        "c1",
        post_reddit_id="abc123",
        parent_fullname="t3_abc123",
        body="[deleted]",
        author=None,
        author_fullname=None,
    )
    with engine.begin() as conn:
        upsert_comments(conn, [_write(row, post_pk)], now=now)
    with engine.begin() as conn:
        upsert_comments(conn, [_write(deleted, post_pk, raw='{"body":"[deleted]"}')], now=now + 60)

    with engine.begin() as conn:
        upsert_comments(conn, [_write(row, post_pk, raw='{"body":"back"}')], now=now + 120)

    stored = _stored(engine, "c1")
    assert stored["content_state"] == "deleted_by_author"
    assert stored["body"] == "[deleted]"
    assert stored["raw_json"] == '{"body":"[deleted]"}'
    assert stored["author"] is None
    # The row still records that this run looked at it: only content is frozen.
    assert stored["last_fetched_at"] == now + 120


def test_a_removed_comment_that_returns_is_updated_again(
    engine: Engine, subreddit_pk: int, now: int
) -> None:
    """The control for the test above: only the *terminal* state freezes content.

    A moderator removal is not terminal — ``decide`` rule 8 returns an item to ``live`` on
    intact content — so a guard keyed on anything wider than ``deleted_by_author`` would
    quietly keep the tombstone forever, and nothing else here would notice.
    """
    post_pk = _seed_post(engine, "abc123", subreddit_pk, now, created=now - 86_400)
    removed = _comment("c1", post_reddit_id="abc123", parent_fullname="t3_abc123", body="[removed]")
    restored = _comment("c1", post_reddit_id="abc123", parent_fullname="t3_abc123", body="approved")
    with engine.begin() as conn:
        upsert_comments(conn, [_write(removed, post_pk)], now=now)
    assert _stored(engine, "c1")["content_state"] == "removed_by_moderator"

    with engine.begin() as conn:
        upsert_comments(conn, [_write(restored, post_pk)], now=now + 60)

    stored = _stored(engine, "c1")
    assert stored["content_state"] == "live"
    assert stored["body"] == "approved"


# --- the stubs and the stamp -----------------------------------------------------------------


def test_replacing_comment_more_leaves_only_this_fetch_s_stubs(
    engine: Engine, subreddit_pk: int, now: int
) -> None:
    """A skipped stub is not addressable in a later run, so a tree write replaces a post's
    stubs wholesale rather than merging them: what is stored is what this fetch left.

    The second post is seeded and asserted untouched because ``DELETE`` with the wrong (or a
    missing) predicate is the way this function fails.
    """
    post_pk = _seed_post(engine, "abc123", subreddit_pk, now, created=now - 86_400)
    other_pk = _seed_post(engine, "def456", subreddit_pk, now, created=now - 86_400)
    top = _comment("c1", post_reddit_id="abc123", parent_fullname="t3_abc123")
    with engine.begin() as conn:
        upsert_comments(conn, [_write(top, post_pk)], now=now)
        replace_comment_more(
            conn,
            post_pk=post_pk,
            stubs=[MoreWrite("t3_abc123", 12), MoreWrite("t1_c1", 3)],
        )
        replace_comment_more(conn, post_pk=other_pk, stubs=[MoreWrite("t3_def456", 5)])

    with engine.begin() as conn:
        written = replace_comment_more(conn, post_pk=post_pk, stubs=[MoreWrite("t1_c1", 1)])

    more = Base.metadata.tables["comment_more"]
    comments = Base.metadata.tables["comments"]
    with engine.connect() as conn:
        comment_pk = conn.execute(
            select(comments.c.pk).where(comments.c.reddit_id == "c1")
        ).scalar_one()
        rows = conn.execute(
            select(more.c.post_pk, more.c.parent_comment_pk, more.c.count).order_by(more.c.post_pk)
        ).all()

    assert written == 1
    assert rows == [(post_pk, comment_pk, 1), (other_pk, None, 5)]


def test_a_tree_that_left_no_stubs_clears_the_post_s_old_ones(
    engine: Engine, subreddit_pk: int, now: int
) -> None:
    """A re-fetch that reached the whole tree must leave the post with no stubs at all.

    This is the case the shipped ``counters_equal_table_deltas`` invariant reads as a
    failure, because it asserts ``comment_more`` never decreases: a tree that becomes *more*
    complete decreases it. The narrowing of that clause is ruled and recorded (D-41); what
    this test pins is the write it is about.
    """
    post_pk = _seed_post(engine, "abc123", subreddit_pk, now, created=now - 86_400)
    with engine.begin() as conn:
        replace_comment_more(conn, post_pk=post_pk, stubs=[MoreWrite("t3_abc123", 12)])

    with engine.begin() as conn:
        written = replace_comment_more(conn, post_pk=post_pk, stubs=[])

    more = Base.metadata.tables["comment_more"]
    with engine.connect() as conn:
        left = conn.execute(select(more.c.pk).where(more.c.post_pk == post_pk)).all()
    assert written == 0
    assert left == []


def test_an_empty_batch_of_comments_writes_nothing(engine: Engine, now: int) -> None:
    """A tree stage that fetched a post with no comments still calls the write path."""
    comments = Base.metadata.tables["comments"]
    with engine.begin() as conn:
        outcome = upsert_comments(conn, [], now=now)

    with engine.connect() as conn:
        assert conn.execute(select(comments.c.pk)).all() == []
    assert outcome.new_ids == ()
    assert outcome.updated_ids == ()
    assert outcome.pks == {}


def test_the_tree_stamp_never_moves_first_seen_at_or_subreddit_pk(
    engine: Engine, subreddit_pk: int, now: int
) -> None:
    """The stamp owns the coverage and ladder columns of ``posts`` and nothing else.

    ``first_seen_at`` and ``subreddit_pk`` are the two the tree stage is in a position to
    corrupt: it holds a post it did not discover, and the refreshed post the tree fetch
    returns carries neither honestly.
    """
    post_pk = _seed_post(engine, "abc123", subreddit_pk, now, created=now - 86_400)
    posts = Base.metadata.tables["posts"]
    with engine.begin() as conn:
        stamp_tree_on_post(
            conn,
            post_pk=post_pk,
            stamp=TreeStamp(
                fetched_at=now + 60,
                captured=7,
                complete=False,
                more_skipped=True,
                more_skipped_count=2,
                more_skipped_reason="cap",
                next_check_at=now + 3 * 86_400,
                check_stage=1,
            ),
        )

    with engine.connect() as conn:
        row = conn.execute(posts.select().where(posts.c.pk == post_pk)).mappings().one()

    assert row["first_seen_at"] == now
    assert row["subreddit_pk"] == subreddit_pk
    assert row["created_utc"] == now - 86_400
    assert row["title"] == "a title"
    assert row["comments_fetched_at"] == now + 60
    assert row["comments_captured"] == 7
    assert row["comments_complete"] == 0
    assert row["more_skipped"] == 1
    assert row["more_skipped_count"] == 2
    assert row["more_skipped_reason"] == "cap"
    assert row["next_check_at"] == now + 3 * 86_400
    assert row["check_stage"] == 1
