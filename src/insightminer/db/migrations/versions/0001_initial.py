"""Schema revision 1: every ordinary table, the live views, FTS5 and the sync triggers.

Revision ID: 0001
Revises:
Create Date: 2026-09-13

Frozen snapshot: never edit after it has been applied anywhere. The FTS5 tables index the
``*_live`` views (live rows only) so ``rebuild`` and ``integrity-check`` agree with the
triggers; the triggers sit on the base tables and gate on ``content_state = 'live'``.
Seeds the default ``premiere`` workspace so the first run has a workspace to attach to.

Checklist for any later batch operation on ``posts`` or ``comments`` (SQLite recreates the
table): drop the ``*_live`` view and the three FTS triggers first, recreate them afterwards,
then run the FTS ``rebuild`` command, all inside that migration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# --- FTS5 search objects (created with op.execute; not SQLAlchemy models) -----------------

FTS_DDL: tuple[str, ...] = (
    # Live-only views: the FTS5 external-content source, so rebuild indexes live rows only.
    """CREATE VIEW IF NOT EXISTS posts_live AS
    SELECT pk, title, selftext, author FROM posts WHERE content_state = 'live'""",
    """CREATE VIEW IF NOT EXISTS comments_live AS
    SELECT pk, body, author FROM comments WHERE content_state = 'live'""",
    # External-content FTS5 tables keyed on pk (columnsize on by default -> *_docsize exists).
    """CREATE VIRTUAL TABLE IF NOT EXISTS posts_fts USING fts5(
    title, selftext, author,
    content='posts_live', content_rowid='pk', tokenize='porter unicode61')""",
    """CREATE VIRTUAL TABLE IF NOT EXISTS comments_fts USING fts5(
    body, author,
    content='comments_live', content_rowid='pk', tokenize='porter unicode61')""",
    # posts: insert when live; on update drop the OLD entry if it was live and add NEW if live;
    # delete when a live row goes away. The update trigger fires only for indexed columns and
    # the state column, so score refreshes do not churn the index.
    """CREATE TRIGGER IF NOT EXISTS posts_fts_ai AFTER INSERT ON posts
    WHEN new.content_state = 'live'
    BEGIN
        INSERT INTO posts_fts(rowid, title, selftext, author)
        VALUES (new.pk, new.title, new.selftext, new.author);
    END""",
    """CREATE TRIGGER IF NOT EXISTS posts_fts_au
    AFTER UPDATE OF title, selftext, author, content_state ON posts
    BEGIN
        INSERT INTO posts_fts(posts_fts, rowid, title, selftext, author)
        SELECT 'delete', old.pk, old.title, old.selftext, old.author
        WHERE old.content_state = 'live';
        INSERT INTO posts_fts(rowid, title, selftext, author)
        SELECT new.pk, new.title, new.selftext, new.author
        WHERE new.content_state = 'live';
    END""",
    """CREATE TRIGGER IF NOT EXISTS posts_fts_ad AFTER DELETE ON posts
    WHEN old.content_state = 'live'
    BEGIN
        INSERT INTO posts_fts(posts_fts, rowid, title, selftext, author)
        VALUES ('delete', old.pk, old.title, old.selftext, old.author);
    END""",
    # comments: same shape.
    """CREATE TRIGGER IF NOT EXISTS comments_fts_ai AFTER INSERT ON comments
    WHEN new.content_state = 'live'
    BEGIN
        INSERT INTO comments_fts(rowid, body, author)
        VALUES (new.pk, new.body, new.author);
    END""",
    """CREATE TRIGGER IF NOT EXISTS comments_fts_au
    AFTER UPDATE OF body, author, content_state ON comments
    BEGIN
        INSERT INTO comments_fts(comments_fts, rowid, body, author)
        SELECT 'delete', old.pk, old.body, old.author
        WHERE old.content_state = 'live';
        INSERT INTO comments_fts(rowid, body, author)
        SELECT new.pk, new.body, new.author
        WHERE new.content_state = 'live';
    END""",
    """CREATE TRIGGER IF NOT EXISTS comments_fts_ad AFTER DELETE ON comments
    WHEN old.content_state = 'live'
    BEGIN
        INSERT INTO comments_fts(comments_fts, rowid, body, author)
        VALUES ('delete', old.pk, old.body, old.author);
    END""",
)

FTS_DROP_DDL: tuple[str, ...] = (
    "DROP TRIGGER IF EXISTS comments_fts_ad",
    "DROP TRIGGER IF EXISTS comments_fts_au",
    "DROP TRIGGER IF EXISTS comments_fts_ai",
    "DROP TRIGGER IF EXISTS posts_fts_ad",
    "DROP TRIGGER IF EXISTS posts_fts_au",
    "DROP TRIGGER IF EXISTS posts_fts_ai",
    "DROP TABLE IF EXISTS comments_fts",
    "DROP TABLE IF EXISTS posts_fts",
    "DROP VIEW IF EXISTS comments_live",
    "DROP VIEW IF EXISTS posts_live",
)

SEED_WORKSPACE = sa.text(
    "INSERT INTO workspaces (pk, slug, name, description, ranking, created_at) "
    "VALUES (1, 'premiere', 'Premiere Pro quality signals', "
    "'Reddit discussion about Premiere Pro and adjacent video-editing communities.', "
    "'distinct_authors', CAST(strftime('%s', 'now') AS INTEGER))"
)


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column(
            "slug",
            sa.Text(),
            nullable=False,
            comment="URL slug and stable identity (e.g. premiere).",
        ),
        sa.Column("name", sa.Text(), nullable=False, comment="Human-readable name."),
        sa.Column("description", sa.Text(), nullable=True, comment="What the workspace is for."),
        sa.Column(
            "ranking",
            sa.Text(),
            server_default="distinct_authors",
            nullable=False,
            comment="Top-issue ranking rule for digests and theme pages.",
        ),
        sa.Column(
            "digest_settings_json",
            sa.Text(),
            nullable=True,
            comment="Per-workspace digest settings as JSON (sections, thresholds, timezone).",
        ),
        sa.Column(
            "created_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds when the workspace was created.",
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_workspaces")),
        sa.UniqueConstraint("slug", name=op.f("uq_workspaces_slug")),
    )
    op.create_table(
        "subreddits",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column("workspace_pk", sa.Integer(), nullable=False, comment="Owning workspace."),
        sa.Column(
            "name_lower",
            sa.Text(),
            nullable=False,
            comment="Lower-cased display name; unique within the workspace.",
        ),
        sa.Column(
            "display_name",
            sa.Text(),
            nullable=False,
            comment="Display name as Reddit capitalises it.",
        ),
        sa.Column(
            "subreddit_id",
            sa.Text(),
            nullable=True,
            comment="Reddit fullname (t5_...), set once validated; unique within the workspace.",
        ),
        sa.Column(
            "subreddit_type",
            sa.Text(),
            nullable=True,
            comment="Upstream enum stored raw (public, restricted, private, ...).",
        ),
        sa.Column(
            "subscribers",
            sa.Integer(),
            nullable=True,
            comment="Subscriber count at last validation.",
        ),
        sa.Column(
            "over18", sa.Boolean(), nullable=True, comment="Subreddit is marked NSFW upstream."
        ),
        sa.Column(
            "quarantine", sa.Boolean(), nullable=True, comment="Subreddit is quarantined upstream."
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
            comment="Polled by the collector when 1; discovered-only rows are 0.",
        ),
        sa.Column(
            "comment_mode",
            sa.Text(),
            server_default="full",
            nullable=False,
            comment="How comment trees are harvested for this source (default full).",
        ),
        sa.Column(
            "added_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds when the row was added.",
        ),
        sa.Column(
            "watermark_created_utc",
            sa.Integer(),
            nullable=True,
            comment="Max created_utc seen in the last complete sweep (informational).",
        ),
        sa.Column(
            "last_complete_poll_at",
            sa.Integer(),
            nullable=True,
            comment="Epoch seconds of the last sweep that reached known territory.",
        ),
        sa.Column(
            "status",
            sa.Text(),
            server_default="ok",
            nullable=False,
            comment="Derived source status; see SUBREDDIT_STATUSES.",
        ),
        sa.Column(
            "last_error",
            sa.Text(),
            nullable=True,
            comment="Last error message; cleared when a run succeeds.",
        ),
        sa.Column(
            "consecutive_failures",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Failed sweeps in a row; reset to 0 on success.",
        ),
        sa.Column(
            "gap_suspected_at",
            sa.Integer(),
            nullable=True,
            comment="Epoch seconds when a sweep hit the 1000-item cap before known posts.",
        ),
        sa.CheckConstraint(
            "status IN ('ok', 'forbidden', 'not_found', 'redirect', 'quarantined', 'error')",
            name=op.f("ck_subreddits_status"),
        ),
        sa.ForeignKeyConstraint(
            ["workspace_pk"], ["workspaces.pk"], name=op.f("fk_subreddits_workspace_pk_workspaces")
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_subreddits")),
        sa.UniqueConstraint(
            "workspace_pk", "name_lower", name="uq_subreddits_workspace_name_lower"
        ),
        sa.UniqueConstraint(
            "workspace_pk", "subreddit_id", name="uq_subreddits_workspace_subreddit_id"
        ),
    )
    op.create_table(
        "searches",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column("workspace_pk", sa.Integer(), nullable=False, comment="Owning workspace."),
        sa.Column("query", sa.Text(), nullable=False, comment="Reddit search query."),
        sa.Column(
            "scope",
            sa.Text(),
            server_default="all",
            nullable=False,
            comment="'all' or a comma-separated list of subreddit names to search within.",
        ),
        sa.Column(
            "sort",
            sa.Text(),
            server_default="new",
            nullable=False,
            comment="Upstream sort (new, relevance, ...).",
        ),
        sa.Column(
            "time_filter",
            sa.Text(),
            server_default="week",
            nullable=False,
            comment="Upstream time filter (hour, day, week, month, year, all).",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
            comment="Run by the collector when 1.",
        ),
        sa.Column(
            "last_run_at",
            sa.Integer(),
            nullable=True,
            comment="Epoch seconds of the last execution.",
        ),
        sa.Column(
            "status",
            sa.Text(),
            nullable=True,
            comment="Outcome of the last execution (ok or an error class).",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_pk"], ["workspaces.pk"], name=op.f("fk_searches_workspace_pk_workspaces")
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_searches")),
    )
    op.create_table(
        "themes",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column("workspace_pk", sa.Integer(), nullable=False, comment="Owning workspace."),
        sa.Column(
            "name",
            sa.Text(),
            nullable=False,
            comment="Human-readable name; unique within the workspace.",
        ),
        sa.Column(
            "slug",
            sa.Text(),
            nullable=False,
            comment="URL slug used at /t/{slug}; unique within the workspace.",
        ),
        sa.Column("color", sa.Text(), nullable=True, comment="UI colour token or hex."),
        sa.Column("description", sa.Text(), nullable=True, comment="What the theme captures."),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
            comment="Applied when tagging if 1.",
        ),
        sa.Column(
            "rules_hash",
            sa.Text(),
            nullable=True,
            comment="Hash of the enabled rules; a change triggers a full retag.",
        ),
        sa.Column(
            "tagged_hash",
            sa.Text(),
            nullable=True,
            comment="rules_hash that produced the current post_themes rows.",
        ),
        sa.ForeignKeyConstraint(
            ["workspace_pk"], ["workspaces.pk"], name=op.f("fk_themes_workspace_pk_workspaces")
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_themes")),
        sa.UniqueConstraint("workspace_pk", "name", name="uq_themes_workspace_name"),
        sa.UniqueConstraint("workspace_pk", "slug", name="uq_themes_workspace_slug"),
    )
    op.create_table(
        "theme_rules",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column("theme_pk", sa.Integer(), nullable=False, comment="Owning theme."),
        sa.Column(
            "rule_group",
            sa.Text(),
            nullable=False,
            comment="match, exclude or only_in (the plan's 'group').",
        ),
        sa.Column("kind", sa.Text(), nullable=False, comment="keyword, regex, flair or subreddit."),
        sa.Column(
            "pattern",
            sa.Text(),
            nullable=False,
            comment="The keyword, regex, flair text or subreddit name.",
        ),
        sa.Column(
            "scope",
            sa.Text(),
            server_default="any",
            nullable=False,
            comment="title, body, comments or any.",
        ),
        sa.Column(
            "case_sensitive",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Match case when 1.",
        ),
        sa.Column(
            "whole_word",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Keyword matches whole words.",
        ),
        sa.Column(
            "enabled",
            sa.Boolean(),
            server_default=sa.text("1"),
            nullable=False,
            comment="Applied when tagging if 1.",
        ),
        sa.CheckConstraint(
            "kind IN ('keyword', 'regex', 'flair', 'subreddit')", name=op.f("ck_theme_rules_kind")
        ),
        sa.CheckConstraint(
            "rule_group IN ('match', 'exclude', 'only_in')", name=op.f("ck_theme_rules_rule_group")
        ),
        sa.CheckConstraint(
            "scope IN ('title', 'body', 'comments', 'any')", name=op.f("ck_theme_rules_scope")
        ),
        sa.ForeignKeyConstraint(
            ["theme_pk"],
            ["themes.pk"],
            name=op.f("fk_theme_rules_theme_pk_themes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_theme_rules")),
    )
    op.create_table(
        "posts",
        sa.Column(
            "pk",
            sa.Integer(),
            nullable=False,
            comment="Surrogate key; also the FTS rowid. AUTOINCREMENT.",
        ),
        sa.Column(
            "reddit_id", sa.Text(), nullable=False, comment="Reddit base36 id (without t3_ prefix)."
        ),
        sa.Column(
            "fullname", sa.Text(), nullable=False, comment="Reddit fullname (t3_ + reddit_id)."
        ),
        sa.Column("subreddit_pk", sa.Integer(), nullable=False, comment="Owning subreddit row."),
        sa.Column(
            "subreddit_id",
            sa.Text(),
            nullable=True,
            comment="Subreddit fullname (t5_...) as reported on the item.",
        ),
        sa.Column(
            "author",
            sa.Text(),
            nullable=True,
            comment="Author name; NULL once scrubbed or account deleted.",
        ),
        sa.Column(
            "author_fullname",
            sa.Text(),
            nullable=True,
            comment="Author fullname (t2_...); NULL once scrubbed or account deleted.",
        ),
        sa.Column(
            "author_flair_text",
            sa.Text(),
            nullable=True,
            comment="Author flair in this subreddit; NULL once scrubbed.",
        ),
        sa.Column(
            "author_is_bot",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Heuristic or confirmed bot author; excluded from themes and digest.",
        ),
        sa.Column("title", sa.Text(), nullable=True, comment="Title; NULL once scrubbed."),
        sa.Column(
            "selftext",
            sa.Text(),
            nullable=True,
            comment="Markdown body (empty for link posts); NULL once scrubbed.",
        ),
        sa.Column(
            "selftext_html",
            sa.Text(),
            nullable=True,
            comment="Body rendered and sanitised at ingest; NULL once scrubbed.",
        ),
        sa.Column("url", sa.Text(), nullable=True, comment="Link target; NULL once scrubbed."),
        sa.Column(
            "domain",
            sa.Text(),
            nullable=True,
            comment="Domain of url (self.<sub> for self posts); NULL once scrubbed.",
        ),
        sa.Column(
            "permalink",
            sa.Text(),
            nullable=True,
            comment="Reddit permalink path (contains the title slug); NULL once scrubbed.",
        ),
        sa.Column(
            "created_utc",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds the post was created (Reddit clock).",
        ),
        sa.Column(
            "edited_utc",
            sa.Integer(),
            nullable=True,
            comment="Epoch seconds of the last edit; NULL when never edited.",
        ),
        sa.Column(
            "score",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Net score at last fetch.",
        ),
        sa.Column(
            "upvote_ratio", sa.Float(), nullable=True, comment="Upvote ratio 0..1 at last fetch."
        ),
        sa.Column(
            "num_comments",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Comment count reported by Reddit at last fetch.",
        ),
        sa.Column("link_flair_text", sa.Text(), nullable=True, comment="Post flair text."),
        sa.Column(
            "over_18",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Marked NSFW.",
        ),
        sa.Column(
            "spoiler",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Marked spoiler.",
        ),
        sa.Column(
            "is_self",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Text post (no link).",
        ),
        sa.Column(
            "is_video",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Reddit-hosted video.",
        ),
        sa.Column(
            "is_gallery",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Image gallery post.",
        ),
        sa.Column(
            "post_hint",
            sa.Text(),
            nullable=True,
            comment="Upstream media hint stored raw (image, link, hosted:video, ...).",
        ),
        sa.Column(
            "locked",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Comments locked.",
        ),
        sa.Column(
            "stickied",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Pinned by moderators; excluded from sweep stop logic.",
        ),
        sa.Column(
            "archived",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Archived (no new comments).",
        ),
        sa.Column(
            "distinguished",
            sa.Text(),
            nullable=True,
            comment="Upstream distinguish stored raw (moderator, admin, ...).",
        ),
        sa.Column(
            "crosspost_parent",
            sa.Text(),
            nullable=True,
            comment="Fullname of the crosspost parent; its text is never stored.",
        ),
        sa.Column(
            "num_crossposts",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Crosspost count.",
        ),
        sa.Column(
            "removed_by_category",
            sa.Text(),
            nullable=True,
            comment="Upstream removal category stored raw (moderator, reddit, deleted, ...).",
        ),
        sa.Column(
            "content_state",
            sa.Text(),
            server_default="live",
            nullable=False,
            comment="Derived content state; see CONTENT_STATES. Only live rows are indexed.",
        ),
        sa.Column(
            "author_state",
            sa.Text(),
            server_default="known",
            nullable=False,
            comment="Derived author state; see AUTHOR_STATES.",
        ),
        sa.Column(
            "misses",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Consecutive reconcile passes in which info() omitted the item.",
        ),
        sa.Column(
            "scrubbed_at",
            sa.Integer(),
            nullable=True,
            comment="Epoch seconds when content and author columns were nulled.",
        ),
        sa.Column(
            "first_seen_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds of first capture; never updated.",
        ),
        sa.Column(
            "last_fetched_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds of the last successful fetch.",
        ),
        sa.Column(
            "comments_fetched_at",
            sa.Integer(),
            nullable=True,
            comment="Epoch seconds of the last comment-tree fetch.",
        ),
        sa.Column(
            "comments_captured",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Comments stored from the last tree fetch.",
        ),
        sa.Column(
            "comments_complete",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="1 when the tree fetch succeeded and replace_more skipped nothing.",
        ),
        sa.Column(
            "more_skipped",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="1 when at least one 'more' stub was left unexpanded.",
        ),
        sa.Column(
            "more_skipped_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Comments left unexpanded (sum of stub counts).",
        ),
        sa.Column(
            "more_skipped_reason",
            sa.Text(),
            nullable=True,
            comment="Why stubs were skipped (per-post cap, budget, error).",
        ),
        sa.Column(
            "next_check_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds the revisit ladder makes this post due; NOT NULL by design.",
        ),
        sa.Column(
            "check_stage",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Revisit ladder stage reached (0 = discovered).",
        ),
        sa.Column(
            "source",
            sa.Text(),
            nullable=False,
            comment="Ingest path of the last write (e.g. subreddit_new, comments).",
        ),
        sa.Column(
            "normalizer_version",
            sa.Integer(),
            nullable=False,
            comment="Version of the JSON-to-columns code that wrote the row.",
        ),
        sa.Column(
            "raw_json",
            sa.Text(),
            nullable=False,
            comment="Canonical raw JSON for reprocessing; replaced by a tombstone on scrub.",
        ),
        sa.CheckConstraint(
            "author_state IN ('known', 'account_deleted')", name=op.f("ck_posts_author_state")
        ),
        sa.CheckConstraint(
            "content_state IN ('live', 'deleted_by_author', 'removed_by_moderator', "
            "'removed_by_reddit', 'gone_unconfirmed', 'gone')",
            name=op.f("ck_posts_content_state"),
        ),
        sa.ForeignKeyConstraint(
            ["subreddit_pk"], ["subreddits.pk"], name=op.f("fk_posts_subreddit_pk_subreddits")
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_posts")),
        sa.UniqueConstraint("reddit_id", name=op.f("uq_posts_reddit_id")),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "comments",
        sa.Column(
            "pk",
            sa.Integer(),
            nullable=False,
            comment="Surrogate key; also the FTS rowid. AUTOINCREMENT.",
        ),
        sa.Column(
            "reddit_id", sa.Text(), nullable=False, comment="Reddit base36 id (without t1_ prefix)."
        ),
        sa.Column(
            "fullname", sa.Text(), nullable=False, comment="Reddit fullname (t1_ + reddit_id)."
        ),
        sa.Column("post_pk", sa.Integer(), nullable=False, comment="Owning post row."),
        sa.Column(
            "parent_fullname",
            sa.Text(),
            nullable=False,
            comment="Raw parent fullname (t3_ for top level, t1_ otherwise).",
        ),
        sa.Column(
            "parent_comment_pk",
            sa.Integer(),
            nullable=True,
            comment="Parent comment row when captured; NULL at top level or under a stub. No FK.",
        ),
        sa.Column(
            "author",
            sa.Text(),
            nullable=True,
            comment="Author name; NULL once scrubbed or account deleted.",
        ),
        sa.Column(
            "author_fullname",
            sa.Text(),
            nullable=True,
            comment="Author fullname (t2_...); NULL once scrubbed or account deleted.",
        ),
        sa.Column(
            "author_is_bot",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Heuristic or confirmed bot author; excluded from themes and digest.",
        ),
        sa.Column("body", sa.Text(), nullable=True, comment="Markdown body; NULL once scrubbed."),
        sa.Column(
            "body_html",
            sa.Text(),
            nullable=True,
            comment="Body rendered and sanitised at ingest; NULL once scrubbed.",
        ),
        sa.Column(
            "created_utc",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds the comment was created (Reddit clock).",
        ),
        sa.Column(
            "edited_utc",
            sa.Integer(),
            nullable=True,
            comment="Epoch seconds of the last edit; NULL when never edited.",
        ),
        sa.Column(
            "score",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Net score at last fetch.",
        ),
        sa.Column(
            "depth",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Nesting depth (0 = top level).",
        ),
        sa.Column(
            "permalink",
            sa.Text(),
            nullable=True,
            comment="Reddit permalink path; NULL once scrubbed.",
        ),
        sa.Column(
            "is_submitter",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Author is the post author.",
        ),
        sa.Column(
            "stickied",
            sa.Boolean(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Pinned by moderators.",
        ),
        sa.Column(
            "distinguished",
            sa.Text(),
            nullable=True,
            comment="Upstream distinguish stored raw (moderator, admin, ...).",
        ),
        sa.Column(
            "content_state",
            sa.Text(),
            server_default="live",
            nullable=False,
            comment="Derived content state; see CONTENT_STATES. Only live rows are indexed.",
        ),
        sa.Column(
            "author_state",
            sa.Text(),
            server_default="known",
            nullable=False,
            comment="Derived author state; see AUTHOR_STATES.",
        ),
        sa.Column(
            "misses",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Consecutive reconcile passes in which info() omitted the item.",
        ),
        sa.Column(
            "scrubbed_at",
            sa.Integer(),
            nullable=True,
            comment="Epoch seconds when content and author columns were nulled.",
        ),
        sa.Column(
            "first_seen_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds of first capture; never updated.",
        ),
        sa.Column(
            "last_fetched_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds of the last successful fetch.",
        ),
        sa.Column(
            "source",
            sa.Text(),
            nullable=False,
            comment="Ingest path of the last write (comments, info, ...).",
        ),
        sa.Column(
            "normalizer_version",
            sa.Integer(),
            nullable=False,
            comment="Version of the JSON-to-columns code that wrote the row.",
        ),
        sa.Column(
            "raw_json",
            sa.Text(),
            nullable=False,
            comment="Canonical raw JSON for reprocessing; replaced by a tombstone on scrub.",
        ),
        sa.CheckConstraint(
            "author_state IN ('known', 'account_deleted')", name=op.f("ck_comments_author_state")
        ),
        sa.CheckConstraint(
            "content_state IN ('live', 'deleted_by_author', 'removed_by_moderator', "
            "'removed_by_reddit', 'gone_unconfirmed', 'gone')",
            name=op.f("ck_comments_content_state"),
        ),
        sa.ForeignKeyConstraint(["post_pk"], ["posts.pk"], name=op.f("fk_comments_post_pk_posts")),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_comments")),
        sa.UniqueConstraint("reddit_id", name=op.f("uq_comments_reddit_id")),
        sqlite_autoincrement=True,
    )
    op.create_table(
        "comment_more",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column("post_pk", sa.Integer(), nullable=False, comment="Owning post row."),
        sa.Column(
            "parent_comment_pk",
            sa.Integer(),
            nullable=True,
            comment="Comment the stub hangs under; NULL when directly under the post. No FK.",
        ),
        sa.Column(
            "count",
            sa.Integer(),
            nullable=False,
            comment="Number of replies Reddit reported behind the stub.",
        ),
        sa.ForeignKeyConstraint(
            ["post_pk"],
            ["posts.pk"],
            name=op.f("fk_comment_more_post_pk_posts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_comment_more")),
    )
    op.create_table(
        "post_sources",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column("post_pk", sa.Integer(), nullable=False, comment="The post."),
        sa.Column(
            "source_type", sa.Text(), nullable=False, comment="Kind of source; see SOURCE_TYPES."
        ),
        sa.Column(
            "source_pk",
            sa.Integer(),
            nullable=False,
            comment="subreddits.pk or searches.pk depending on source_type.",
        ),
        sa.Column(
            "first_seen_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds this source first delivered the post.",
        ),
        sa.CheckConstraint(
            "source_type IN ('subreddit', 'search')", name=op.f("ck_post_sources_source_type")
        ),
        sa.ForeignKeyConstraint(
            ["post_pk"],
            ["posts.pk"],
            name=op.f("fk_post_sources_post_pk_posts"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_post_sources")),
        sa.UniqueConstraint("post_pk", "source_type", "source_pk", name="uq_post_sources_identity"),
    )
    op.create_table(
        "item_snapshots",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column(
            "item_pk",
            sa.Integer(),
            nullable=False,
            comment="posts.pk or comments.pk depending on kind. No FK.",
        ),
        sa.Column("kind", sa.Text(), nullable=False, comment="post or comment."),
        sa.Column(
            "fetched_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds of the fetch that produced the snapshot.",
        ),
        sa.Column("score", sa.Integer(), nullable=True, comment="Score at fetch time."),
        sa.Column(
            "num_comments",
            sa.Integer(),
            nullable=True,
            comment="Comment count at fetch time (posts only).",
        ),
        sa.Column(
            "upvote_ratio",
            sa.Float(),
            nullable=True,
            comment="Upvote ratio at fetch time (posts only).",
        ),
        sa.CheckConstraint("kind IN ('post', 'comment')", name=op.f("ck_item_snapshots_kind")),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_item_snapshots")),
    )
    op.create_table(
        "authors",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column(
            "author_fullname", sa.Text(), nullable=False, comment="Author fullname (t2_...)."
        ),
        sa.Column("name", sa.Text(), nullable=False, comment="Author name as last seen."),
        sa.Column(
            "first_seen_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds of the first captured item.",
        ),
        sa.Column(
            "last_seen_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds of the most recent captured item.",
        ),
        sa.Column(
            "post_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Captured posts; checked against COUNT(*) by invariant.",
        ),
        sa.Column(
            "comment_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Captured comments; checked against COUNT(*) by invariant.",
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_authors")),
        sa.UniqueConstraint("author_fullname", name=op.f("uq_authors_author_fullname")),
    )
    op.create_table(
        "post_themes",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column("post_pk", sa.Integer(), nullable=False, comment="Tagged post."),
        sa.Column("theme_pk", sa.Integer(), nullable=False, comment="Theme applied."),
        sa.Column("rule_pk", sa.Integer(), nullable=False, comment="Rule that matched."),
        sa.Column(
            "matched_field",
            sa.Text(),
            nullable=False,
            comment="Field the rule matched (title, body, comments, ...).",
        ),
        sa.Column(
            "tagged_at", sa.Integer(), nullable=False, comment="Epoch seconds the tag was written."
        ),
        sa.ForeignKeyConstraint(
            ["post_pk"], ["posts.pk"], name=op.f("fk_post_themes_post_pk_posts"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["rule_pk"],
            ["theme_rules.pk"],
            name=op.f("fk_post_themes_rule_pk_theme_rules"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["theme_pk"],
            ["themes.pk"],
            name=op.f("fk_post_themes_theme_pk_themes"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_post_themes")),
        sa.UniqueConstraint(
            "post_pk", "theme_pk", "rule_pk", "matched_field", name="uq_post_themes_identity"
        ),
    )
    op.create_table(
        "runs",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column(
            "kind",
            sa.Text(),
            nullable=False,
            comment="Command kind (run, fetch, comments, reconcile, ...).",
        ),
        sa.Column(
            "trigger", sa.Text(), nullable=False, comment="Who started it; see RUN_TRIGGERS."
        ),
        sa.Column(
            "status", sa.Text(), nullable=False, comment="Lifecycle state; see RUN_STATUSES."
        ),
        sa.Column(
            "created_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds the row was created (queued or started).",
        ),
        sa.Column(
            "started_at",
            sa.Integer(),
            nullable=True,
            comment="Epoch seconds the process took the lock; NULL while queued.",
        ),
        sa.Column(
            "finished_at",
            sa.Integer(),
            nullable=True,
            comment="Epoch seconds of completion; NULL while running.",
        ),
        sa.Column(
            "heartbeat_at",
            sa.Integer(),
            nullable=True,
            comment="Epoch seconds of the last heartbeat; stale after 3 minutes.",
        ),
        sa.Column("pid", sa.Integer(), nullable=True, comment="Process id of the runner."),
        sa.Column(
            "stage",
            sa.Text(),
            nullable=True,
            comment="Current stage carried by the heartbeat (e.g. rate_wait:37s).",
        ),
        sa.Column(
            "options_json",
            sa.Text(),
            nullable=True,
            comment="Requested options as JSON, including the written reason for any bypass.",
        ),
        sa.Column(
            "counters_json",
            sa.Text(),
            nullable=True,
            comment="Outcome counters as JSON (new, updated, scrubbed, unknown_enum_values...).",
        ),
        sa.Column(
            "api_requests",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="HTTP requests counted by our own session hook.",
        ),
        sa.Column("app_version", sa.Text(), nullable=True, comment="insightminer version."),
        sa.Column("praw_version", sa.Text(), nullable=True, comment="PRAW version."),
        sa.Column("schema_rev", sa.Text(), nullable=True, comment="Alembic revision at run time."),
        sa.Column(
            "settings_fingerprint",
            sa.Text(),
            nullable=True,
            comment="Hash of the resolved non-secret settings.",
        ),
        sa.Column("error", sa.Text(), nullable=True, comment="Terminal error message, if any."),
        sa.Column("log_path", sa.Text(), nullable=True, comment="Path of the run's log file."),
        sa.Column(
            "purge_counts_json",
            sa.Text(),
            nullable=True,
            comment="Rows purged per table as JSON, so the row-count invariant can read them.",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'ok', 'partial', 'failed', 'rate_limited', "
            "'skipped_locked', 'crashed', 'cancelled')",
            name=op.f("ck_runs_status"),
        ),
        sa.CheckConstraint("trigger IN ('cli', 'ui', 'schedule')", name=op.f("ck_runs_trigger")),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_runs")),
    )
    op.create_table(
        "run_subreddits",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column("run_pk", sa.Integer(), nullable=False, comment="The run."),
        sa.Column("subreddit_pk", sa.Integer(), nullable=False, comment="The subreddit swept."),
        sa.Column(
            "pages",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Listing pages fetched.",
        ),
        sa.Column(
            "items_seen",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Items seen in the listing.",
        ),
        sa.Column(
            "new_items",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Posts inserted.",
        ),
        sa.Column(
            "updated_items",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
            comment="Posts updated.",
        ),
        sa.Column(
            "stop_reason",
            sa.Text(),
            nullable=True,
            comment="Why paging stopped; see STOP_REASONS. NULL while in progress.",
        ),
        sa.Column(
            "error", sa.Text(), nullable=True, comment="Error message when stop_reason=error."
        ),
        sa.CheckConstraint(
            "stop_reason IN ('exhausted', 'cap', 'error')",
            name=op.f("ck_run_subreddits_stop_reason"),
        ),
        sa.ForeignKeyConstraint(
            ["run_pk"], ["runs.pk"], name=op.f("fk_run_subreddits_run_pk_runs"), ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["subreddit_pk"],
            ["subreddits.pk"],
            name=op.f("fk_run_subreddits_subreddit_pk_subreddits"),
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_run_subreddits")),
        sa.UniqueConstraint("run_pk", "subreddit_pk", name="uq_run_subreddits_identity"),
    )
    op.create_table(
        "raw_rejects",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column("run_pk", sa.Integer(), nullable=False, comment="Run that saw it."),
        sa.Column("raw_json", sa.Text(), nullable=False, comment="The rejected item."),
        sa.Column("error", sa.Text(), nullable=False, comment="Why it was rejected."),
        sa.Column(
            "created_at",
            sa.Integer(),
            nullable=False,
            comment="Epoch seconds; rows older than 30 days are purged.",
        ),
        sa.ForeignKeyConstraint(
            ["run_pk"], ["runs.pk"], name=op.f("fk_raw_rejects_run_pk_runs"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_raw_rejects")),
    )
    op.create_table(
        "ui_state",
        sa.Column("key", sa.Text(), nullable=False, comment="State key."),
        sa.Column("value", sa.Text(), nullable=False, comment="State value (text)."),
        sa.Column(
            "updated_at", sa.Integer(), nullable=False, comment="Epoch seconds of the last write."
        ),
        sa.PrimaryKeyConstraint("key", name=op.f("pk_ui_state")),
    )
    op.create_table(
        "backups",
        sa.Column("pk", sa.Integer(), nullable=False, comment="Surrogate key."),
        sa.Column("path", sa.Text(), nullable=False, comment="Absolute path of the backup file."),
        sa.Column(
            "sha256", sa.Text(), nullable=False, comment="SHA-256 of the file after it was written."
        ),
        sa.Column("size_bytes", sa.Integer(), nullable=False, comment="File size."),
        sa.Column(
            "integrity",
            sa.Text(),
            nullable=False,
            comment="PRAGMA integrity_check result on the copy ('ok' or text).",
        ),
        sa.Column(
            "kind",
            sa.Text(),
            nullable=False,
            comment="daily, weekly, pre-migrate, manual or export.",
        ),
        sa.Column(
            "created_at", sa.Integer(), nullable=False, comment="Epoch seconds the backup finished."
        ),
        sa.Column(
            "schema_rev",
            sa.Text(),
            nullable=True,
            comment="Alembic revision of the database at backup time.",
        ),
        sa.Column(
            "table_counts_json",
            sa.Text(),
            nullable=True,
            comment="Row counts per table at backup time as JSON, for restore verification.",
        ),
        sa.PrimaryKeyConstraint("pk", name=op.f("pk_backups")),
        sa.UniqueConstraint("path", name=op.f("uq_backups_path")),
    )

    op.create_index("ix_subreddits_workspace_pk", "subreddits", ["workspace_pk"])
    op.create_index("ix_searches_workspace_pk", "searches", ["workspace_pk"])
    op.create_index("ix_themes_workspace_pk", "themes", ["workspace_pk"])
    op.create_index("ix_posts_next_check_at", "posts", ["next_check_at"])
    op.create_index("ix_posts_subreddit_pk_created_utc", "posts", ["subreddit_pk", "created_utc"])
    op.create_index("ix_posts_author_fullname", "posts", ["author_fullname"])
    op.create_index("ix_posts_content_state", "posts", ["content_state"])
    op.create_index(
        "ix_comments_post_pk_parent_comment_pk", "comments", ["post_pk", "parent_comment_pk"]
    )
    op.create_index("ix_comments_author_fullname", "comments", ["author_fullname"])
    op.create_index(
        "ix_item_snapshots_item_pk_fetched_at", "item_snapshots", ["item_pk", "fetched_at"]
    )
    op.create_index("ix_post_themes_theme_pk", "post_themes", ["theme_pk"])

    for statement in FTS_DDL:
        op.execute(statement)

    op.execute(SEED_WORKSPACE)


def downgrade() -> None:
    for statement in FTS_DROP_DDL:
        op.execute(statement)
    op.drop_table("backups")
    op.drop_table("ui_state")
    op.drop_table("raw_rejects")
    op.drop_table("run_subreddits")
    op.drop_table("runs")
    op.drop_table("post_themes")
    op.drop_table("authors")
    op.drop_table("item_snapshots")
    op.drop_table("post_sources")
    op.drop_table("comment_more")
    op.drop_table("comments")
    op.drop_table("posts")
    op.drop_table("theme_rules")
    op.drop_table("themes")
    op.drop_table("searches")
    op.drop_table("subreddits")
    op.drop_table("workspaces")
