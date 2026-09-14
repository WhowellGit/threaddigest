"""SW-05, DB-25/NM-02 and NM-01's sweep half: what one committed page actually writes
(design-round5.md §4.2, §4.3, §6.4, §13.1, §16).

``_prepare_page``'s unit-level shape (pure, no DB) lives here too, next to the behavioural
tests that prove the declaration in ``db/ownership.py`` describes reality.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select, update

from insightminer.db.schema import Base
from insightminer.services import sweep

BASE = 1_757_700_000  # matches tests/conftest.py's ``seeded`` fixture


def _reddit_id(fullname: str) -> str:
    """Strip the ``t3_``/``t1_`` prefix a ``fake.add_post``/``add_comment`` call returns."""
    return fullname.split("_", 1)[1]


# --- SW-05: the sweep never moves a guarded column on update -----------------------------------


def test_sweep_never_touches_first_seen_at_check_stage_next_check_at_or_scrubbed_at(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any, engine: Any
) -> None:
    """§4.3's behavioural half: sentinel the four guarded ``posts`` columns through a second
    connection, change the wire, sweep again, and prove only the changed columns moved."""
    fake.add_subreddit("premiere")
    fn = fake.add_post("premiere", title="original", created_utc=BASE, num_comments=1)
    source = add_source("premiere")
    sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    posts = Base.metadata.tables["posts"]
    reddit_id = _reddit_id(fn)
    with engine.begin() as conn:
        conn.execute(
            update(posts)
            .where(posts.c.reddit_id == reddit_id)
            .values(check_stage=7, next_check_at=1, first_seen_at=42, scrubbed_at=99)
        )

    fake.set_field(fn, "score", 999)
    fake.set_field(fn, "title", "changed")

    from insightminer.services import runs

    ctx2 = runs.start_run(
        engine, kind="run", trigger="cli", clock=run_context.clock, settings=run_context.settings
    )
    sweep.sweep_subreddit(ctx2, subreddit_row(source.pk), gateway=fake, notifier=notifier)

    with engine.connect() as conn:
        row = conn.execute(select(posts).where(posts.c.reddit_id == reddit_id)).mappings().one()
    assert row["score"] == 999
    assert row["title"] == "changed"
    assert row["check_stage"] == 7
    assert row["next_check_at"] == 1
    assert row["first_seen_at"] == 42
    assert row["scrubbed_at"] == 99


def test_authors_first_seen_at_is_insert_only_and_last_seen_at_never_goes_backward(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, subreddit_row: Any, engine: Any
) -> None:
    """§4.3's authors half: ``first_seen_at`` is insert-only; ``last_seen_at`` is monotonic
    (``max(authors.last_seen_at, excluded.last_seen_at)``), never a plain overwrite."""
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="one", author="u1", created_utc=BASE)
    source = add_source("premiere")
    sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    authors = Base.metadata.tables["authors"]
    future = 2_000_000_000  # past both the fake clock's `now` and any `created_utc` used below
    # The fake derives a t2_ fullname from a crc32 of the name, so the row is found by the
    # name it was written under rather than by a guessed literal.
    with engine.connect() as conn:
        fullname = conn.execute(
            select(authors.c.author_fullname).where(authors.c.name == "u1")
        ).scalar_one()
    with engine.begin() as conn:
        conn.execute(
            update(authors)
            .where(authors.c.author_fullname == fullname)
            .values(first_seen_at=42, last_seen_at=future)
        )

    fake.add_post("premiere", title="two", author="u1", created_utc=BASE + 60)

    from insightminer.services import runs

    ctx2 = runs.start_run(
        engine, kind="run", trigger="cli", clock=run_context.clock, settings=run_context.settings
    )
    sweep.sweep_subreddit(ctx2, subreddit_row(source.pk), gateway=fake, notifier=notifier)

    with engine.connect() as conn:
        row = (
            conn.execute(select(authors).where(authors.c.author_fullname == fullname))
            .mappings()
            .one()
        )
    assert row["first_seen_at"] == 42
    assert row["last_seen_at"] == future  # the new item's created_utc is OLDER; never moves back


# --- NM-01, sweep half: a malformed item costs a slot, never the page -----------------------


def test_a_malformed_item_is_rejected_and_the_page_still_commits(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, snapshot_tables: Any
) -> None:
    """A missing ``created_utc`` (planted at emit time, § 6.4.1's injection trap) becomes one
    ``raw_rejects`` row; the sibling post in the same page still commits."""
    fake.add_subreddit("premiere")
    good = fake.add_post("premiere", title="good", created_utc=BASE)
    bad_fn = fake.add_post("premiere", title="bad", created_utc=BASE + 60)
    bad_id = _reddit_id(bad_fn)
    fake.set_raw_shape(
        "post",
        lambda it, bad_id=bad_id: {
            k: v for k, v in it.items() if not (it.get("id") == bad_id and k == "created_utc")
        },
    )
    source = add_source("premiere")

    result = sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert result.new_items == 1  # only the sibling
    assert snapshot_tables(["raw_rejects", "posts"]) == {"raw_rejects": 1, "posts": 1}
    assert run_context.counters.rejects == 1
    posts = Base.metadata.tables["posts"]
    with run_context.engine.connect() as conn:
        stored = conn.execute(select(posts.c.reddit_id)).scalars().all()
    assert stored == [_reddit_id(good)]


def test_a_rejected_item_still_consumes_a_listing_slot(
    fake: Any, add_source: Any, run_context: Any
) -> None:
    """``plan_stop`` never sees a reject, so the loop pre-loads ``items_seen`` for it (§6.2):
    the reject occupies a listing slot but never enters ``seen_ids`` or the window."""
    fake.add_subreddit("premiere")
    good_ids = [
        fake.add_post("premiere", title=f"good {i}", created_utc=BASE + i * 60) for i in range(3)
    ]
    bad_fn = fake.add_post("premiere", title="bad", created_utc=BASE + 999 * 60)
    bad_id = _reddit_id(bad_fn)
    fake.set_raw_shape(
        "post",
        lambda it, bad_id=bad_id: {
            k: v for k, v in it.items() if not (it.get("id") == bad_id and k == "created_utc")
        },
    )
    source = add_source("premiere")

    outcome, exc = sweep._page_loop(run_context, source, gateway=fake)

    assert exc is None
    assert len(good_ids) == 3
    assert outcome.state.items_seen == 4  # 3 accepted rows + 1 reject, all consuming a slot
    assert outcome.state.unique_items == 3  # the reject never entered `seen_ids`


# --- DB-25 / NM-02, service half: unknown enum occurrences, counted once per post -----------


def test_unknown_enum_is_stored_raw_and_counted(
    fake: Any, add_source: Any, run_context: Any, notifier: Any
) -> None:
    fake.add_subreddit("premiere")
    fn = fake.add_post("premiere", title="mystery", created_utc=BASE, post_hint="mystery_hint")
    source = add_source("premiere")

    sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    reddit_id = _reddit_id(fn)
    assert run_context.unknown_enum_keys == {f"{reddit_id}|post_hint=mystery_hint"}
    posts = Base.metadata.tables["posts"]
    with run_context.engine.connect() as conn:
        stored = conn.execute(
            select(posts.c.post_hint).where(posts.c.reddit_id == reddit_id)
        ).scalar_one()
    assert stored == "mystery_hint"  # stored raw, never coerced


def test_overlapping_pages_count_one_unknown_occurrence(
    fake: Any, add_source: Any, run_context: Any, notifier: Any
) -> None:
    """Overlapping pages re-deliver the same post (SW-03); the occurrence set dedupes it so the
    counter is not doubled (§13.1)."""
    fake.add_subreddit("premiere")
    for i in range(150):
        kwargs: dict[str, Any] = {"post_hint": "mystery_hint"} if i == 50 else {}
        fake.add_post("premiere", title=f"post {i}", created_utc=BASE + i * 60, **kwargs)
    fake.set_overlap("premiere", n=1)  # repeats the last item of page 1 (post index 50) on page 2
    source = add_source("premiere")

    sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    unknown = {k for k in run_context.unknown_enum_keys if "post_hint=mystery_hint" in k}
    assert len(unknown) == 1


def test_a_deleted_author_contributes_no_authors_row(
    fake: Any, add_source: Any, run_context: Any, notifier: Any, snapshot_tables: Any
) -> None:
    """A post whose author Reddit shows as ``[deleted]`` carries neither a name nor a
    ``t2_`` fullname, so there is no identity to record: the post is written, the ``authors``
    table is untouched, and the row's ``author_state`` says why (``core.deletion`` rule 8)."""
    fake.add_subreddit("premiere")
    fake.add_post("premiere", title="orphan", author="[deleted]", created_utc=BASE)
    source = add_source("premiere")

    sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)

    assert snapshot_tables(["posts", "authors"]) == {"posts": 1, "authors": 0}
    posts = Base.metadata.tables["posts"]
    with run_context.engine.connect() as conn:
        row = conn.execute(select(posts)).mappings().one()
    assert row["author"] is None
    assert row["author_fullname"] is None
    assert row["author_state"] == "account_deleted"


def test_a_removal_seen_on_a_later_sweep_counts_one_scrub_transition(
    fake: Any,
    add_source: Any,
    run_context: Any,
    notifier: Any,
    subreddit_row: Any,
    engine: Any,
    clock: Any,
    settings: Any,
) -> None:
    """``core.deletion.Decision.scrub`` is a per-run EVENT count, not a second copy of a
    stored fact (§6.4.2, Q8): the transition INTO a scrub state bumps
    ``counters.scrubs_pending`` once, on the run that observed it.

    The removal is applied to the wire between two sweeps -- which is how a moderator removal
    really reaches the collector -- and the marker is stored raw, because redacting content is
    the M1c scrub service's job and tranche A never writes ``scrubbed_at``.
    """
    from insightminer.services import runs

    fake.add_subreddit("premiere")
    fn = fake.add_post("premiere", title="taken down", selftext="body", created_utc=BASE)
    source = add_source("premiere")
    sweep.sweep_subreddit(run_context, source, gateway=fake, notifier=notifier)
    assert run_context.counters.scrubs_pending == 0

    fake.set_field(fn, "selftext", "[removed]")
    fake.set_field(fn, "removed_by_category", "moderator")
    ctx2 = runs.start_run(engine, kind="run", trigger="cli", clock=clock, settings=settings)

    sweep.sweep_subreddit(ctx2, subreddit_row(source.pk), gateway=fake, notifier=notifier)

    assert ctx2.counters.scrubs_pending == 1
    posts = Base.metadata.tables["posts"]
    with engine.connect() as conn:
        row = conn.execute(select(posts)).mappings().one()
    assert row["content_state"] == "removed_by_moderator"
    assert row["removed_by_category"] == "moderator"  # stored raw, never coerced
    assert row["selftext"] == "[removed]"  # tranche A never redacts; scrubbed_at stays NULL
    assert row["scrubbed_at"] is None
