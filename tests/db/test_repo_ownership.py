"""DB-21: the field-ownership declaration and the one upsert generator it drives agree.

design-round5.md §4.1-§4.3. Parametrized over **all three** ``OWNERSHIP`` rows (posts,
authors, post_sources) for the structural rules; ``test_recount_authors_touches_only_the_
derived_columns`` and ``test_scrubbed_at_is_never_written_in_tranche_a`` check the one row
each rule is actually about (§4.3 rules 8 and 9).

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

from insightminer.db.ownership import OWNERSHIP, IngestPath
from insightminer.db.repo import _upsert_for, recount_authors
from insightminer.db.schema import Base

OWNERSHIP_ROWS = list(OWNERSHIP.values())
OWNERSHIP_IDS = [f"{own.table}/{own.path.value}" for own in OWNERSHIP_ROWS]


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


def test_emitted_statement_matches_ownership(own: Any) -> None:
    """§4.3 rule 6: the compiled SQL says exactly what the declaration says."""
    sql = _compile(own)
    if not own.update_columns:
        assert " DO UPDATE SET " not in sql
        assert "DO NOTHING" in sql
    else:
        assert _set_clause_columns(sql) == set(own.update_columns)
    assert _conflict_target(sql) == tuple(own.conflict_columns)


def test_conflict_columns_match_a_real_unique_constraint(own: Any) -> None:
    """§4.3 rule 2: the ON CONFLICT target names a real UNIQUE constraint of the table."""
    table = Base.metadata.tables[own.table]
    unique_col_sets = {
        frozenset(c.name for c in constraint.columns)
        for constraint in table.constraints
        if isinstance(constraint, UniqueConstraint)
    }
    assert frozenset(own.conflict_columns) in unique_col_sets


def test_not_null_columns_are_inserted_and_pk_is_not(own: Any) -> None:
    """§4.3 rule 4 (as restated in round 5) and rule 5."""
    table = Base.metadata.tables[own.table]
    for column in table.columns:
        if column.primary_key:
            continue
        if not column.nullable and column.server_default is None:
            assert column.name in own.insert_columns, (
                f"{own.table}.{column.name} is NOT NULL with no server default "
                "and must be in insert_columns"
            )
    assert "pk" not in own.insert_columns


def test_monotonic_columns_are_emitted_as_max(own: Any) -> None:
    """§4.3 rule 7, asserted both ways so no row is exempt.

    A declared monotonic column's SET fragment must read ``max(<table>.<col>, ...)``, and
    nothing else in the statement may. The negative half is what keeps the two rows that
    declare no monotonic column honest: skipping them would leave them asserting nothing
    (and the skip ratchet is at zero).
    """
    sql = _compile(own)
    for name in own.monotonic_columns:
        assert f"max({own.table}.{name}" in sql
    assert sql.count("max(") == len(own.monotonic_columns), (
        "only declared monotonic columns may be emitted as max(...)"
    )
    for name in set(own.update_columns) - set(own.monotonic_columns):
        assert f"max({own.table}.{name}" not in sql


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
