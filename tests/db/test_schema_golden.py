"""The packaged schema.sql is byte-identical to a fresh head database, and one normalizer
produces the same fingerprint from either side."""

from __future__ import annotations

import difflib

import pytest
from sqlalchemy import Engine, text

from insightminer.db.schema_dump import (
    SCHEMA_SQL,
    canonical,
    dump_schema,
    fingerprint,
    normalize_ws,
)


def test_dump_of_fresh_head_db_equals_packaged_schema_sql(engine: Engine) -> None:
    live = dump_schema(engine)
    packaged = SCHEMA_SQL.read_text(encoding="utf-8")
    if live != packaged:
        diff = "".join(
            difflib.unified_diff(
                packaged.splitlines(keepends=True),
                live.splitlines(keepends=True),
                fromfile="schema.sql (packaged)",
                tofile="live head database",
            )
        )
        pytest.fail(
            "schema.sql is stale: run `uv run python -m insightminer.db.schema_dump`\n" + diff
        )


def test_fingerprint_of_live_db_equals_fingerprint_of_file(engine: Engine) -> None:
    assert fingerprint(dump_schema(engine)) == fingerprint(SCHEMA_SQL.read_text(encoding="utf-8"))


def test_dump_has_head_and_data_dictionary(engine: Engine) -> None:
    rendered = dump_schema(engine)
    assert rendered.startswith("-- head: 0001\n")
    assert "-- COLUMN COMMENTS\n" in rendered
    assert "-- posts.next_check_at: " in rendered
    assert "CREATE VIRTUAL TABLE posts_fts USING fts5(" in rendered
    assert "posts_fts_docsize" not in rendered, "FTS shadow tables are not part of the schema"
    assert "sqlite_sequence" not in rendered


def test_dump_is_a_fixed_point_of_the_normalizer(engine: Engine) -> None:
    rendered = dump_schema(engine)
    assert canonical(rendered) + "\n" == rendered


def test_fingerprint_ignores_line_endings_and_indentation() -> None:
    file_text = SCHEMA_SQL.read_text(encoding="utf-8")
    crlf = file_text.replace("\n", "\r\n")
    indented = "\n".join("    " + line for line in file_text.splitlines())
    assert fingerprint(crlf) == fingerprint(file_text) == fingerprint(indented)


@pytest.mark.gate
def test_fingerprint_goes_red_when_the_live_schema_drifts(engine: Engine) -> None:
    """Positive control: a column added outside a migration changes the fingerprint."""
    before = fingerprint(dump_schema(engine))
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE ui_state ADD COLUMN drift TEXT"))
    assert fingerprint(dump_schema(engine)) != before


def test_normalize_ws_preserves_quoted_regions() -> None:
    assert normalize_ws("  a   b\n\tc ") == "a b c"
    assert normalize_ws("x 'a   b' y") == "x 'a   b' y"
    assert normalize_ws('x "a\tb" y') == 'x "a\tb" y'
    assert normalize_ws("x [a  b] y") == "x [a  b] y"
    assert normalize_ws("x 'it''s  ok' y") == "x 'it''s  ok' y"
