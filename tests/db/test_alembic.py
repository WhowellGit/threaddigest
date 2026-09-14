"""Migration history tests: pytest-alembic built-ins plus project-specific guarantees."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from alembic import command
from alembic.script import ScriptDirectory
from pytest_alembic.tests import (  # noqa: F401 - collected by pytest
    test_model_definitions_match_ddl,
    test_single_head_revision,
    test_up_down_consistency,
    test_upgrade,
)
from sqlalchemy import Engine, func, select, text
from sqlalchemy.dialects.sqlite import insert

from insightminer.db.engine import engine_for
from insightminer.db.fts import fts_membership_count, integrity_check
from insightminer.db.migrate import head_revision
from insightminer.db.schema import Base, Post
from insightminer.db.schema_dump import alembic_config, migrate_to_head

NOW = 1_800_000_000  # matches the conftest row builders

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "db"
FIXTURE_PATHS = sorted(FIXTURES_DIR.glob("*.sqlite"))
FIXTURE_MANIFEST: dict[str, Any] = json.loads(
    (FIXTURES_DIR / "manifest.json").read_text(encoding="utf-8")
)


def test_foreign_keys_off_inside_migration_and_clean_after(tmp_path: Path) -> None:
    """env.py issues PRAGMA foreign_keys=OFF before the transaction, and restores it after."""
    seen: list[int] = []

    def probe(ctx: Any, **_kwargs: Any) -> None:
        seen.append(int(ctx.connection.exec_driver_sql("PRAGMA foreign_keys").scalar()))

    engine = engine_for(tmp_path / "fk.db")
    try:
        cfg = alembic_config()
        cfg.attributes["connection"] = engine
        cfg.attributes["on_version_apply"] = probe
        command.upgrade(cfg, "head")
        # One probe per revision applied, so the expected length moves with the history;
        # what is asserted is the invariant, not the count: every revision ran with
        # foreign-key enforcement off, and at least one revision ran.
        assert seen, "the probe never fired: no revision was applied"
        assert set(seen) == {0}, f"foreign_keys must read 0 while a migration runs, saw {seen}"
        with engine.connect() as conn:
            # Same pooled DBAPI connection env.py used: proves the pragma was switched back.
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
            assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []
            assert conn.exec_driver_sql("PRAGMA integrity_check").scalar() == "ok"
    finally:
        engine.dispose()


def _post_values(reddit_id: str, subreddit_pk: int, *, score: int, seen_at: int) -> dict[str, Any]:
    return {
        "reddit_id": reddit_id,
        "fullname": f"t3_{reddit_id}",
        "subreddit_pk": subreddit_pk,
        "title": f"title {score}",
        "created_utc": NOW - 3600,
        "score": score,
        "first_seen_at": seen_at,
        "last_fetched_at": seen_at,
        "next_check_at": seen_at + 86_400,
        "source": "subreddit_new",
        "normalizer_version": 1,
        "raw_json": "{}",
    }


def _identity(engine: Engine) -> tuple[int, int, int, int]:
    with engine.connect() as conn:
        pk, first_seen_at, score = conn.execute(
            text("SELECT pk, first_seen_at, score FROM posts WHERE reddit_id = 'up1'")
        ).one()
        max_pk, count = conn.execute(text("SELECT max(pk), count(*) FROM posts")).one()
        assert max_pk == count, "max(pk) == count(*) is the PK-stability invariant"
    return int(pk), int(first_seen_at), int(score), int(count)


def test_on_conflict_upsert_preserves_pk_and_first_seen_at(
    engine: Engine, subreddit_pk: int
) -> None:
    results = []
    for i in range(3):
        values = _post_values("up1", subreddit_pk, score=i, seen_at=NOW + i)
        stmt = insert(Post).values(values)
        stmt = stmt.on_conflict_do_update(
            index_elements=["reddit_id"],
            set_={
                "score": stmt.excluded.score,
                "title": stmt.excluded.title,
                "last_fetched_at": stmt.excluded.last_fetched_at,
            },
        )
        with engine.begin() as conn:
            conn.execute(stmt)
        results.append(_identity(engine))
    pks = {r[0] for r in results}
    first_seen = {r[1] for r in results}
    assert pks == {1}
    assert first_seen == {NOW}
    assert results[-1][2] == 2
    with engine.connect() as conn:
        assert fts_membership_count(conn, "posts_fts") == 1
        assert integrity_check(conn, "posts_fts")


@pytest.mark.gate
def test_insert_or_replace_burns_the_pk_and_detaches_fts(engine: Engine, subreddit_pk: int) -> None:
    """Positive control: the forbidden upsert form does exactly the damage the plan describes."""
    columns = list(_post_values("x", 1, score=0, seen_at=0))
    sql = text(
        f"INSERT OR REPLACE INTO posts ({', '.join(columns)}) "
        f"VALUES ({', '.join(':' + c for c in columns)})"
    )
    pks = []
    for i in range(3):
        with engine.begin() as conn:
            conn.execute(sql, _post_values("up1", subreddit_pk, score=i, seen_at=NOW + i))
        with engine.connect() as conn:
            pk, first_seen_at = conn.execute(
                text("SELECT pk, first_seen_at FROM posts WHERE reddit_id = 'up1'")
            ).one()
        pks.append(int(pk))
        assert first_seen_at == NOW + i, "REPLACE overwrote first_seen_at"
    assert pks == [1, 2, 3], "REPLACE deletes and re-inserts, burning a pk each time"
    with engine.connect() as conn:
        max_pk, count = conn.execute(text("SELECT max(pk), count(*) FROM posts")).one()
        assert (max_pk, count) == (3, 1)
        # REPLACE's implicit delete fires no delete trigger (recursive_triggers is off), so
        # the two burned pks stay in the index: detached FTS rows.
        assert fts_membership_count(conn, "posts_fts") == 3
        assert not integrity_check(conn, "posts_fts")


# --- DB-44 / DB-45 / G17: the fixture-database set (§10.4, §2.2) ---------------------------


@pytest.mark.parametrize("fixture_path", FIXTURE_PATHS, ids=lambda p: p.stem)
def test_revision_fixture_upgrades_clean(fixture_path: Path, tmp_path: Path) -> None:
    """DB-44 / G17: every fixture in ``tests/fixtures/db/`` upgrades to head without losing a
    row from any table it seeded, with ``foreign_key_check`` clean afterwards.

    The 0001 fixture seeds ``run_subreddits`` and ``raw_rejects`` alongside ``runs`` (§10.4),
    so this parametrization is not vacuous for the §10.4 cascade: if
    ``db/migrations/env.py::_set_foreign_keys`` ever stopped disabling foreign keys before a
    batch recreate, the 0001 case here would go red, not just the standalone positive control
    in ``tests/db/test_migrate_revisions.py``.
    """
    revision = fixture_path.stem
    manifest = FIXTURE_MANIFEST[revision]["row_counts"]
    working_copy = tmp_path / fixture_path.name
    working_copy.write_bytes(fixture_path.read_bytes())

    engine = engine_for(working_copy)
    try:
        migrate_to_head(engine)

        with engine.connect() as conn:
            head = conn.execute(text("SELECT version_num FROM alembic_version")).scalar_one()
            assert head == head_revision(), "the fixture did not reach the current head"
            assert conn.exec_driver_sql("PRAGMA foreign_key_check").all() == []

            for table, seeded in manifest.items():
                if table not in Base.metadata.tables:
                    continue
                after = conn.execute(
                    select(func.count()).select_from(Base.metadata.tables[table])
                ).scalar_one()
                assert after >= seeded, f"{table} lost rows upgrading the {revision} fixture"

            # §10.4 step-1 assertion 7: both FTS indexes still match their live counts.
            for base_table, fts_table in (("posts", "posts_fts"), ("comments", "comments_fts")):
                base = Base.metadata.tables[base_table]
                live = conn.execute(
                    select(func.count()).select_from(base).where(base.c.content_state == "live")
                ).scalar_one()
                assert live >= 1, f"{base_table} must seed a live row or this check is vacuous"
                assert fts_membership_count(conn, fts_table) == live
                assert integrity_check(conn, fts_table)
    finally:
        engine.dispose()


def test_fixture_set_equals_non_head_revisions() -> None:
    """DB-45: every non-head revision has exactly one fixture database, named by its id, and
    no fixture exists for a revision that no longer needs one (the head itself, or a revision
    since removed).
    """
    script_dir = ScriptDirectory.from_config(alembic_config())
    heads = set(script_dir.get_heads())
    all_revisions = {rev.revision for rev in script_dir.walk_revisions()}
    non_head_revisions = all_revisions - heads

    fixture_revisions = {p.stem for p in FIXTURE_PATHS}
    assert fixture_revisions == non_head_revisions
    assert fixture_revisions == set(FIXTURE_MANIFEST)


def test_every_table_seeded_in_each_fixture(tmp_path: Path) -> None:
    """DB-45: each fixture's manifest declares a seeded row count for every table
    ``Base.metadata`` knows about, and the row is really there -- so the DB-44 parametrization
    cannot be vacuous for any table, the way round 3's rev-0001 fixture would have been for
    ``run_subreddits`` and ``raw_rejects``.

    Reads a copy of each fixture, never the packaged file directly: even a read-only
    ``engine_for`` connection can leave a WAL/SHM sidecar next to it (SQLite's journal_mode
    pragma runs at connect time), and the packaged fixture must stay byte-identical.
    """
    for fixture_path in FIXTURE_PATHS:
        manifest = FIXTURE_MANIFEST[fixture_path.stem]["row_counts"]
        missing = sorted(set(Base.metadata.tables) - set(manifest))
        assert missing == [], f"{fixture_path.name}: manifest is missing {missing}"

        working_copy = tmp_path / fixture_path.name
        working_copy.write_bytes(fixture_path.read_bytes())
        engine = engine_for(working_copy)
        try:
            with engine.connect() as conn:
                for table, expected in manifest.items():
                    if table not in Base.metadata.tables:
                        continue
                    actual = conn.execute(
                        select(func.count()).select_from(Base.metadata.tables[table])
                    ).scalar_one()
                    assert actual == expected, f"{fixture_path.name}: {table}"
                    assert actual >= 1, f"{fixture_path.name}: {table} has no seeded row"
        finally:
            engine.dispose()
