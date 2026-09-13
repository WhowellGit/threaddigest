"""The field-ownership table, declared as data.

One row per ``(table, ingest path)``. Each row says which columns that path may put in an
``INSERT``, which it may move in the ``ON CONFLICT DO UPDATE SET`` clause, which it writes
through a *different*, named statement, which it must never move after the insert, and
which of the updated ones are monotonic (``max(table.col, excluded.col)`` rather than
``excluded.col``).

The declaration is not documentation. ``db/repo.py`` builds every collector upsert from it
through one generator (``_upsert_for``), and ``tests/db/test_repo_ownership.py`` asserts the
*emitted SQL* against the declaration on every row -- the ``DO UPDATE SET`` column set, the
``DO NOTHING`` branch, the ``ON CONFLICT`` target and the ``max(...)`` fragments -- so a
statement and its declaration cannot drift apart (design-round5 §4.1-§4.3).

Only the M1a ingest path is populated. M1b/M1c/M3 rows land with their stage, so the
assertions grow with the code and never ahead of it.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

__all__ = ["OWNERSHIP", "IngestPath", "Ownership"]


class IngestPath(StrEnum):
    """Values of ``posts.source`` / ``comments.source``: which code path last wrote the row."""

    SUBREDDIT_NEW = "subreddit_new"
    COMMENTS = "comments"  # M1b
    INFO = "info"  # M1c
    SEARCH = "search"  # M3


@dataclass(frozen=True, slots=True)
class Ownership:
    """What one ingest path may write to one table, and what the emitted statement must say.

    Every column of the table falls in exactly one of ``update_columns`` /
    ``derived_columns`` / ``never_update`` (rule 3); ``insert_columns`` cuts across all
    three and never contains a primary key (rules 4 and 5).
    """

    table: str
    path: IngestPath
    #: The ON CONFLICT target. A real UNIQUE constraint of the table; rule 2 checks that.
    conflict_columns: tuple[str, ...]
    #: Columns present in the INSERT ... VALUES row this path builds.
    insert_columns: frozenset[str]
    #: Columns in ON CONFLICT DO UPDATE SET. EMPTY means the statement is DO NOTHING.
    update_columns: frozenset[str]
    #: Columns this path writes through a DECLARED separate statement, never through the
    #: upsert's SET clause. The docstring names the function; today only recount_authors.
    derived_columns: frozenset[str]
    #: This path must never move these after the insert.
    never_update: frozenset[str]
    #: Columns whose SET clause is ``max(<table>.col, excluded.col)`` rather than
    #: ``excluded.col``, so a late or out-of-order write cannot move them backwards.
    monotonic_columns: frozenset[str] = frozenset()


#: Every column of ``posts`` except ``pk`` (AUTOINCREMENT, rule 5) and ``scrubbed_at``
#: (tranche A never writes it at all -- the scrub service owns it from M1c, so no row can
#: read "scrubbed" while carrying content). Written out literally rather than derived from
#: the metadata: a column added without a decision must fail rule 3, not be swept in.
_POSTS_INSERT_COLUMNS: Final = frozenset({
    "reddit_id", "fullname", "subreddit_pk", "subreddit_id",
    "author", "author_fullname", "author_flair_text", "author_is_bot",
    "title", "selftext", "selftext_html", "url", "domain", "permalink",
    "created_utc", "edited_utc", "score", "upvote_ratio", "num_comments",
    "link_flair_text", "over_18", "spoiler", "is_self", "is_video", "is_gallery",
    "post_hint", "locked", "stickied", "archived", "distinguished",
    "crosspost_parent", "num_crossposts", "removed_by_category",
    "content_state", "author_state", "misses",
    "first_seen_at", "last_fetched_at",
    "comments_fetched_at", "comments_captured", "comments_complete",
    "more_skipped", "more_skipped_count", "more_skipped_reason",
    "next_check_at", "check_stage",
    "source", "normalizer_version", "raw_json",
})  # fmt: skip


#: Keyed by (table, path). Only the M1a path is populated.
OWNERSHIP: Final[Mapping[tuple[str, IngestPath], Ownership]] = MappingProxyType({
    ("posts", IngestPath.SUBREDDIT_NEW): Ownership(
        table="posts",
        path=IngestPath.SUBREDDIT_NEW,
        conflict_columns=("reddit_id",),
        insert_columns=_POSTS_INSERT_COLUMNS,
        update_columns=frozenset({
            # content refreshed every sweep, wire markers included (§6.4)
            "title", "selftext", "selftext_html", "url", "domain", "permalink",
            "link_flair_text", "author_flair_text",
            # numerics and flags Reddit moves
            "score", "upvote_ratio", "num_comments", "edited_utc", "num_crossposts",
            "over_18", "spoiler", "is_self", "is_video", "is_gallery", "post_hint",
            "locked", "stickied", "archived", "distinguished", "removed_by_category",
            # identity/author as observed
            "author", "author_fullname", "author_is_bot", "subreddit_id",
            # state the sweep observes (computed by core.deletion.decide against the prior row)
            "content_state", "author_state", "misses",
            # provenance of this write
            "last_fetched_at", "source", "normalizer_version", "raw_json",
        }),
        derived_columns=frozenset(),
        never_update=frozenset({
            "pk", "reddit_id", "fullname", "subreddit_pk", "created_utc",
            "first_seen_at", "check_stage", "next_check_at",
            "comments_fetched_at", "comments_captured", "comments_complete",
            "more_skipped", "more_skipped_count", "more_skipped_reason",
            "scrubbed_at", "crosspost_parent",
        }),
    ),
    ("authors", IngestPath.SUBREDDIT_NEW): Ownership(
        table="authors",
        path=IngestPath.SUBREDDIT_NEW,
        conflict_columns=("author_fullname",),
        insert_columns=frozenset({"author_fullname", "name", "first_seen_at", "last_seen_at"}),
        update_columns=frozenset({"name", "last_seen_at"}),
        #: repo.recount_authors, one UPDATE per page over the touched fullnames (§5.2).
        derived_columns=frozenset({"post_count", "comment_count"}),
        never_update=frozenset({"pk", "author_fullname", "first_seen_at"}),
        monotonic_columns=frozenset({"last_seen_at"}),
    ),
    ("post_sources", IngestPath.SUBREDDIT_NEW): Ownership(
        table="post_sources",
        path=IngestPath.SUBREDDIT_NEW,
        conflict_columns=("post_pk", "source_type", "source_pk"),
        insert_columns=frozenset({"post_pk", "source_type", "source_pk", "first_seen_at"}),
        update_columns=frozenset(),  # => INSERT ... ON CONFLICT ... DO NOTHING
        derived_columns=frozenset(),
        never_update=frozenset({"pk", "post_pk", "source_type", "source_pk", "first_seen_at"}),
    ),
})  # fmt: skip
