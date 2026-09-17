"""The only write path for the collector tables, plus the reads the services need.

``services/`` never builds SQL: every statement in this tranche is SQLAlchemy Core built
here, in ``db/backup.py`` or in ``db/migrate.py``. The statements are built from
``Base.metadata.tables[...]`` -- the head models -- so a column added without a migration
cannot be written, and so every function here is valid only against a database **at head**
(see :func:`finish_run` and :func:`insert_backup`).

Collector upserts are generated from ``db/ownership.py`` through one generator,
:func:`_upsert_for`, so the declaration governs the SQL for all three tables rather than
describing one of them (design-round5 §4.2). The repo returns plain dataclasses, never ORM
instances, so ``services/`` never holds a session.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from typing import Any, Final

from sqlalchemy import (
    Connection,
    RowMapping,
    Select,
    Table,
    case,
    delete,
    func,
    insert,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import Insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from threaddigest.core.digest import PostItem, rank_posts
from threaddigest.core.models import PostRow, Reject
from threaddigest.core.paging import KnownPost
from threaddigest.db.ownership import OWNERSHIP, IngestPath
from threaddigest.db.schema import Base

__all__ = [
    "FRESHNESS_STATUSES",
    "AuthorWrite",
    "BackupInsert",
    "PostWrite",
    "PriorPost",
    "RunDisplay",
    "RunInsert",
    "RunRow",
    "SnapshotWrite",
    "SubredditRow",
    "SweepProgress",
    "UpsertOutcome",
    "advance_watermark",
    "all_sources_for_freshness",
    "author_values",
    "backups_of_kind",
    "clear_subreddit_error",
    "default_workspace_pk",
    "delete_backups",
    "due_posts",
    "enabled_subreddits",
    "finish_run",
    "floor_population",
    "insert_item_snapshots",
    "insert_post_sources",
    "insert_rejects",
    "insert_run",
    "known_posts_in_window",
    "last_successful_run",
    "live_counts",
    "live_rows_missing",
    "mark_runs",
    "post_source_values",
    "post_values",
    "REDDIT_WEB_HOST",
    "posts_in_window",
    "prior_posts",
    "ranked_posts",
    "recent_runs",
    "recent_sweeping_runs",
    "recount_authors",
    "record_run_settings",
    "record_subreddit_failure",
    "rows_below_normalizer_version",
    "run_display",
    "run_for_window",
    "run_options",
    "running_runs",
    "seed_subreddits",
    "set_gap_suspected",
    "set_subreddit_identity",
    "source_outcomes",
    "stale_candidates",
    "stamp_complete_poll",
    "subreddit_names",
    "table_counts",
    "unknown_enum_occurrences",
    "upsert_authors",
    "upsert_posts",
    "upsert_run_subreddit",
    "workspaces",
]

#: Slug of the workspace every M1a command operates in.
DEFAULT_WORKSPACE_SLUG: Final = "premiere"

#: Where a stored permalink is rooted. ``posts.permalink`` holds the site-relative path Reddit's
#: API returns (``/r/premiere/comments/abc123/slug/``), which is the form the scrub clears and
#: the form the column's comment describes; joined to this host on the way out, in one place, so
#: no reader of a permalink can hand the digest a link that resolves against whatever server
#: rendered the page. A literal until M2, when the UI gains its own configuration and this
#: becomes a setting beside the bind address (PLAN § Web UI).
REDDIT_WEB_HOST: Final = "https://www.reddit.com"

#: Upstream enum columns of ``posts`` that are scanned for unknown values. ``subreddit_type``
#: is registered in ``core.models.KNOWN_VALUES`` but is a column of ``subreddits``, which
#: tranche A never writes, so naming it here would be invalid SQL (design-round5 §13.1).
UNKNOWN_ENUM_FIELDS: Final[tuple[str, ...]] = ("post_hint", "removed_by_category")

#: Run statuses that count as "this run swept something" for the freshness window
#: (design-round5 §14.2). Declared here because :func:`recent_sweeping_runs` is the query
#: that consumes it; ``services/invariants.py`` imports this name rather than restating it.
FRESHNESS_STATUSES: Final[frozenset[str]] = frozenset({
    "ok", "partial", "failed", "rate_limited", "network", "cancelled", "crashed",
})  # fmt: skip


# --- row-facing value types (design-round5 §5.1) --------------------------------------------


@dataclass(frozen=True, slots=True)
class SubredditRow:
    pk: int
    workspace_pk: int
    name_lower: str
    display_name: str
    subreddit_id: str | None
    enabled: bool
    status: str
    consecutive_failures: int
    watermark_created_utc: int | None
    last_complete_poll_at: int | None
    gap_suspected_at: int | None


@dataclass(frozen=True, slots=True)
class PriorPost:
    """The prior row's columns the sweep needs before deciding what to write."""

    pk: int
    first_seen_at: int
    content_state: str
    author_state: str
    misses: int
    score: int | None
    num_comments: int | None
    upvote_ratio: float | None


@dataclass(frozen=True, slots=True)
class PostWrite:
    """A normalized row plus everything the columns need that ``PostRow`` does not carry."""

    row: PostRow
    subreddit_pk: int
    first_seen_at: int
    last_fetched_at: int
    next_check_at: int
    check_stage: int
    content_state: str
    author_state: str
    misses: int
    raw_json: str


@dataclass(frozen=True, slots=True)
class SnapshotWrite:
    item_pk: int
    kind: str
    fetched_at: int
    score: int | None
    num_comments: int | None
    upvote_ratio: float | None


@dataclass(frozen=True, slots=True)
class AuthorWrite:
    author_fullname: str
    name: str
    seen_at: int


@dataclass(frozen=True, slots=True)
class UpsertOutcome:
    new_ids: tuple[str, ...]
    updated_ids: tuple[str, ...]
    pks: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class SweepProgress:
    """One ``run_subreddits`` row's payload, used at both grains (design-round5 §6.3)."""

    pages: int
    items_seen: int
    new_items: int
    updated_items: int
    stop_reason: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class RunInsert:
    kind: str
    trigger: str
    status: str
    created_at: int
    started_at: int | None
    pid: int | None
    stage: str | None
    options_json: str | None
    app_version: str | None
    praw_version: str | None
    schema_rev: str | None
    settings_fingerprint: str | None
    log_path: str | None


@dataclass(frozen=True, slots=True)
class RunRow:
    pk: int
    kind: str
    status: str
    created_at: int
    started_at: int | None
    finished_at: int | None
    heartbeat_at: int | None
    pid: int | None
    stage: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class RunDisplay:
    """Every ``runs`` column a surface *displays*, as opposed to the lifecycle columns
    :class:`RunRow` carries for the stale sweep.

    A separate type rather than a widened :class:`RunRow` because the two have different
    readers: the sweep must not be tempted to branch on a counter, and a page must not be
    handed a row missing the trigger, the budget or the violations it has to print. The JSON
    columns arrive as the raw strings the run wrote; ``services/runs_view.py`` parses them
    once for every reader, so no route or template ever calls ``json.loads``.
    """

    pk: int
    kind: str
    trigger: str
    status: str
    created_at: int
    started_at: int | None
    finished_at: int | None
    heartbeat_at: int | None
    pid: int | None
    stage: str | None
    options_json: str | None
    counters_json: str | None
    api_requests: int
    error: str | None
    violations_json: str | None
    settings_fingerprint: str | None
    app_version: str | None
    schema_rev: str | None


@dataclass(frozen=True, slots=True)
class BackupInsert:
    path: str
    sha256: str
    size_bytes: int
    integrity: str
    kind: str
    created_at: int
    schema_rev: str | None
    table_counts_json: str | None


# --- the one upsert generator (design-round5 §4.2) ------------------------------------------


def _table(name: str) -> Table:
    return Base.metadata.tables[name]


@cache
def _upsert_for(table: str, path: IngestPath) -> Insert:
    """The ONE statement generator. Everything DB-21 asserts is a property of this function.

    The emitted statement is a pure function of ``OWNERSHIP[(table, path)]``: the ``SET``
    clause of ``update_columns`` and ``monotonic_columns``, the ``ON CONFLICT`` target of
    ``conflict_columns``, and ``DO NOTHING`` of an empty ``update_columns``. Cached because
    a page compiles it once and executes it as an executemany over <= 100 rows.
    """
    own = OWNERSHIP[(table, path)]
    t = _table(table)
    stmt = sqlite_insert(t)
    index_elements = [t.c[name] for name in own.conflict_columns]
    if not own.update_columns:
        return stmt.on_conflict_do_nothing(index_elements=index_elements)
    set_ = {
        name: (
            func.max(t.c[name], stmt.excluded[name])
            if name in own.monotonic_columns
            else stmt.excluded[name]
        )
        for name in sorted(own.update_columns)
    }
    return stmt.on_conflict_do_update(index_elements=index_elements, set_=set_)


# --- writes (design-round5 §5.2) ------------------------------------------------------------


def post_values(write: PostWrite) -> dict[str, Any]:
    """The one mapping from ``PostRow`` + context to ``posts`` columns.

    ``crosspost_parent`` becomes the parent's ``t3_`` fullname or ``None`` (the parent's
    text is never stored); every NOT NULL column whose ``PostRow`` field is optional is
    coalesced to the column's server default; ``subreddit`` (the name) is not a column --
    ``subreddit_pk`` is; ``scrubbed_at`` is never emitted. The key set equals
    ``OWNERSHIP[("posts", path)].insert_columns``.
    """
    row = write.row
    parent = row.crosspost_parent
    return {
        "reddit_id": row.reddit_id,
        "fullname": row.fullname,
        "subreddit_pk": write.subreddit_pk,
        "subreddit_id": row.subreddit_id,
        "author": row.author,
        "author_fullname": row.author_fullname,
        "author_flair_text": row.author_flair_text,
        "author_is_bot": row.author_is_bot,
        "title": row.title,
        "selftext": row.selftext,
        "selftext_html": row.selftext_html,
        "url": row.url,
        "domain": row.domain,
        "permalink": row.permalink,
        "created_utc": row.created_utc,
        "edited_utc": row.edited_utc,
        "score": 0 if row.score is None else row.score,
        "upvote_ratio": row.upvote_ratio,
        "num_comments": 0 if row.num_comments is None else row.num_comments,
        "link_flair_text": row.link_flair_text,
        "over_18": bool(row.over_18),
        "spoiler": bool(row.spoiler),
        "is_self": bool(row.is_self),
        "is_video": bool(row.is_video),
        "is_gallery": bool(row.is_gallery),
        "post_hint": row.post_hint,
        "locked": bool(row.locked),
        "stickied": bool(row.stickied),
        "archived": bool(row.archived),
        "distinguished": row.distinguished,
        "crosspost_parent": None if parent is None else f"t3_{parent.id}",
        "num_crossposts": 0 if row.num_crossposts is None else row.num_crossposts,
        "removed_by_category": row.removed_by_category,
        "content_state": write.content_state,
        "author_state": write.author_state,
        "misses": write.misses,
        "first_seen_at": write.first_seen_at,
        "last_fetched_at": write.last_fetched_at,
        "comments_fetched_at": None,
        "comments_captured": 0,
        "comments_complete": False,
        "more_skipped": False,
        "more_skipped_count": 0,
        "more_skipped_reason": None,
        "next_check_at": write.next_check_at,
        "check_stage": write.check_stage,
        "source": row.source,
        "normalizer_version": row.normalizer_version,
        "raw_json": write.raw_json,
    }


def author_values(write: AuthorWrite) -> dict[str, Any]:
    """The one mapping from ``AuthorWrite`` to ``authors`` columns.

    ``seen_at`` fills both ``first_seen_at`` (insert-only) and ``last_seen_at`` (monotonic);
    ``post_count`` / ``comment_count`` are :func:`recount_authors`' derived columns and are
    never emitted here. The key set equals
    ``OWNERSHIP[("authors", IngestPath.SUBREDDIT_NEW)].insert_columns``, which
    ``tests/db/test_repo_ownership.py`` asserts -- a column added to one side and not the
    other is a red (panel P2-13).
    """
    return {
        "author_fullname": write.author_fullname,
        "name": write.name,
        "first_seen_at": write.seen_at,
        "last_seen_at": write.seen_at,
    }


def post_source_values(
    *, post_pk: int, source_type: str, source_pk: int, now: int
) -> dict[str, Any]:
    """The one mapping to ``post_sources`` columns; key set == that row's ``insert_columns``."""
    return {
        "post_pk": post_pk,
        "source_type": source_type,
        "source_pk": source_pk,
        "first_seen_at": now,
    }


def upsert_posts(
    conn: Connection, writes: Sequence[PostWrite], *, path: IngestPath
) -> UpsertOutcome:
    """Upsert one page of posts and report what was new, what was updated, and every pk.

    Three statements inside the caller's transaction: classify, upsert, read back the pks.
    Classification is a ``SELECT`` rather than ``RETURNING`` because SQLAlchemy will not
    combine ``RETURNING`` with an executemany upsert on pysqlite, and because relying on
    which rows an upsert "returns" is exactly the driver-specific semantics this project
    refuses (design-round5 §4.2 note 3).

    Duplicate ``reddit_id``s inside one batch are collapsed **before** execution, last write
    wins (Reddit returns the same post twice when items shift between pages, SW-03), which
    is what makes ``posts_new + posts_updated == len(distinct ids)`` hold.
    """
    collapsed: dict[str, PostWrite] = {write.row.reddit_id: write for write in writes}
    if not collapsed:
        return UpsertOutcome(new_ids=(), updated_ids=(), pks={})
    ids = list(collapsed)
    posts = _table("posts")

    preexisting = set(
        conn.execute(select(posts.c.reddit_id).where(posts.c.reddit_id.in_(ids))).scalars()
    )
    conn.execute(_upsert_for("posts", path), [post_values(w) for w in collapsed.values()])
    pks = {
        str(reddit_id): int(pk)
        for reddit_id, pk in conn.execute(
            select(posts.c.reddit_id, posts.c.pk).where(posts.c.reddit_id.in_(ids))
        ).all()
    }
    return UpsertOutcome(
        new_ids=tuple(i for i in ids if i not in preexisting),
        updated_ids=tuple(i for i in ids if i in preexisting),
        pks=pks,
    )


def insert_post_sources(
    conn: Connection,
    *,
    post_pks: Sequence[int],
    source_type: str,
    source_pk: int,
    now: int,
) -> int:
    """Record provenance for a page's posts; returns the rows actually added.

    ``INSERT ... ON CONFLICT(post_pk, source_type, source_pk) DO NOTHING``, so
    ``first_seen_at`` is genuinely first-seen per source. The count of new rows comes from a
    ``SELECT`` taken in the same transaction rather than from ``rowcount``, which pysqlite
    does not report reliably for an executemany.
    """
    wanted = list(dict.fromkeys(post_pks))
    if not wanted:
        return 0
    sources = _table("post_sources")
    already = conn.execute(
        select(func.count())
        .select_from(sources)
        .where(
            sources.c.post_pk.in_(wanted),
            sources.c.source_type == source_type,
            sources.c.source_pk == source_pk,
        )
    ).scalar_one()
    conn.execute(
        _upsert_for("post_sources", IngestPath.SUBREDDIT_NEW),
        [
            post_source_values(
                post_pk=post_pk, source_type=source_type, source_pk=source_pk, now=now
            )
            for post_pk in wanted
        ],
    )
    return len(wanted) - int(already)


def insert_item_snapshots(conn: Connection, snapshots: Sequence[SnapshotWrite]) -> int:
    """Append numeric-only history rows; returns the number inserted."""
    if not snapshots:
        return 0
    conn.execute(
        insert(_table("item_snapshots")),
        [
            {
                "item_pk": s.item_pk,
                "kind": s.kind,
                "fetched_at": s.fetched_at,
                "score": s.score,
                "num_comments": s.num_comments,
                "upvote_ratio": s.upvote_ratio,
            }
            for s in snapshots
        ],
    )
    return len(snapshots)


def upsert_authors(conn: Connection, authors: Sequence[AuthorWrite]) -> None:
    """Write author identity only: ``name`` moves, ``last_seen_at`` is monotonic.

    ``first_seen_at`` is insert-only and ``post_count`` / ``comment_count`` are the
    ``derived_columns`` :func:`recount_authors` owns -- this statement never touches them.
    """
    collapsed: dict[str, AuthorWrite] = {a.author_fullname: a for a in authors}
    if not collapsed:
        return
    conn.execute(
        _upsert_for("authors", IngestPath.SUBREDDIT_NEW),
        [author_values(a) for a in collapsed.values()],
    )


def recount_authors(conn: Connection, author_fullnames: Sequence[str]) -> None:
    """Recompute ``post_count`` / ``comment_count`` for the touched authors.

    Recompute, not increment: an increment drifts the moment a purge or a rerun-with-a-bug
    happens. One extra ``UPDATE`` per page over <= 100 authors, served by
    ``ix_posts_author_fullname`` / ``ix_comments_author_fullname`` (DB-08). This is the
    separate statement ``OWNERSHIP[("authors", ...)].derived_columns`` names, and DB-21
    rule 8 asserts its ``SET`` clause touches exactly those two columns.
    """
    wanted = list(dict.fromkeys(author_fullnames))
    if not wanted:
        return
    authors = _table("authors")
    posts = _table("posts")
    comments = _table("comments")
    post_count = (
        select(func.count())
        .select_from(posts)
        .where(posts.c.author_fullname == authors.c.author_fullname)
        .scalar_subquery()
    )
    comment_count = (
        select(func.count())
        .select_from(comments)
        .where(comments.c.author_fullname == authors.c.author_fullname)
        .scalar_subquery()
    )
    conn.execute(
        update(authors)
        .where(authors.c.author_fullname.in_(wanted))
        .values(post_count=post_count, comment_count=comment_count)
    )


def insert_rejects(conn: Connection, *, run_pk: int, rejects: Sequence[Reject], now: int) -> int:
    """Store the wire items ``core.normalize`` refused; returns the number stored."""
    if not rejects:
        return 0
    conn.execute(
        insert(_table("raw_rejects")),
        [
            {
                "run_pk": run_pk,
                "raw_json": json.dumps(r.raw, sort_keys=True, separators=(",", ":"), default=str),
                "error": r.error,
                "created_at": now,
            }
            for r in rejects
        ],
    )
    return len(rejects)


def upsert_run_subreddit(
    conn: Connection, *, run_pk: int, subreddit_pk: int, progress: SweepProgress
) -> None:
    """Write one ``run_subreddits`` row, at either grain (design-round5 §6.3).

    Called once per committed page with ``stop_reason=None`` (the progress a crash leaves
    behind) and once at the end of the subreddit with the final ``stop_reason`` / ``error``
    inside T6. The upsert on ``(run_pk, subreddit_pk)`` is what makes those two the same row.
    """
    run_subreddits = _table("run_subreddits")
    values = {
        "run_pk": run_pk,
        "subreddit_pk": subreddit_pk,
        "pages": progress.pages,
        "items_seen": progress.items_seen,
        "new_items": progress.new_items,
        "updated_items": progress.updated_items,
        "stop_reason": progress.stop_reason,
        "error": progress.error,
    }
    moving = ("pages", "items_seen", "new_items", "updated_items", "stop_reason", "error")
    stmt = sqlite_insert(run_subreddits).values(**values)
    conn.execute(
        stmt.on_conflict_do_update(
            index_elements=[run_subreddits.c.run_pk, run_subreddits.c.subreddit_pk],
            set_={name: stmt.excluded[name] for name in moving},
        )
    )


def set_subreddit_identity(conn: Connection, *, subreddit_pk: int, subreddit_id: str) -> None:
    """Adopt the listing's ``t5_`` identity for a source that had none."""
    subreddits = _table("subreddits")
    conn.execute(
        update(subreddits).where(subreddits.c.pk == subreddit_pk).values(subreddit_id=subreddit_id)
    )


def record_subreddit_failure(
    conn: Connection,
    *,
    subreddit_pk: int,
    status: str,
    error: str,
    now: int,
    disable_at: int | None,
) -> tuple[int, bool]:
    """Record one per-source failure and auto-disable in the same statement.

    Returns ``(consecutive_failures, disabled)`` after the write, so the caller decides on
    the alert without a read-modify-write race. ``disable_at=None`` means this status never
    auto-disables; ``disable_at=1`` disables on the first occurrence.

    ``now`` is accepted for symmetry with the other per-source writers; ``subreddits`` has
    no failure-timestamp column today, so nothing binds it.

    ``UPDATE ... RETURNING`` needs SQLite >= 3.35 (2021). If a target platform ever ships
    something older, the fallback is ``SELECT consecutive_failures, enabled FROM subreddits
    WHERE pk = :pk`` issued **in the same transaction** immediately after the ``UPDATE``,
    which is equally race-free: the whole call runs inside T6 and this process holds the
    collector flock.
    """
    del now
    subreddits = _table("subreddits")
    next_failures = subreddits.c.consecutive_failures + 1
    enabled = (
        subreddits.c.enabled
        if disable_at is None
        else case((next_failures >= disable_at, False), else_=subreddits.c.enabled)
    )
    row = conn.execute(
        update(subreddits)
        .where(subreddits.c.pk == subreddit_pk)
        .values(
            status=status,
            last_error=error,
            consecutive_failures=next_failures,
            enabled=enabled,
        )
        .returning(subreddits.c.consecutive_failures, subreddits.c.enabled)
    ).one()
    return int(row[0]), not bool(row[1])


def clear_subreddit_error(conn: Connection, *, subreddit_pk: int, now: int) -> None:
    """Clear the error trio after a healthy sweep.

    Sets ``status='ok'``, ``consecutive_failures=0`` and ``last_error=NULL``. It does **not**
    touch the watermark, ``last_complete_poll_at`` or ``gap_suspected_at``: those are
    :func:`advance_watermark`, :func:`stamp_complete_poll` and :func:`set_gap_suspected`,
    which fire on different events. ``now`` is accepted for call-site symmetry; no column
    records when the error was cleared.
    """
    del now
    subreddits = _table("subreddits")
    conn.execute(
        update(subreddits)
        .where(subreddits.c.pk == subreddit_pk)
        .values(status="ok", consecutive_failures=0, last_error=None)
    )


def advance_watermark(
    conn: Connection, *, subreddit_pk: int, seen_max_created_utc: int | None
) -> None:
    """Move ``watermark_created_utc`` forward, never backward and never to NULL.

    A no-op on ``seen_max_created_utc is None`` (an empty or sticky-only sweep): the
    statement is not issued at all, so a prior watermark survives intact.
    """
    if seen_max_created_utc is None:
        return
    subreddits = _table("subreddits")
    conn.execute(
        update(subreddits)
        .where(subreddits.c.pk == subreddit_pk)
        .values(
            watermark_created_utc=func.max(
                func.coalesce(subreddits.c.watermark_created_utc, seen_max_created_utc),
                seen_max_created_utc,
            )
        )
    )


def stamp_complete_poll(conn: Connection, *, subreddit_pk: int, at: int) -> None:
    """Record that this sweep reached known territory.

    Separate from :func:`advance_watermark` on purpose: two columns with two triggers and
    one writer each, so neither can be gated on the other's input by accident. The caller
    proves coverage; this function is simply not called when it was not.
    """
    subreddits = _table("subreddits")
    conn.execute(
        update(subreddits).where(subreddits.c.pk == subreddit_pk).values(last_complete_poll_at=at)
    )


def set_gap_suspected(conn: Connection, *, subreddit_pk: int, at: int | None) -> None:
    """Set or clear the standing gap latch (``at=None`` clears it)."""
    subreddits = _table("subreddits")
    conn.execute(
        update(subreddits).where(subreddits.c.pk == subreddit_pk).values(gap_suspected_at=at)
    )


def insert_run(conn: Connection, run: RunInsert) -> int:
    """Insert one ``runs`` row; returns its pk.

    **The one write here that may legitimately meet a database below head**, so it names
    only columns revision 0001 already has. ``db upgrade`` inserts its own run row *before*
    it migrates the file (§10.3), and ``cli``'s ``skipped_locked`` row is written while
    another process may be mid-migration. A column a later revision added therefore cannot
    be named here, however convenient: ``db upgrade`` would die inside this statement,
    before the backup it takes to make itself recoverable. :func:`record_run_settings`
    exists for exactly that reason, and
    ``tests/db/test_migrate_revisions.py::test_insert_run_and_touch_run_work_on_a_database_at_0001``
    is the control.
    """
    runs = _table("runs")
    pk = conn.execute(
        insert(runs)
        .values(
            kind=run.kind,
            trigger=run.trigger,
            status=run.status,
            created_at=run.created_at,
            started_at=run.started_at,
            pid=run.pid,
            stage=run.stage,
            options_json=run.options_json,
            app_version=run.app_version,
            praw_version=run.praw_version,
            schema_rev=run.schema_rev,
            settings_fingerprint=run.settings_fingerprint,
            log_path=run.log_path,
        )
        .returning(runs.c.pk)
    ).scalar_one()
    return int(pk)


def record_run_settings(conn: Connection, *, run_pk: int, settings_json: str) -> None:
    """Store the resolved non-secret settings on a run row (revision 0005).

    A second statement rather than two more columns on :func:`insert_run`, because the
    insert may meet a database below head and this column arrived at 0005: the caller
    (``services.runs.start_run``) issues it in the insert's own transaction when the
    database is at head, so a run row either carries its settings from the moment it exists
    or says NULL, never something in between. ``settings_fingerprint`` stays on the insert:
    it is a revision 0001 column and the two are derived from one serialization
    (``settings.settings_json``), so the hash on the row is the hash of these bytes.
    """
    runs = _table("runs")
    conn.execute(update(runs).where(runs.c.pk == run_pk).values(settings_json=settings_json))


def touch_run(
    conn: Connection,
    *,
    run_pk: int,
    heartbeat_at: int,
    stage: str | None,
    warnings_json: str | None,
) -> None:
    """Write the heartbeat, the current stage and the warnings recorded so far.

    The warnings ride on the heartbeat rather than on a statement of their own because the
    heartbeat is already the one write that happens *during* a run: a run killed between two
    beats then leaves behind every warning it had recorded by the last one, instead of
    leaving a counter with nothing behind it.

    ``warnings_json=None`` never names the column at all, which is what keeps this callable
    against a database below head -- ``db upgrade`` beats ``upgrade:backup`` onto its row
    before it migrates the file. It also means a caller with nothing to flush cannot erase
    what an earlier beat wrote.
    """
    runs = _table("runs")
    values: dict[str, object] = {"heartbeat_at": heartbeat_at, "stage": stage}
    if warnings_json is not None:
        values["warnings_json"] = warnings_json
    conn.execute(update(runs).where(runs.c.pk == run_pk).values(**values))


def finish_run(
    conn: Connection,
    *,
    run_pk: int,
    status: str,
    finished_at: int,
    counters_json: str,
    api_requests: int,
    error: str | None,
    violations_json: str | None,
    warnings_json: str | None,
) -> None:
    """Close the run row.

    **Never called against a database below head.** Every statement in this module is built
    from the head models, so this one names ``violations_json`` -- a column revision 0002
    added. Against an older file it raises ``OperationalError: no such column``. A code path
    that writes to a database it has not just migrated to head goes through
    ``db.migrate.finish_restored_run`` instead (design-round5 §5.2, §10.3 T12).
    """
    runs = _table("runs")
    conn.execute(
        update(runs)
        .where(runs.c.pk == run_pk)
        .values(
            status=status,
            finished_at=finished_at,
            counters_json=counters_json,
            api_requests=api_requests,
            error=error,
            violations_json=violations_json,
            warnings_json=warnings_json,
        )
    )


def mark_runs(
    conn: Connection, *, pks: Sequence[int], status: str, finished_at: int, error: str
) -> None:
    """Stamp a terminal status on rows the stale sweep condemned."""
    if not pks:
        return
    runs = _table("runs")
    conn.execute(
        update(runs)
        .where(runs.c.pk.in_(list(pks)))
        .values(status=status, finished_at=finished_at, error=error)
    )


def insert_backup(conn: Connection, backup: BackupInsert) -> int:
    """Insert one ``backups`` row; returns its pk.

    **Never called against a database below head**, for the reason :func:`finish_run`
    documents: the restored-file bookkeeping uses ``db.migrate.finish_restored_run``.
    """
    backups = _table("backups")
    pk = conn.execute(
        insert(backups)
        .values(
            path=backup.path,
            sha256=backup.sha256,
            size_bytes=backup.size_bytes,
            integrity=backup.integrity,
            kind=backup.kind,
            created_at=backup.created_at,
            schema_rev=backup.schema_rev,
            table_counts_json=backup.table_counts_json,
        )
        .returning(backups.c.pk)
    ).scalar_one()
    return int(pk)


def backups_of_kind(conn: Connection, kind: str) -> list[tuple[int, str, int]]:
    """``(pk, path, created_at)`` for one backup kind, newest first."""
    backups = _table("backups")
    rows = conn.execute(
        select(backups.c.pk, backups.c.path, backups.c.created_at)
        .where(backups.c.kind == kind)
        .order_by(backups.c.created_at.desc(), backups.c.pk.desc())
    ).all()
    return [(int(pk), str(path), int(created_at)) for pk, path, created_at in rows]


def delete_backups(conn: Connection, pks: Sequence[int]) -> None:
    """Delete ``backups`` rows by pk (the caller removes the files)."""
    if not pks:
        return
    backups = _table("backups")
    conn.execute(delete(backups).where(backups.c.pk.in_(list(pks))))


def seed_subreddits(conn: Connection, *, workspace_pk: int, names: Sequence[str], now: int) -> int:
    """Idempotently add sources to a workspace; returns the rows actually added."""
    wanted = list(dict.fromkeys(name.lower() for name in names))
    if not wanted:
        return 0
    subreddits = _table("subreddits")
    already = conn.execute(
        select(func.count())
        .select_from(subreddits)
        .where(subreddits.c.workspace_pk == workspace_pk, subreddits.c.name_lower.in_(wanted))
    ).scalar_one()
    stmt = sqlite_insert(subreddits)
    conn.execute(
        stmt.on_conflict_do_nothing(
            index_elements=[subreddits.c.workspace_pk, subreddits.c.name_lower]
        ),
        [
            {
                "workspace_pk": workspace_pk,
                "name_lower": name,
                "display_name": name,
                "added_at": now,
            }
            for name in wanted
        ],
    )
    return len(wanted) - int(already)


# --- reads (design-round5 §5.3) -------------------------------------------------------------


def _subreddit_row(mapping: RowMapping) -> SubredditRow:
    return SubredditRow(
        pk=int(mapping["pk"]),
        workspace_pk=int(mapping["workspace_pk"]),
        name_lower=str(mapping["name_lower"]),
        display_name=str(mapping["display_name"]),
        subreddit_id=mapping["subreddit_id"],
        enabled=bool(mapping["enabled"]),
        status=str(mapping["status"]),
        consecutive_failures=int(mapping["consecutive_failures"]),
        watermark_created_utc=mapping["watermark_created_utc"],
        last_complete_poll_at=mapping["last_complete_poll_at"],
        gap_suspected_at=mapping["gap_suspected_at"],
    )


def _run_row(mapping: RowMapping) -> RunRow:
    return RunRow(
        pk=int(mapping["pk"]),
        kind=str(mapping["kind"]),
        status=str(mapping["status"]),
        created_at=int(mapping["created_at"]),
        started_at=mapping["started_at"],
        finished_at=mapping["finished_at"],
        heartbeat_at=mapping["heartbeat_at"],
        pid=mapping["pid"],
        stage=mapping["stage"],
        error=mapping["error"],
    )


def default_workspace_pk(conn: Connection) -> int:
    """The pk of the default workspace; raises when the seed row is absent."""
    workspaces = _table("workspaces")
    return int(
        conn.execute(
            select(workspaces.c.pk).where(workspaces.c.slug == DEFAULT_WORKSPACE_SLUG)
        ).scalar_one()
    )


def enabled_subreddits(conn: Connection, workspace_pk: int) -> list[SubredditRow]:
    """Sources the collector polls, ordered by ``name_lower``."""
    subreddits = _table("subreddits")
    rows = conn.execute(
        select(subreddits)
        .where(subreddits.c.workspace_pk == workspace_pk, subreddits.c.enabled.is_(True))
        .order_by(subreddits.c.name_lower)
    ).mappings()
    return [_subreddit_row(row) for row in rows]


#: Statuses of an enabled source that will never yield data until an operator acts: a private
#: (forbidden) or missing (not_found) subreddit is swept every run and fails every time. A
#: source in one of these is enabled but not *collectable*; ``ok`` and the transient ``error``
#: are collectable (external round one panel, 2026-09-15, KI-017 forbidden-enabled gap).
UNCOLLECTABLE_STATUSES: Final[frozenset[str]] = frozenset({"forbidden", "not_found"})


def source_counts(conn: Connection, workspace_pk: int) -> tuple[int, int, int]:
    """``(configured, enabled, collectable)`` sources of the workspace, for ``doctor`` (KI-017).

    ``collectable`` counts enabled sources whose status is not one a run can never collect
    from (``forbidden`` / ``not_found``), so a workspace whose every enabled source is private
    or gone is caught even though ``enabled > 0``.
    """
    subreddits = _table("subreddits")
    total = conn.execute(
        select(func.count())
        .select_from(subreddits)
        .where(subreddits.c.workspace_pk == workspace_pk)
    ).scalar_one()
    enabled = conn.execute(
        select(func.count())
        .select_from(subreddits)
        .where(subreddits.c.workspace_pk == workspace_pk, subreddits.c.enabled.is_(True))
    ).scalar_one()
    collectable = conn.execute(
        select(func.count())
        .select_from(subreddits)
        .where(
            subreddits.c.workspace_pk == workspace_pk,
            subreddits.c.enabled.is_(True),
            subreddits.c.status.notin_(tuple(UNCOLLECTABLE_STATUSES)),
        )
    ).scalar_one()
    return int(total), int(enabled), int(collectable)


def all_sources_for_freshness(conn: Connection, workspace_pk: int) -> list[SubredditRow]:
    """Enabled sources **plus** sources disabled by an error status.

    A subreddit that was auto-disabled by a failure does not quietly leave the freshness
    population (ingest B8); one the operator muted by hand, with ``status='ok'``, does.
    """
    subreddits = _table("subreddits")
    rows = conn.execute(
        select(subreddits)
        .where(
            subreddits.c.workspace_pk == workspace_pk,
            (subreddits.c.enabled.is_(True)) | (subreddits.c.status != "ok"),
        )
        .order_by(subreddits.c.name_lower)
    ).mappings()
    return [_subreddit_row(row) for row in rows]


def prior_posts(conn: Connection, reddit_ids: Sequence[str]) -> dict[str, PriorPost]:
    """The columns the sweep needs about posts it is about to write, keyed by ``reddit_id``."""
    wanted = list(dict.fromkeys(reddit_ids))
    if not wanted:
        return {}
    posts = _table("posts")
    rows = conn.execute(
        select(
            posts.c.reddit_id,
            posts.c.pk,
            posts.c.first_seen_at,
            posts.c.content_state,
            posts.c.author_state,
            posts.c.misses,
            posts.c.score,
            posts.c.num_comments,
            posts.c.upvote_ratio,
        ).where(posts.c.reddit_id.in_(wanted))
    ).mappings()
    return {
        str(row["reddit_id"]): PriorPost(
            pk=int(row["pk"]),
            first_seen_at=int(row["first_seen_at"]),
            content_state=str(row["content_state"]),
            author_state=str(row["author_state"]),
            misses=int(row["misses"]),
            score=row["score"],
            num_comments=row["num_comments"],
            upvote_ratio=row["upvote_ratio"],
        )
        for row in rows
    }


def known_posts_in_window(
    conn: Connection, *, subreddit_pk: int, since_created_utc: int
) -> list[KnownPost]:
    """Posts already stored for one source inside the sweep's window.

    Served by ``ix_posts_subreddit_pk_created_utc`` (DB-08).
    """
    posts = _table("posts")
    rows = conn.execute(
        select(posts.c.reddit_id, posts.c.created_utc, posts.c.stickied).where(
            posts.c.subreddit_pk == subreddit_pk,
            posts.c.created_utc >= since_created_utc,
        )
    ).all()
    return [
        KnownPost(reddit_id=str(reddit_id), created_utc=int(created_utc), stickied=bool(stickied))
        for reddit_id, created_utc, stickied in rows
    ]


def due_posts(conn: Connection, *, now: int, limit: int) -> list[tuple[int, str]]:
    """``(pk, reddit_id)`` for the posts the revisit ladder makes due, most overdue first.

    The ``ORDER BY next_check_at`` is load-bearing as well as useful: it is what makes
    SQLite serve the read from ``ix_posts_next_check_at`` (DB-08). M1b is the consumer.
    """
    posts = _table("posts")
    rows = conn.execute(
        select(posts.c.pk, posts.c.reddit_id)
        .where(posts.c.next_check_at <= now)
        .order_by(posts.c.next_check_at)
        .limit(limit)
    ).all()
    return [(int(pk), str(reddit_id)) for pk, reddit_id in rows]


def table_counts(conn: Connection, tables: Sequence[str]) -> dict[str, int]:
    """One ``SELECT count(*)`` per named table, for the DB-54 baseline and the deltas."""
    return {
        name: int(conn.execute(select(func.count()).select_from(_table(name))).scalar_one())
        for name in tables
    }


def running_runs(conn: Connection, *, exclude_pk: int) -> list[RunRow]:
    """Every ``running`` run row except one -- the ``no_other_running_rows`` invariant's read."""
    runs = _table("runs")
    rows = conn.execute(
        select(runs).where(runs.c.status == "running", runs.c.pk != exclude_pk).order_by(runs.c.pk)
    ).mappings()
    return [_run_row(row) for row in rows]


def stale_candidates(
    conn: Connection, *, now: int, stale_after_seconds: int
) -> tuple[list[RunRow], list[int]]:
    """Rows the stale sweep must judge: every ``running`` row, plus orphan ``queued`` pks.

    The ``running`` half is deliberately unfiltered. Three of § 12.2's four clauses
    (``pid IS NULL``, ``not pid_alive(pid)``, ``pid == this_pid``) are decided in Python
    against a live process table, so a SQL staleness filter would hide exactly the rows the
    sweep must condemn -- a fresh heartbeat from a dead pid is the common crash shape.
    ``stale_after_seconds`` therefore bounds the ``queued`` half only: an orphan is a
    ``queued`` row with no pid that has sat there longer than the grace the caller passes.
    """
    runs = _table("runs")
    running = conn.execute(
        select(runs).where(runs.c.status == "running").order_by(runs.c.pk)
    ).mappings()
    orphans = conn.execute(
        select(runs.c.pk)
        .where(
            runs.c.status == "queued",
            runs.c.pid.is_(None),
            runs.c.created_at < now - stale_after_seconds,
        )
        .order_by(runs.c.pk)
    ).scalars()
    return [_run_row(row) for row in running], [int(pk) for pk in orphans]


def run_options(conn: Connection, kind: str = "run") -> list[str | None]:
    """Every run row's ``options_json`` for one ``kind``, oldest first.

    The read behind ``cli``'s content-based ``--gateway fake`` guard (§11.3 step 2): the only
    record of which gateway wrote a row is the ``gateway`` key ``cli._options_json`` puts in
    ``options_json``, so the guard needs the raw strings and decides for itself. ``NULL`` is
    kept rather than filtered: a ``skipped_locked`` row has no options and also wrote no data,
    and the caller is the layer that knows that.
    """
    runs = _table("runs")
    rows = conn.execute(
        select(runs.c.options_json).where(runs.c.kind == kind).order_by(runs.c.pk)
    ).scalars()
    return [None if row is None else str(row) for row in rows]


def last_successful_run(conn: Connection, kind: str = "run") -> RunRow | None:
    """The newest ``ok`` run of one kind, or ``None``."""
    runs = _table("runs")
    row = (
        conn.execute(
            select(runs)
            .where(runs.c.kind == kind, runs.c.status == "ok")
            .order_by(runs.c.pk.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return None if row is None else _run_row(row)


def recent_sweeping_runs(conn: Connection, *, current_run_pk: int, limit: int) -> list[int]:
    """Run pks in the freshness window, newest first (design-round5 §14.2).

    The ``EXISTS`` clause is self-maintaining: every kind of run that writes a ``runs`` row
    but sweeps nothing -- ``skipped_locked``, a run aborted at the auth preflight, a network
    outage -- is excluded by construction, with no status list to keep in sync.

    The window *ends* at ``current_run_pk``: it is the newest ``runs`` row by construction
    while the invariants run (the row was inserted by this process, which holds the
    collector flock), so the clause changes nothing for ``per_source_freshness``. It is what
    makes the read usable after the fact, by the digest of an older run, which must not be
    handed runs that had not happened yet.
    """
    runs = _table("runs")
    run_subreddits = _table("run_subreddits")
    swept = select(run_subreddits.c.pk).where(run_subreddits.c.run_pk == runs.c.pk).exists()
    rows = conn.execute(
        select(runs.c.pk)
        .where(
            runs.c.kind == "run",
            swept,
            runs.c.pk <= current_run_pk,
            (runs.c.pk == current_run_pk) | (runs.c.status.in_(sorted(FRESHNESS_STATUSES))),
        )
        .order_by(runs.c.pk.desc())
        .limit(limit)
    ).scalars()
    return [int(pk) for pk in rows]


def source_outcomes(
    conn: Connection, *, run_pks: Sequence[int]
) -> dict[int, dict[int, SweepProgress]]:
    """``run_pk -> subreddit_pk -> SweepProgress`` for the freshness window."""
    wanted = list(dict.fromkeys(run_pks))
    if not wanted:
        return {}
    run_subreddits = _table("run_subreddits")
    rows = conn.execute(
        select(run_subreddits).where(run_subreddits.c.run_pk.in_(wanted))
    ).mappings()
    outcomes: dict[int, dict[int, SweepProgress]] = {pk: {} for pk in wanted}
    for row in rows:
        outcomes[int(row["run_pk"])][int(row["subreddit_pk"])] = SweepProgress(
            pages=int(row["pages"]),
            items_seen=int(row["items_seen"]),
            new_items=int(row["new_items"]),
            updated_items=int(row["updated_items"]),
            stop_reason=row["stop_reason"],
            error=row["error"],
        )
    return outcomes


def _floor_population_stmt(*, since: int, normalizer_version: int) -> Select[tuple[int]]:
    """``count(*)`` over the population the floors evaluate: live, known-author posts
    written this run at this normalizer version (design-round5 §14.2).

    One builder for both halves of the floor, so the population :func:`floor_population`
    measures and the population :func:`live_rows_missing` looks for NULLs in cannot drift
    apart -- which is the whole point of DB-51's "an empty population fails".
    """
    posts = _table("posts")
    return (
        select(func.count())
        .select_from(posts)
        .where(
            posts.c.content_state == "live",
            posts.c.author_state == "known",
            posts.c.normalizer_version == normalizer_version,
            posts.c.last_fetched_at >= since,
        )
    )


def live_rows_missing(conn: Connection, *, column: str, since: int, normalizer_version: int) -> int:
    """Live, known-author posts written since ``since`` that carry NULL in ``column``.

    The column name is validated against the model before it reaches the statement, so it
    can never carry caller text into SQL. ``selftext_html`` is additionally scoped to
    ``is_self = 1 AND selftext <> ''``: an empty body renders to NULL by design.
    """
    posts = _table("posts")
    if column not in posts.c:
        msg = f"{column!r} is not a column of posts"
        raise ValueError(msg)
    target = posts.c[column]
    stmt = _floor_population_stmt(since=since, normalizer_version=normalizer_version).where(
        target.is_(None)
    )
    if column == "selftext_html":
        stmt = stmt.where(posts.c.is_self.is_(True), posts.c.selftext != "")
    return int(conn.execute(stmt).scalar_one())


def floor_population(conn: Connection, *, since: int, normalizer_version: int) -> int:
    """How many rows :func:`live_rows_missing` evaluates over, with no column named.

    DB-51's clause (b): a floor that evaluates over zero rows is inert, so
    ``population_floors_hold`` needs the population's size as well as its NULL count
    (design-round5 §14.2). §5.3 lists no such read -- ``live_rows_missing`` answers only
    "how many are NULL" -- and ``services/`` may not build SQL (§1), so the query lives here
    next to the predicate it shares.
    """
    return int(
        conn.execute(
            _floor_population_stmt(since=since, normalizer_version=normalizer_version)
        ).scalar_one()
    )


def rows_below_normalizer_version(conn: Connection, *, table: str, since: int, version: int) -> int:
    """Rows written since ``since`` that a later normalizer would render differently."""
    if table not in {"posts", "comments"}:
        msg = f"{table!r} carries no normalizer_version"
        raise ValueError(msg)
    t = _table(table)
    return int(
        conn.execute(
            select(func.count())
            .select_from(t)
            .where(t.c.last_fetched_at >= since, t.c.normalizer_version < version)
        ).scalar_one()
    )


def unknown_enum_occurrences(
    conn: Connection,
    *,
    since: int,
    known: Mapping[str, frozenset[str]],
    until: int | None = None,
) -> list[str]:
    """``"<reddit_id>|<field>=<value>"`` per unknown enum occurrence written this run.

    One entry per ``(reddit_id, field, value)`` triple where ``value`` is non-NULL and
    outside the known set for that field, over the distinct posts written in the window.
    The field set is exactly ``UNKNOWN_ENUM_FIELDS``.

    ``until`` closes the window at the top. The invariant leaves it open, because it runs
    while the run it measures is the last thing that wrote anything; the digest passes the
    run's ``finished_at``, because a report assembled for an older run must not count the
    rows a *later* run wrote into that run's section (§14.1's window, read after the fact).
    """
    posts = _table("posts")
    found: list[str] = []
    for field in UNKNOWN_ENUM_FIELDS:
        column = posts.c[field]
        stmt = select(posts.c.reddit_id, column).where(
            posts.c.last_fetched_at >= since,
            column.is_not(None),
            column.notin_(sorted(known[field])),
        )
        if until is not None:
            stmt = stmt.where(posts.c.last_fetched_at <= until)
        found.extend(
            f"{reddit_id}|{field}={value}" for reddit_id, value in conn.execute(stmt).all()
        )
    return found


def live_counts(conn: Connection) -> dict[str, int]:
    """``posts_live`` / ``comments_live`` row counts, in one statement.

    One statement rather than two so the ``posts`` half is served by
    ``ix_posts_content_state`` in the same plan DB-08 inspects; ``comments`` has no
    ``content_state`` index today and scans.
    """
    posts = _table("posts")
    comments = _table("comments")
    posts_live = (
        select(func.count()).select_from(posts).where(posts.c.content_state == "live")
    ).scalar_subquery()
    comments_live = (
        select(func.count()).select_from(comments).where(comments.c.content_state == "live")
    ).scalar_subquery()
    row = conn.execute(
        select(posts_live.label("posts_live"), comments_live.label("comments_live"))
    ).one()
    return {"posts_live": int(row[0]), "comments_live": int(row[1])}


# --- display reads: the Runs page and the digest (DB-63, the first web slice) ---------------


def _run_display(mapping: RowMapping) -> RunDisplay:
    return RunDisplay(
        pk=int(mapping["pk"]),
        kind=str(mapping["kind"]),
        trigger=str(mapping["trigger"]),
        status=str(mapping["status"]),
        created_at=int(mapping["created_at"]),
        started_at=mapping["started_at"],
        finished_at=mapping["finished_at"],
        heartbeat_at=mapping["heartbeat_at"],
        pid=mapping["pid"],
        stage=mapping["stage"],
        options_json=mapping["options_json"],
        counters_json=mapping["counters_json"],
        api_requests=int(mapping["api_requests"]),
        error=mapping["error"],
        violations_json=mapping["violations_json"],
        settings_fingerprint=mapping["settings_fingerprint"],
        app_version=mapping["app_version"],
        schema_rev=mapping["schema_rev"],
    )


def recent_runs(
    conn: Connection, *, limit: int, before_pk: int | None = None, kind: str | None = None
) -> list[RunDisplay]:
    """One page of run rows, newest first: the Runs page's list read.

    ``before_pk`` is the page cursor and is **strictly** exclusive, so "load more" can never
    repeat the row it paged from; the pk is the cursor rather than a timestamp because two
    runs can share a second and a pk cannot. ``kind`` narrows to one command (the digest asks
    for ``run``); the page itself passes nothing, because an operator reading history wants
    the ``doctor`` and ``migrate`` rows in it too.
    """
    runs = _table("runs")
    stmt = select(runs).order_by(runs.c.pk.desc()).limit(limit)
    if before_pk is not None:
        stmt = stmt.where(runs.c.pk < before_pk)
    if kind is not None:
        stmt = stmt.where(runs.c.kind == kind)
    return [_run_display(row) for row in conn.execute(stmt).mappings()]


def run_display(conn: Connection, *, run_pk: int) -> RunDisplay | None:
    """One run row by pk, or ``None`` -- which the route turns into a 404."""
    runs = _table("runs")
    row = conn.execute(select(runs).where(runs.c.pk == run_pk)).mappings().first()
    return None if row is None else _run_display(row)


def run_for_window(
    conn: Connection, *, start_utc: int, end_utc: int, kind: str = "run"
) -> RunDisplay | None:
    """The newest **finished** run of ``kind`` that started inside ``[start_utc, end_utc)``.

    Two choices are made here rather than in the caller, because both are properties of the
    query and a caller handed a single row could not undo them:

    * A run belongs to the day it **started**, from ``coalesce(started_at, created_at)``: a
      sweep that begins at 23:50 and ends after midnight is one evening's run, not two days'.
      The window is half-open so consecutive local days tile without an overlap.
    * Only a finished run has a report. A run still in flight has no terminal status, no
      counters and no invariant verdict, so a digest of it would be a page of NULLs; the Runs
      page is where a run in flight is read.
    """
    runs = _table("runs")
    anchor = func.coalesce(runs.c.started_at, runs.c.created_at)
    row = (
        conn.execute(
            select(runs)
            .where(
                runs.c.kind == kind,
                runs.c.finished_at.is_not(None),
                anchor >= start_utc,
                anchor < end_utc,
            )
            .order_by(runs.c.pk.desc())
            .limit(1)
        )
        .mappings()
        .first()
    )
    return None if row is None else _run_display(row)


def subreddit_names(conn: Connection, *, pks: Sequence[int]) -> dict[int, str]:
    """``subreddit_pk -> display_name`` for the per-source rows of a run.

    Reddit's own capitalisation, because that is what an operator sees on the site; the
    lower-cased name is the identity and never the label.
    """
    wanted = list(dict.fromkeys(pks))
    if not wanted:
        return {}
    subreddits = _table("subreddits")
    rows = conn.execute(
        select(subreddits.c.pk, subreddits.c.display_name).where(subreddits.c.pk.in_(wanted))
    ).all()
    return {int(pk): str(display_name) for pk, display_name in rows}


def workspaces(conn: Connection) -> list[tuple[int, str, str]]:
    """``(pk, slug, name)`` for every workspace, ordered by slug."""
    table = _table("workspaces")
    rows = conn.execute(select(table.c.pk, table.c.slug, table.c.name).order_by(table.c.slug)).all()
    return [(int(pk), str(slug), str(name)) for pk, slug, name in rows]


def _post_window_stmt(*, workspace_pk: int, since_created_utc: int) -> Select[tuple[int]]:
    """The digest's post window: live, linkable posts of one workspace created since a point.

    One builder for both the ranked list and its denominator, because "show the denominator"
    is only true if the population counted is the population listed. A post with no
    ``permalink`` is excluded from both halves together: a scrubbed row has no link and no
    title, so it can be neither shown nor named, and a *live* row without one is a population
    floor violation the run already reports (DB-50).
    """
    posts = _table("posts")
    subreddits = _table("subreddits")
    return (
        select(posts.c.pk)
        .select_from(posts.join(subreddits, posts.c.subreddit_pk == subreddits.c.pk))
        .where(
            subreddits.c.workspace_pk == workspace_pk,
            posts.c.content_state == "live",
            posts.c.permalink.is_not(None),
            posts.c.created_utc >= since_created_utc,
        )
    )


def posts_in_window(conn: Connection, *, workspace_pk: int, since_created_utc: int) -> int:
    """How many posts :func:`ranked_posts` ranks over, with no ranking and no limit.

    The denominator of every digest count whose population is "posts in the window": the
    ranked list is capped at its top N, so its length can never be the population.
    """
    stmt = _post_window_stmt(workspace_pk=workspace_pk, since_created_utc=since_created_utc)
    return int(conn.execute(stmt.with_only_columns(func.count())).scalar_one())


def ranked_posts(
    conn: Connection, *, workspace_pk: int, since_created_utc: int, limit: int
) -> list[PostItem]:
    """The window's posts ordered by :func:`core.digest.rank_posts`, capped at ``limit``.

    The ordering is **never** a SQL ``ORDER BY`` on the ranking keys: one ranking function is
    shared by the digest, the theme pages and the export (D-09), so a second spelling of it
    in SQL is a second answer waiting to disagree. ``limit`` is therefore applied after the
    ranking, in Python; the database's bound is the window, which is what keeps the read
    finite.

    ``distinct_author_count`` counts the **distinct live comment authors** of the post by
    ``author_fullname``, with NULL identities excluded rather than collapsed into one bucket
    (D-09). No comment tree is captured before M1b, so today it is zero for every post and
    the ranking falls through to comment count and score: the digest is thin, not wrong. The
    post's own author is deliberately not counted -- the section asks how many people are
    *discussing* a post, and the author is its subject.

    ``permalink`` comes back rooted at :data:`REDDIT_WEB_HOST`. The column holds the
    site-relative path Reddit's API returns, so a digest that rendered it unchanged produced a
    link resolving against whatever server served the page rather than against Reddit
    (KI-036). The host is joined on here, once, rather than in each of the three renderings,
    because :class:`core.digest.PostItem` is what the model carries and a link is the one
    thing that list is for; the stored column is left as the collector wrote it, which is what
    the scrub clears and what a re-upsert compares.
    """
    posts = _table("posts")
    subreddits = _table("subreddits")
    comments = _table("comments")
    distinct_authors = (
        select(func.count(func.distinct(comments.c.author_fullname)))
        .where(
            comments.c.post_pk == posts.c.pk,
            comments.c.content_state == "live",
            comments.c.author_fullname.is_not(None),
        )
        .scalar_subquery()
    )
    stmt = _post_window_stmt(
        workspace_pk=workspace_pk, since_created_utc=since_created_utc
    ).with_only_columns(
        posts.c.reddit_id,
        posts.c.title,
        posts.c.permalink,
        subreddits.c.display_name,
        distinct_authors.label("distinct_author_count"),
        posts.c.num_comments,
        posts.c.score,
        posts.c.created_utc,
    )
    items = [
        PostItem(
            post_id=str(row["reddit_id"]),
            title="" if row["title"] is None else str(row["title"]),
            permalink=f"{REDDIT_WEB_HOST}{row['permalink']}",
            subreddit=str(row["display_name"]),
            distinct_author_count=int(row["distinct_author_count"]),
            comment_count=int(row["num_comments"]),
            score=int(row["score"]),
            created_utc=int(row["created_utc"]),
        )
        for row in conn.execute(stmt).mappings()
    ]
    return rank_posts(items)[:limit]
