"""Schema revision 1: SQLAlchemy 2.0 declarative models for every ordinary table.

Conventions (docs/PLAN.md "Data model"):

- Integer surrogate primary keys named ``pk``; ``posts`` and ``comments`` use SQLite
  ``AUTOINCREMENT`` so a purge can never recycle a rowid into a stale FTS entry.
- ``reddit_id TEXT NOT NULL UNIQUE`` wherever a Reddit object is stored.
- Every timestamp is an INTEGER of epoch seconds (``*_utc`` for Reddit's clock, ``*_at``
  for ours). No ``DateTime`` anywhere: SQLite drops the timezone silently.
- Derived enums are closed by CHECK constraints; upstream enums (``removed_by_category``,
  ``post_hint``, ``subreddit_type``, ``distinguished``, ...) stay open TEXT so an unknown
  value is stored raw and counted, never coerced.
- Every column carries ``comment=``; ``schema.sql`` renders them as the data dictionary.
- All constraints are named through ``NAMING_CONVENTION`` so Alembic batch operations can
  drop them by name.

The FTS5 tables, the ``*_live`` views and the sync triggers are not models; they are
created with ``op.execute`` in the migration (see ``migrations/versions/0001_initial.py``).
"""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

__all__ = [
    "AUTHOR_STATES",
    "CONTENT_STATES",
    "ITEM_KINDS",
    "NAMING_CONVENTION",
    "RULE_GROUPS",
    "RULE_KINDS",
    "RULE_SCOPES",
    "RUN_STATUSES",
    "RUN_TRIGGERS",
    "SOURCE_TYPES",
    "STOP_REASONS",
    "SUBREDDIT_STATUSES",
    "Author",
    "Backup",
    "Base",
    "Comment",
    "CommentMore",
    "ItemSnapshot",
    "Post",
    "PostSource",
    "PostTheme",
    "RawReject",
    "Run",
    "RunSubreddit",
    "Search",
    "Subreddit",
    "Theme",
    "ThemeRule",
    "UiState",
    "Workspace",
]

NAMING_CONVENTION: dict[str, str] = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

# Closed (derived) enumerations. These are the values our own code produces; the CHECK
# constraints below reject anything else so a typo can never masquerade as a state.
CONTENT_STATES: tuple[str, ...] = (
    "live",
    "deleted_by_author",
    "removed_by_moderator",
    "removed_by_reddit",
    "gone_unconfirmed",
    "gone",
)
AUTHOR_STATES: tuple[str, ...] = ("known", "account_deleted")
SUBREDDIT_STATUSES: tuple[str, ...] = (
    "ok",
    "forbidden",
    "not_found",
    "redirect",
    "quarantined",
    "error",
)
SOURCE_TYPES: tuple[str, ...] = ("subreddit", "search")
ITEM_KINDS: tuple[str, ...] = ("post", "comment")
RULE_GROUPS: tuple[str, ...] = ("match", "exclude", "only_in")
RULE_KINDS: tuple[str, ...] = ("keyword", "regex", "flair", "subreddit")
RULE_SCOPES: tuple[str, ...] = ("title", "body", "comments", "any")
RUN_TRIGGERS: tuple[str, ...] = ("cli", "ui", "schedule")
RUN_STATUSES: tuple[str, ...] = (
    "queued",
    "running",
    "ok",
    "partial",
    "failed",
    "rate_limited",
    "skipped_locked",
    "crashed",
    "cancelled",
    "network",
)
STOP_REASONS: tuple[str, ...] = ("exhausted", "cap", "error")


def _in(column: str, values: Sequence[str], name: str) -> CheckConstraint:
    """CHECK that ``column`` is one of ``values`` (NULL passes; use NOT NULL to forbid it)."""
    quoted = ", ".join(f"'{v}'" for v in values)
    return CheckConstraint(f"{column} IN ({quoted})", name=name)


class Base(DeclarativeBase):
    """Declarative base carrying the project naming convention."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class Workspace(Base):
    """A named set of sources, themes, digest settings and ranking rules (one per domain)."""

    __tablename__ = "workspaces"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    slug: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, comment="URL slug and stable identity (e.g. premiere)."
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, comment="Human-readable name.")
    description: Mapped[str | None] = mapped_column(Text, comment="What the workspace is for.")
    ranking: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="distinct_authors",
        comment="Top-issue ranking rule for digests and theme pages.",
    )
    digest_settings_json: Mapped[str | None] = mapped_column(
        Text, comment="Per-workspace digest settings as JSON (sections, thresholds, timezone)."
    )
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds when the workspace was created."
    )


class Subreddit(Base):
    """A polled source: one row per (workspace, subreddit); two workspaces may share a name."""

    __tablename__ = "subreddits"
    __table_args__ = (
        _in("status", SUBREDDIT_STATUSES, "status"),
        UniqueConstraint("workspace_pk", "name_lower", name="uq_subreddits_workspace_name_lower"),
        UniqueConstraint(
            "workspace_pk", "subreddit_id", name="uq_subreddits_workspace_subreddit_id"
        ),
        Index("ix_subreddits_workspace_pk", "workspace_pk"),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    workspace_pk: Mapped[int] = mapped_column(
        ForeignKey("workspaces.pk"), nullable=False, comment="Owning workspace."
    )
    name_lower: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Lower-cased display name; unique within the workspace."
    )
    display_name: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Display name as Reddit capitalises it."
    )
    subreddit_id: Mapped[str | None] = mapped_column(
        Text, comment="Reddit fullname (t5_...), set once validated; unique within the workspace."
    )
    subreddit_type: Mapped[str | None] = mapped_column(
        Text, comment="Upstream enum stored raw (public, restricted, private, ...)."
    )
    subscribers: Mapped[int | None] = mapped_column(
        Integer, comment="Subscriber count at last validation."
    )
    over18: Mapped[bool | None] = mapped_column(
        Boolean, comment="Subreddit is marked NSFW upstream."
    )
    quarantine: Mapped[bool | None] = mapped_column(
        Boolean, comment="Subreddit is quarantined upstream."
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("1"),
        comment="Polled by the collector when 1; discovered-only rows are 0.",
    )
    comment_mode: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="full",
        comment="How comment trees are harvested for this source (default full).",
    )
    added_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds when the row was added."
    )
    watermark_created_utc: Mapped[int | None] = mapped_column(
        Integer, comment="Max created_utc seen in the last sweep (informational)."
    )
    last_complete_poll_at: Mapped[int | None] = mapped_column(
        Integer, comment="Epoch seconds of the last sweep that reached known territory."
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="ok",
        comment="Derived source status; see SUBREDDIT_STATUSES.",
    )
    last_error: Mapped[str | None] = mapped_column(
        Text, comment="Last error message; cleared when a run succeeds."
    )
    consecutive_failures: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="Failed sweeps in a row; reset to 0 on success.",
    )
    gap_suspected_at: Mapped[int | None] = mapped_column(
        Integer, comment="Epoch seconds when a sweep hit the 1000-item cap before known posts."
    )


class Search(Base):
    """A saved Reddit-wide search run on the schedule as a third source type (M3)."""

    __tablename__ = "searches"
    __table_args__ = (Index("ix_searches_workspace_pk", "workspace_pk"),)

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    workspace_pk: Mapped[int] = mapped_column(
        ForeignKey("workspaces.pk"), nullable=False, comment="Owning workspace."
    )
    query: Mapped[str] = mapped_column(Text, nullable=False, comment="Reddit search query.")
    scope: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="all",
        comment="'all' or a comma-separated list of subreddit names to search within.",
    )
    sort: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="new", comment="Upstream sort (new, relevance, ...)."
    )
    time_filter: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="week",
        comment="Upstream time filter (hour, day, week, month, year, all).",
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1"), comment="Run by the collector when 1."
    )
    last_run_at: Mapped[int | None] = mapped_column(
        Integer, comment="Epoch seconds of the last execution."
    )
    status: Mapped[str | None] = mapped_column(
        Text, comment="Outcome of the last execution (ok or an error class)."
    )


class Post(Base):
    """Upserted current state of a submission; scrubbed to a tombstone when gone."""

    __tablename__ = "posts"
    __table_args__ = (
        _in("content_state", CONTENT_STATES, "content_state"),
        _in("author_state", AUTHOR_STATES, "author_state"),
        Index("ix_posts_next_check_at", "next_check_at"),
        Index("ix_posts_subreddit_pk_created_utc", "subreddit_pk", "created_utc"),
        Index("ix_posts_author_fullname", "author_fullname"),
        Index("ix_posts_content_state", "content_state"),
        {"sqlite_autoincrement": True},
    )

    pk: Mapped[int] = mapped_column(
        Integer, primary_key=True, comment="Surrogate key; also the FTS rowid. AUTOINCREMENT."
    )
    reddit_id: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, comment="Reddit base36 id (without t3_ prefix)."
    )
    fullname: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Reddit fullname (t3_ + reddit_id)."
    )
    subreddit_pk: Mapped[int] = mapped_column(
        ForeignKey("subreddits.pk"), nullable=False, comment="Owning subreddit row."
    )
    subreddit_id: Mapped[str | None] = mapped_column(
        Text, comment="Subreddit fullname (t5_...) as reported on the item."
    )
    author: Mapped[str | None] = mapped_column(
        Text, comment="Author name; NULL once scrubbed or account deleted."
    )
    author_fullname: Mapped[str | None] = mapped_column(
        Text, comment="Author fullname (t2_...); NULL once scrubbed or account deleted."
    )
    author_flair_text: Mapped[str | None] = mapped_column(
        Text, comment="Author flair in this subreddit; NULL once scrubbed."
    )
    author_is_bot: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
        comment="Heuristic or confirmed bot author; excluded from themes and digest.",
    )
    title: Mapped[str | None] = mapped_column(Text, comment="Title; NULL once scrubbed.")
    selftext: Mapped[str | None] = mapped_column(
        Text, comment="Markdown body (empty for link posts); NULL once scrubbed."
    )
    selftext_html: Mapped[str | None] = mapped_column(
        Text, comment="Body rendered and sanitised at ingest; NULL once scrubbed."
    )
    url: Mapped[str | None] = mapped_column(Text, comment="Link target; NULL once scrubbed.")
    domain: Mapped[str | None] = mapped_column(
        Text, comment="Domain of url (self.<sub> for self posts); NULL once scrubbed."
    )
    permalink: Mapped[str | None] = mapped_column(
        Text, comment="Reddit permalink path (contains the title slug); NULL once scrubbed."
    )
    created_utc: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds the post was created (Reddit clock)."
    )
    edited_utc: Mapped[int | None] = mapped_column(
        Integer, comment="Epoch seconds of the last edit; NULL when never edited."
    )
    score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="Net score at last fetch."
    )
    upvote_ratio: Mapped[float | None] = mapped_column(
        Float, comment="Upvote ratio 0..1 at last fetch."
    )
    num_comments: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="Comment count reported by Reddit at last fetch.",
    )
    link_flair_text: Mapped[str | None] = mapped_column(Text, comment="Post flair text.")
    over_18: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="Marked NSFW."
    )
    spoiler: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="Marked spoiler."
    )
    is_self: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="Text post (no link)."
    )
    is_video: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="Reddit-hosted video."
    )
    is_gallery: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="Image gallery post."
    )
    post_hint: Mapped[str | None] = mapped_column(
        Text, comment="Upstream media hint stored raw (image, link, hosted:video, ...)."
    )
    locked: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="Comments locked."
    )
    stickied: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
        comment="Pinned by moderators; excluded from sweep stop logic.",
    )
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="Archived (no new comments)."
    )
    distinguished: Mapped[str | None] = mapped_column(
        Text, comment="Upstream distinguish stored raw (moderator, admin, ...)."
    )
    crosspost_parent: Mapped[str | None] = mapped_column(
        Text, comment="Fullname of the crosspost parent; its text is never stored."
    )
    num_crossposts: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="Crosspost count."
    )
    removed_by_category: Mapped[str | None] = mapped_column(
        Text, comment="Upstream removal category stored raw (moderator, reddit, deleted, ...)."
    )
    content_state: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="live",
        comment="Derived content state; see CONTENT_STATES. Only live rows are indexed.",
    )
    author_state: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="known",
        comment="Derived author state; see AUTHOR_STATES.",
    )
    misses: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="Consecutive reconcile passes in which info() omitted the item.",
    )
    scrubbed_at: Mapped[int | None] = mapped_column(
        Integer, comment="Epoch seconds when content and author columns were nulled."
    )
    first_seen_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds of first capture; never updated."
    )
    last_fetched_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds of the last successful fetch."
    )
    comments_fetched_at: Mapped[int | None] = mapped_column(
        Integer, comment="Epoch seconds of the last comment-tree fetch."
    )
    comments_captured: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="Comments stored from the last tree fetch.",
    )
    comments_complete: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
        comment="1 when the tree fetch succeeded and replace_more skipped nothing.",
    )
    more_skipped: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
        comment="1 when at least one 'more' stub was left unexpanded.",
    )
    more_skipped_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="Comments left unexpanded (sum of stub counts).",
    )
    more_skipped_reason: Mapped[str | None] = mapped_column(
        Text, comment="Why stubs were skipped (per-post cap, budget, error)."
    )
    next_check_at: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        comment="Epoch seconds the revisit ladder makes this post due; NOT NULL by design.",
    )
    check_stage: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="Revisit ladder stage reached (0 = discovered).",
    )
    source: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Ingest path of the last write (e.g. subreddit_new, comments).",
    )
    normalizer_version: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Version of the JSON-to-columns code that wrote the row."
    )
    raw_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Canonical raw JSON for reprocessing; replaced by a tombstone on scrub.",
    )


class Comment(Base):
    """Upserted current state of a comment; the tree is built in Python from post_pk."""

    __tablename__ = "comments"
    __table_args__ = (
        _in("content_state", CONTENT_STATES, "content_state"),
        _in("author_state", AUTHOR_STATES, "author_state"),
        Index("ix_comments_post_pk_parent_comment_pk", "post_pk", "parent_comment_pk"),
        Index("ix_comments_author_fullname", "author_fullname"),
        {"sqlite_autoincrement": True},
    )

    pk: Mapped[int] = mapped_column(
        Integer, primary_key=True, comment="Surrogate key; also the FTS rowid. AUTOINCREMENT."
    )
    reddit_id: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, comment="Reddit base36 id (without t1_ prefix)."
    )
    fullname: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Reddit fullname (t1_ + reddit_id)."
    )
    post_pk: Mapped[int] = mapped_column(
        ForeignKey("posts.pk"), nullable=False, comment="Owning post row."
    )
    parent_fullname: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Raw parent fullname (t3_ for top level, t1_ otherwise)."
    )
    parent_comment_pk: Mapped[int | None] = mapped_column(
        Integer,
        comment="Parent comment row when captured; NULL at top level or under a stub. No FK.",
    )
    author: Mapped[str | None] = mapped_column(
        Text, comment="Author name; NULL once scrubbed or account deleted."
    )
    author_fullname: Mapped[str | None] = mapped_column(
        Text, comment="Author fullname (t2_...); NULL once scrubbed or account deleted."
    )
    author_is_bot: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        server_default=text("0"),
        comment="Heuristic or confirmed bot author; excluded from themes and digest.",
    )
    body: Mapped[str | None] = mapped_column(Text, comment="Markdown body; NULL once scrubbed.")
    body_html: Mapped[str | None] = mapped_column(
        Text, comment="Body rendered and sanitised at ingest; NULL once scrubbed."
    )
    created_utc: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds the comment was created (Reddit clock)."
    )
    edited_utc: Mapped[int | None] = mapped_column(
        Integer, comment="Epoch seconds of the last edit; NULL when never edited."
    )
    score: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="Net score at last fetch."
    )
    depth: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="Nesting depth (0 = top level)."
    )
    permalink: Mapped[str | None] = mapped_column(
        Text, comment="Reddit permalink path; NULL once scrubbed."
    )
    is_submitter: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="Author is the post author."
    )
    stickied: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="Pinned by moderators."
    )
    distinguished: Mapped[str | None] = mapped_column(
        Text, comment="Upstream distinguish stored raw (moderator, admin, ...)."
    )
    content_state: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="live",
        comment="Derived content state; see CONTENT_STATES. Only live rows are indexed.",
    )
    author_state: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default="known",
        comment="Derived author state; see AUTHOR_STATES.",
    )
    misses: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="Consecutive reconcile passes in which info() omitted the item.",
    )
    scrubbed_at: Mapped[int | None] = mapped_column(
        Integer, comment="Epoch seconds when content and author columns were nulled."
    )
    first_seen_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds of first capture; never updated."
    )
    last_fetched_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds of the last successful fetch."
    )
    source: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Ingest path of the last write (comments, info, ...)."
    )
    normalizer_version: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Version of the JSON-to-columns code that wrote the row."
    )
    raw_json: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        comment="Canonical raw JSON for reprocessing; replaced by a tombstone on scrub.",
    )


class CommentMore(Base):
    """An unexpanded 'more comments' stub, rendered as 'N replies not captured'."""

    __tablename__ = "comment_more"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    post_pk: Mapped[int] = mapped_column(
        ForeignKey("posts.pk", ondelete="CASCADE"), nullable=False, comment="Owning post row."
    )
    parent_comment_pk: Mapped[int | None] = mapped_column(
        Integer, comment="Comment the stub hangs under; NULL when directly under the post. No FK."
    )
    count: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Number of replies Reddit reported behind the stub."
    )


class PostSource(Base):
    """Provenance: which source(s) delivered a post. A post can arrive both ways."""

    __tablename__ = "post_sources"
    __table_args__ = (
        _in("source_type", SOURCE_TYPES, "source_type"),
        UniqueConstraint("post_pk", "source_type", "source_pk", name="uq_post_sources_identity"),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    post_pk: Mapped[int] = mapped_column(
        ForeignKey("posts.pk", ondelete="CASCADE"), nullable=False, comment="The post."
    )
    source_type: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Kind of source; see SOURCE_TYPES."
    )
    source_pk: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="subreddits.pk or searches.pk depending on source_type."
    )
    first_seen_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds this source first delivered the post."
    )


class ItemSnapshot(Base):
    """Numeric-only history written on every revisit (no content, no hashes of content)."""

    __tablename__ = "item_snapshots"
    __table_args__ = (
        _in("kind", ITEM_KINDS, "kind"),
        Index("ix_item_snapshots_item_pk_fetched_at", "item_pk", "fetched_at"),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    item_pk: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="posts.pk or comments.pk depending on kind. No FK."
    )
    kind: Mapped[str] = mapped_column(Text, nullable=False, comment="post or comment.")
    fetched_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds of the fetch that produced the snapshot."
    )
    score: Mapped[int | None] = mapped_column(Integer, comment="Score at fetch time.")
    num_comments: Mapped[int | None] = mapped_column(
        Integer, comment="Comment count at fetch time (posts only)."
    )
    upvote_ratio: Mapped[float | None] = mapped_column(
        Float, comment="Upvote ratio at fetch time (posts only)."
    )


class Author(Base):
    """Per-author aggregate maintained at ingest; deleted when the account is deleted."""

    __tablename__ = "authors"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    author_fullname: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, comment="Author fullname (t2_...)."
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, comment="Author name as last seen.")
    first_seen_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds of the first captured item."
    )
    last_seen_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds of the most recent captured item."
    )
    post_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="Captured posts; checked against COUNT(*) by invariant.",
    )
    comment_count: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="Captured comments; checked against COUNT(*) by invariant.",
    )


class Theme(Base):
    """A named group of local tagging rules (the #1 priority: quality-issue themes)."""

    __tablename__ = "themes"
    __table_args__ = (
        UniqueConstraint("workspace_pk", "name", name="uq_themes_workspace_name"),
        UniqueConstraint("workspace_pk", "slug", name="uq_themes_workspace_slug"),
        Index("ix_themes_workspace_pk", "workspace_pk"),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    workspace_pk: Mapped[int] = mapped_column(
        ForeignKey("workspaces.pk"), nullable=False, comment="Owning workspace."
    )
    name: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Human-readable name; unique within the workspace."
    )
    slug: Mapped[str] = mapped_column(
        Text, nullable=False, comment="URL slug used at /t/{slug}; unique within the workspace."
    )
    color: Mapped[str | None] = mapped_column(Text, comment="UI colour token or hex.")
    description: Mapped[str | None] = mapped_column(Text, comment="What the theme captures.")
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1"), comment="Applied when tagging if 1."
    )
    rules_hash: Mapped[str | None] = mapped_column(
        Text, comment="Hash of the enabled rules; a change triggers a full retag."
    )
    tagged_hash: Mapped[str | None] = mapped_column(
        Text, comment="rules_hash that produced the current post_themes rows."
    )


class ThemeRule(Base):
    """One keyword/regex/flair/subreddit rule inside a theme."""

    __tablename__ = "theme_rules"
    __table_args__ = (
        _in("rule_group", RULE_GROUPS, "rule_group"),
        _in("kind", RULE_KINDS, "kind"),
        _in("scope", RULE_SCOPES, "scope"),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    theme_pk: Mapped[int] = mapped_column(
        ForeignKey("themes.pk", ondelete="CASCADE"), nullable=False, comment="Owning theme."
    )
    rule_group: Mapped[str] = mapped_column(
        Text, nullable=False, comment="match, exclude or only_in (the plan's 'group')."
    )
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, comment="keyword, regex, flair or subreddit."
    )
    pattern: Mapped[str] = mapped_column(
        Text, nullable=False, comment="The keyword, regex, flair text or subreddit name."
    )
    scope: Mapped[str] = mapped_column(
        Text, nullable=False, server_default="any", comment="title, body, comments or any."
    )
    case_sensitive: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="Match case when 1."
    )
    whole_word: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("0"), comment="Keyword matches whole words."
    )
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("1"), comment="Applied when tagging if 1."
    )


class PostTheme(Base):
    """A post tagged by a theme rule. No matched-text snippets: they are content."""

    __tablename__ = "post_themes"
    __table_args__ = (
        UniqueConstraint(
            "post_pk", "theme_pk", "rule_pk", "matched_field", name="uq_post_themes_identity"
        ),
        Index("ix_post_themes_theme_pk", "theme_pk"),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    post_pk: Mapped[int] = mapped_column(
        ForeignKey("posts.pk", ondelete="CASCADE"), nullable=False, comment="Tagged post."
    )
    theme_pk: Mapped[int] = mapped_column(
        ForeignKey("themes.pk", ondelete="CASCADE"), nullable=False, comment="Theme applied."
    )
    rule_pk: Mapped[int] = mapped_column(
        ForeignKey("theme_rules.pk", ondelete="CASCADE"),
        nullable=False,
        comment="Rule that matched.",
    )
    matched_field: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Field the rule matched (title, body, comments, ...)."
    )
    tagged_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds the tag was written."
    )


class Run(Base):
    """One execution of a mutating command; drives the Runs page, digest and gap detection."""

    __tablename__ = "runs"
    __table_args__ = (
        _in("trigger", RUN_TRIGGERS, "trigger"),
        _in("status", RUN_STATUSES, "status"),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Command kind (run, fetch, comments, reconcile, ...)."
    )
    trigger: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Who started it; see RUN_TRIGGERS."
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, comment="Lifecycle state; see RUN_STATUSES."
    )
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds the row was created (queued or started)."
    )
    started_at: Mapped[int | None] = mapped_column(
        Integer, comment="Epoch seconds the process took the lock; NULL while queued."
    )
    finished_at: Mapped[int | None] = mapped_column(
        Integer, comment="Epoch seconds of completion; NULL while running."
    )
    heartbeat_at: Mapped[int | None] = mapped_column(
        Integer, comment="Epoch seconds of the last heartbeat; stale after 3 minutes."
    )
    pid: Mapped[int | None] = mapped_column(Integer, comment="Process id of the runner.")
    stage: Mapped[str | None] = mapped_column(
        Text, comment="Current stage carried by the heartbeat (e.g. rate_wait:37s)."
    )
    options_json: Mapped[str | None] = mapped_column(
        Text, comment="Requested options as JSON, including the written reason for any bypass."
    )
    counters_json: Mapped[str | None] = mapped_column(
        Text, comment="Outcome counters as JSON (new, updated, scrubbed, unknown_enum_values...)."
    )
    api_requests: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        server_default=text("0"),
        comment="HTTP requests counted by our own session hook.",
    )
    app_version: Mapped[str | None] = mapped_column(Text, comment="threaddigest version.")
    praw_version: Mapped[str | None] = mapped_column(Text, comment="PRAW version.")
    schema_rev: Mapped[str | None] = mapped_column(Text, comment="Alembic revision at run time.")
    settings_fingerprint: Mapped[str | None] = mapped_column(
        Text, comment="Hash of the resolved non-secret settings."
    )
    error: Mapped[str | None] = mapped_column(Text, comment="Terminal error message, if any.")
    log_path: Mapped[str | None] = mapped_column(Text, comment="Path of the run's log file.")
    purge_counts_json: Mapped[str | None] = mapped_column(
        Text, comment="Rows purged per table as JSON, so the row-count invariant can read them."
    )
    violations_json: Mapped[str | None] = mapped_column(
        Text, comment="Invariant violations as JSON; NULL when they did not run."
    )


class RunSubreddit(Base):
    """Per-subreddit outcome of a sweep inside a run."""

    __tablename__ = "run_subreddits"
    __table_args__ = (
        _in("stop_reason", STOP_REASONS, "stop_reason"),
        UniqueConstraint("run_pk", "subreddit_pk", name="uq_run_subreddits_identity"),
    )

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    run_pk: Mapped[int] = mapped_column(
        ForeignKey("runs.pk", ondelete="CASCADE"), nullable=False, comment="The run."
    )
    subreddit_pk: Mapped[int] = mapped_column(
        ForeignKey("subreddits.pk"), nullable=False, comment="The subreddit swept."
    )
    pages: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="Listing pages fetched."
    )
    items_seen: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="Items seen in the listing."
    )
    new_items: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="Posts inserted."
    )
    updated_items: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default=text("0"), comment="Posts updated."
    )
    stop_reason: Mapped[str | None] = mapped_column(
        Text, comment="Why paging stopped; see STOP_REASONS. NULL while in progress."
    )
    error: Mapped[str | None] = mapped_column(Text, comment="Error message when stop_reason=error.")


class RawReject(Base):
    """A wire item missing a required field (id, created_utc, subreddit); 30-day retention."""

    __tablename__ = "raw_rejects"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    run_pk: Mapped[int] = mapped_column(
        ForeignKey("runs.pk", ondelete="CASCADE"), nullable=False, comment="Run that saw it."
    )
    raw_json: Mapped[str] = mapped_column(Text, nullable=False, comment="The rejected item.")
    error: Mapped[str] = mapped_column(Text, nullable=False, comment="Why it was rejected.")
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds; rows older than 30 days are purged."
    )


class UiState(Base):
    """Small key/value store for UI state such as last_visit_at."""

    __tablename__ = "ui_state"

    key: Mapped[str] = mapped_column(Text, primary_key=True, comment="State key.")
    value: Mapped[str] = mapped_column(Text, nullable=False, comment="State value (text).")
    updated_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds of the last write."
    )


class Backup(Base):
    """A verified backup file; the destructive gate requires a recent row here."""

    __tablename__ = "backups"

    pk: Mapped[int] = mapped_column(Integer, primary_key=True, comment="Surrogate key.")
    path: Mapped[str] = mapped_column(
        Text, nullable=False, unique=True, comment="Absolute path of the backup file."
    )
    sha256: Mapped[str] = mapped_column(
        Text, nullable=False, comment="SHA-256 of the file after it was written."
    )
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False, comment="File size.")
    integrity: Mapped[str] = mapped_column(
        Text, nullable=False, comment="PRAGMA integrity_check result on the copy ('ok' or text)."
    )
    kind: Mapped[str] = mapped_column(
        Text, nullable=False, comment="daily, weekly, pre-migrate, manual or export."
    )
    created_at: Mapped[int] = mapped_column(
        Integer, nullable=False, comment="Epoch seconds the backup finished."
    )
    schema_rev: Mapped[str | None] = mapped_column(
        Text, comment="Alembic revision of the database at backup time."
    )
    table_counts_json: Mapped[str | None] = mapped_column(
        Text, comment="Row counts per table at backup time as JSON, for restore verification."
    )
