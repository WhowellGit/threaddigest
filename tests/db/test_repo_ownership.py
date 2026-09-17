"""DB-21: the field-ownership declaration and the one upsert generator it drives agree.

design-round5.md §4.1-§4.3. Parametrized over **every** ``OWNERSHIP`` row for the two
structural rules that hold whatever statement a path uses, and over the rows that actually
upsert for the rules about emitted SQL; ``test_recount_authors_touches_only_the_derived_
columns`` and ``test_scrubbed_at_is_never_written_in_tranche_a`` check the one row each rule
is actually about (§4.3 rules 8 and 9).

M1b added a third shape the declaration has to carry. ``("posts", COMMENTS)`` is
*update-only*: the tree stage never inserts a post, it stamps coverage and ladder columns on
a row the sweep inserted, so the rules that ask what an ``INSERT`` names have no premise on
it. Rather than let it pass those rules vacuously it declares ``upserts=False``, which is
its own assertion here (``test_an_update_only_row_declares_no_statement_of_its_own``) and
makes ``_upsert_for`` refuse to build a statement for it at all.

Round 4's declaration failed these same checks: ``authors``' emitted SET was
``{last_seen_at, name}`` against a declared ``{name, last_seen_at, post_count,
comment_count}`` (rule 6 False), and ``post_sources``' ``DO NOTHING`` statement raised
``IndexError`` when split on `` DO UPDATE SET `` (no such substring exists in it).
"""

from __future__ import annotations

from typing import Any

import pytest
from sqlalchemy import UniqueConstraint
from sqlalchemy.dialects import sqlite as sqlite_dialect

from threaddigest.core.models import CommentRow, PostRow
from threaddigest.db.ownership import OWNERSHIP, IngestPath
from threaddigest.db.repo import (
    AuthorWrite,
    CommentWrite,
    PostWrite,
    TreeStamp,
    _upsert_for,
    author_values,
    comment_values,
    post_source_values,
    post_values,
    recount_authors,
    tree_stamp_values,
)
from threaddigest.db.schema import Base


def _ids(rows: list[Any]) -> list[str]:
    return [f"{own.table}/{own.path.value}" for own in rows]


OWNERSHIP_ROWS = list(OWNERSHIP.values())
OWNERSHIP_IDS = _ids(OWNERSHIP_ROWS)
UPSERTING_ROWS = [own for own in OWNERSHIP_ROWS if own.upserts]
UPSERTING_IDS = _ids(UPSERTING_ROWS)
UPDATE_ONLY_ROWS = [own for own in OWNERSHIP_ROWS if not own.upserts]


def _split_top_level(text: str, sep: str) -> list[str]:
    """Split ``text`` on ``sep`` at paren-depth 0, so ``max(a, b)`` survives intact."""
    parts: list[str] = []
    depth = 0
    start = 0
    for i, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
        elif ch == sep and depth == 0:
            parts.append(text[start:i])
            start = i
    parts.append(text[start:])
    # the first split-off fragment has no leading separator; strip it from the rest
    return [parts[0]] + [p[len(sep) :] for p in parts[1:]]


def _set_clause_columns(sql: str) -> set[str]:
    """Column names set by a `` DO UPDATE SET `` clause, paren-depth aware (§4.3 rule 6)."""
    _, _, tail = sql.partition(" DO UPDATE SET ")
    fragments = _split_top_level(tail, ",")
    columns = set()
    for frag in fragments:
        name, _, _ = frag.partition("=")
        columns.add(name.strip())
    return columns


def _conflict_target(sql: str) -> tuple[str, ...]:
    _, _, after = sql.partition("ON CONFLICT (")
    target_text, _, _ = after.partition(")")
    return tuple(c.strip() for c in target_text.split(","))


def _compile(own: Any) -> str:
    stmt = _upsert_for(own.table, own.path)
    return str(stmt.compile(dialect=sqlite_dialect.dialect()))


@pytest.fixture(params=OWNERSHIP_ROWS, ids=OWNERSHIP_IDS)
def own(request: pytest.FixtureRequest) -> Any:
    return request.param


@pytest.fixture(params=UPSERTING_ROWS, ids=UPSERTING_IDS)
def upserting(request: pytest.FixtureRequest) -> Any:
    """The rows whose path reaches its table through ``_upsert_for``; §4.3's SQL rules."""
    return request.param


def test_ownership_covers_every_column(own: Any) -> None:
    """§4.3 rule 3: update | derived | never_update covers every column of the table."""
    table = Base.metadata.tables[own.table]
    declared = own.update_columns | own.derived_columns | own.never_update
    assert declared == {c.name for c in table.columns}


def test_update_derived_and_never_update_are_disjoint(own: Any) -> None:
    """§4.3 rule 1."""
    assert own.update_columns.isdisjoint(own.derived_columns)
    assert own.update_columns.isdisjoint(own.never_update)
    assert own.derived_columns.isdisjoint(own.never_update)


def test_emitted_statement_matches_ownership(upserting: Any) -> None:
    """§4.3 rule 6: the compiled SQL says exactly what the declaration says."""
    sql = _compile(upserting)
    if not upserting.update_columns:
        assert " DO UPDATE SET " not in sql
        assert "DO NOTHING" in sql
    else:
        assert _set_clause_columns(sql) == set(upserting.update_columns)
    assert _conflict_target(sql) == tuple(upserting.conflict_columns)


def test_conflict_columns_match_a_real_unique_constraint(upserting: Any) -> None:
    """§4.3 rule 2: the ON CONFLICT target names a real UNIQUE constraint of the table."""
    table = Base.metadata.tables[upserting.table]
    unique_col_sets = {
        frozenset(c.name for c in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert frozenset(upserting.conflict_columns) in unique_col_sets


def test_not_null_columns_are_inserted_and_pk_is_not(upserting: Any) -> None:
    """§4.3 rule 4 (as restated in round 5) and rule 5."""
    table = Base.metadata.tables[upserting.table]
    for column in table.columns:
        if column.primary_key:
            continue
        if not column.nullable and column.server_default is None:
            assert column.name in upserting.insert_columns, (
                f"{upserting.table}.{column.name} is NOT NULL with no server default "
                "and must be in insert_columns"
            )
    assert "pk" not in upserting.insert_columns


def test_monotonic_columns_are_emitted_as_max(upserting: Any) -> None:
    """§4.3 rule 7, asserted both ways so no row is exempt.

    A declared monotonic column's SET fragment must read ``max(<table>.<col>, ...)``, and
    nothing else in the statement may. The negative half is what keeps the two rows that
    declare no monotonic column honest: skipping them would leave them asserting nothing
    (and the skip ratchet is at zero).
    """
    sql = _compile(upserting)
    for name in upserting.monotonic_columns:
        assert f"max({upserting.table}.{name}" in sql
    assert sql.count("max(") == len(upserting.monotonic_columns), (
        "only declared monotonic columns may be emitted as max(...)"
    )
    for name in set(upserting.update_columns) - set(upserting.monotonic_columns):
        assert f"max({upserting.table}.{name}" not in sql


def test_terminal_guard_columns_are_emitted_as_a_case_on_the_terminal_state(
    upserting: Any,
) -> None:
    """§4.3 rule 7's sibling, added for M1b, asserted both ways for the same reason.

    A declared guarded column's SET fragment must read ``CASE WHEN <table>.content_state =
    ... THEN <table>.<col> ELSE excluded.<col> END``, and no other column in the statement
    may be written as a CASE. The negative half is what keeps the rows that guard nothing
    honest, and the count is what stops a guard being added to the SQL without being
    declared here.
    """
    sql = _compile(upserting)
    for name in upserting.terminal_guard_columns:
        assert f"THEN {upserting.table}.{name} ELSE excluded.{name} END" in sql
    assert sql.count("CASE WHEN") == len(upserting.terminal_guard_columns), (
        "only declared terminal-guard columns may be emitted as a CASE"
    )
    for name in set(upserting.update_columns) - set(upserting.terminal_guard_columns):
        assert f"THEN {upserting.table}.{name} " not in sql


def test_an_update_only_row_declares_no_statement_of_its_own() -> None:
    """A path that never inserts declares nothing for ``_upsert_for`` to build.

    Rules 2, 4, 5, 6 and 7 are about an emitted ``INSERT ... ON CONFLICT``; an update-only
    row would pass most of them by having nothing to check, which is the vacuous pass this
    project treats as a red. So it asserts the opposite shape instead -- no insert, no
    update, no conflict target, at least one column written by a named statement -- and that
    asking the generator for a statement raises rather than quietly emitting a ``DO NOTHING``
    that would look like a write path.
    """
    assert UPDATE_ONLY_ROWS, "no update-only row in the declaration; this test asserts nothing"
    for own in UPDATE_ONLY_ROWS:
        assert own.insert_columns == frozenset()
        assert own.update_columns == frozenset()
        assert own.conflict_columns == ()
        assert own.monotonic_columns == frozenset()
        assert own.terminal_guard_columns == frozenset()
        assert own.derived_columns, f"{own.table}/{own.path.value} writes nothing at all"
        with pytest.raises(ValueError, match="never inserts"):
            _upsert_for(own.table, own.path)


def test_ownership_covers_every_comments_column() -> None:
    """§4.3 rule 3 for the M1b table by name, beside the parametrized rule.

    ``comments`` is the table this milestone adds a write path to, and the rule that matters
    most on it is the one a new column silently escapes: every column falls in exactly one
    of update / derived / never_update. Named rather than left to the parametrized rule so
    that a declaration for ``comments`` deleted, renamed, or never written is a failure
    here, not a smaller parametrization nobody counts.
    """
    own = OWNERSHIP[("comments", IngestPath.COMMENTS)]
    table = Base.metadata.tables["comments"]
    assert own.update_columns | own.derived_columns | own.never_update == {
        c.name for c in table.columns
    }
    assert own.derived_columns == frozenset({"parent_comment_pk"})
    assert {"pk", "reddit_id", "post_pk", "parent_fullname", "created_utc", "first_seen_at"} <= (
        own.never_update
    )
    assert "scrubbed_at" in own.never_update
    assert "scrubbed_at" not in own.insert_columns


def _post_write() -> PostWrite:
    """One fully-populated ``PostWrite``, built field by field.

    Nothing is defaulted or spread from a helper: the point of the test below is that the
    builder's key set is checked against a declaration, so the input has to be a real
    ``PostWrite`` a sweep could produce rather than a mapping shaped to fit.
    """
    row = PostRow(
        reddit_id="abc123",
        fullname="t3_abc123",
        subreddit="premiere",
        subreddit_id="t5_2s9fq",
        author="editorguy",
        author_fullname="t2_abcd12",
        author_flair_text=None,
        author_is_bot=False,
        title="a title",
        selftext="a body",
        selftext_html="<p>a body</p>",
        url="https://example.com/x",
        domain="example.com",
        permalink="/r/premiere/comments/abc123/",
        created_utc=1_800_000_000,
        edited_utc=None,
        score=3,
        upvote_ratio=0.9,
        num_comments=1,
        link_flair_text=None,
        over_18=False,
        spoiler=False,
        is_self=True,
        is_video=False,
        is_gallery=False,
        post_hint=None,
        locked=False,
        stickied=False,
        archived=False,
        distinguished=None,
        crosspost_parent=None,
        num_crossposts=0,
        removed_by_category=None,
        source=IngestPath.SUBREDDIT_NEW.value,
    )
    return PostWrite(
        row=row,
        subreddit_pk=1,
        first_seen_at=1_800_000_000,
        last_fetched_at=1_800_000_000,
        next_check_at=1_800_086_400,
        check_stage=0,
        content_state="live",
        author_state="known",
        misses=0,
        raw_json="{}",
    )


def _comment_write() -> CommentWrite:
    """One fully-populated ``CommentWrite``, built field by field, for the same reason."""
    row = CommentRow(
        reddit_id="c1abc",
        fullname="t1_c1abc",
        post_reddit_id="abc123",
        parent_fullname="t3_abc123",
        author="helpful",
        author_fullname="t2_helper",
        author_is_bot=False,
        body="try the GPU renderer",
        body_html="<p>try the GPU renderer</p>",
        created_utc=1_800_000_100,
        edited_utc=None,
        score=4,
        depth=0,
        permalink="/r/premiere/comments/abc123/_/c1abc/",
        is_submitter=False,
        stickied=False,
        distinguished=None,
        source=IngestPath.COMMENTS.value,
    )
    return CommentWrite(row=row, post_pk=1, raw_json="{}")


VALUE_BUILDERS = [
    ("posts", IngestPath.SUBREDDIT_NEW, lambda: post_values(_post_write())),
    (
        "authors",
        IngestPath.SUBREDDIT_NEW,
        lambda: author_values(AuthorWrite(author_fullname="t2_a", name="a", seen_at=1)),
    ),
    (
        "post_sources",
        IngestPath.SUBREDDIT_NEW,
        lambda: post_source_values(post_pk=1, source_type="subreddit", source_pk=1, now=1),
    ),
    ("comments", IngestPath.COMMENTS, lambda: comment_values(_comment_write(), None, now=1)),
    (
        "authors",
        IngestPath.COMMENTS,
        lambda: author_values(AuthorWrite(author_fullname="t2_a", name="a", seen_at=1)),
    ),
]
BUILDER_IDS = [f"{table}/{path.value}" for table, path, _ in VALUE_BUILDERS]


@pytest.mark.parametrize("table,path,build", VALUE_BUILDERS, ids=BUILDER_IDS)
def test_value_builder_emits_exactly_the_declared_insert_columns(
    table: str, path: IngestPath, build: Any
) -> None:
    """§4.3 rule 4, the *value* half (panel P2-13).

    Every other rule here is about the emitted SQL; nothing compared the dictionaries the
    builders actually hand to it against ``insert_columns``. A column added to the
    declaration but not to the builder (or the reverse) therefore passed silently until an
    ``INSERT`` hit a NOT NULL at runtime. Asserted for every upserting row: set equality, so
    a drift in either direction is red.
    """
    assert set(build()) == set(OWNERSHIP[(table, path)].insert_columns)


def test_every_upserting_ownership_row_has_a_value_builder() -> None:
    """The rule above is only worth its parametrization if nothing can sit outside it.

    A new ingest path that declares ``insert_columns`` and no builder here would leave rule
    4's value half unasserted for exactly the statement nobody has run yet, which is the one
    that needs it.
    """
    declared = {(own.table, own.path) for own in UPSERTING_ROWS}
    assert {(table, path) for table, path, _ in VALUE_BUILDERS} == declared


def test_the_tree_stamp_writes_exactly_the_columns_its_row_declares() -> None:
    """Rule 4's value half, in the only form an update-only row can be given it.

    ``("posts", COMMENTS)`` emits no ``INSERT`` for the SQL rules to read, so what keeps its
    declaration honest is the mapping its named statement writes: a column added to
    ``derived_columns`` and not to ``repo.tree_stamp_values`` (or the reverse) would leave
    the declaration describing a write nobody makes.
    """
    stamp = TreeStamp(
        fetched_at=1_800_000_000,
        captured=12,
        complete=False,
        more_skipped=True,
        more_skipped_count=2,
        more_skipped_reason="budget",
        next_check_at=1_800_086_400,
        check_stage=1,
    )
    own = OWNERSHIP[("posts", IngestPath.COMMENTS)]
    assert set(tree_stamp_values(stamp)) == set(own.derived_columns)


def test_recount_authors_touches_only_the_derived_columns(
    engine: Any, workspace_pk: int, now: int
) -> None:
    """§4.3 rule 8 (behavioural half): ``recount_authors`` writes exactly the two columns
    ``OWNERSHIP[("authors", SUBREDDIT_NEW)].derived_columns`` names, and nothing else --
    a sentinel ``name`` / ``first_seen_at`` / ``last_seen_at`` survive the call untouched.
    """
    authors = Base.metadata.tables["authors"]
    fullname = "t2_recounttest"
    with engine.begin() as conn:
        conn.execute(
            authors.insert().values(
                author_fullname=fullname,
                name="sentinel-name",
                first_seen_at=1,
                last_seen_at=2,
                post_count=999,
                comment_count=999,
            )
        )

    with engine.begin() as conn:
        recount_authors(conn, [fullname])

    with engine.connect() as conn:
        row = (
            conn.execute(authors.select().where(authors.c.author_fullname == fullname))
            .mappings()
            .one()
        )

    derived = OWNERSHIP[("authors", IngestPath.SUBREDDIT_NEW)].derived_columns
    assert derived == frozenset({"post_count", "comment_count"})
    assert row["name"] == "sentinel-name"
    assert row["first_seen_at"] == 1
    assert row["last_seen_at"] == 2
    # No posts/comments reference this author, so a real recount must zero the counts --
    # proof the statement actually ran rather than the row being untouched by accident.
    assert row["post_count"] == 0
    assert row["comment_count"] == 0


def test_scrubbed_at_is_never_written_in_tranche_a() -> None:
    """§4.3 rule 9: for posts/SUBREDDIT_NEW specifically."""
    own = OWNERSHIP[("posts", IngestPath.SUBREDDIT_NEW)]
    assert {"first_seen_at", "check_stage", "next_check_at", "scrubbed_at"} <= own.never_update
    assert "scrubbed_at" not in own.insert_columns
