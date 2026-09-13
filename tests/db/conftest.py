"""Fixtures for the database tests: a temp DB migrated to head, and row builders."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any

import pytest
from alembic.config import Config
from sqlalchemy import Engine, text

from insightminer.db.engine import engine_for
from insightminer.db.schema_dump import alembic_config as _alembic_config
from insightminer.db.schema_dump import migrate_to_head

NOW = 1_800_000_000  # a fixed epoch second, well inside the project's lifetime


@pytest.fixture
def now() -> int:
    """The fixed epoch second the row builders stamp on rows."""
    return NOW


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    return tmp_path / "insightminer.db"


@pytest.fixture
def engine(db_path: Path) -> Iterator[Engine]:
    """A read-write engine on a temp database migrated to head through the Alembic API."""
    eng = engine_for(db_path)
    try:
        migrate_to_head(eng)
        yield eng
    finally:
        eng.dispose()


# --- pytest-alembic fixtures ---------------------------------------------------------------


@pytest.fixture
def alembic_config() -> Config:
    """Bind pytest-alembic to this package's migrations."""
    return _alembic_config()


@pytest.fixture
def alembic_engine(tmp_path: Path) -> Iterator[Engine]:
    """pytest-alembic runs the history on a fresh temp database through the project engine."""
    eng = engine_for(tmp_path / "alembic.db")
    try:
        yield eng
    finally:
        eng.dispose()


# --- row builders ---------------------------------------------------------------------------


@pytest.fixture
def workspace_pk(engine: Engine) -> int:
    """The seeded default workspace (migration 0001 inserts ``premiere``)."""
    with engine.connect() as conn:
        pk = conn.execute(text("SELECT pk FROM workspaces WHERE slug = 'premiere'")).scalar_one()
    return int(pk)


@pytest.fixture
def subreddit_pk(engine: Engine, workspace_pk: int) -> int:
    """One monitored subreddit row to hang posts on."""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                "INSERT INTO subreddits (workspace_pk, name_lower, display_name, added_at) "
                "VALUES (:ws, 'premiere', 'premiere', :now)"
            ),
            {"ws": workspace_pk, "now": NOW},
        )
    return int(result.lastrowid)


def _post_values(reddit_id: str, subreddit_pk: int, **overrides: Any) -> dict[str, Any]:
    values: dict[str, Any] = {
        "reddit_id": reddit_id,
        "fullname": f"t3_{reddit_id}",
        "subreddit_pk": subreddit_pk,
        "author": "someone",
        "author_fullname": "t2_someone",
        "title": f"title {reddit_id}",
        "selftext": f"body {reddit_id}",
        "url": f"https://www.reddit.com/r/premiere/comments/{reddit_id}/",
        "permalink": f"/r/premiere/comments/{reddit_id}/",
        "created_utc": NOW - 3600,
        "first_seen_at": NOW,
        "last_fetched_at": NOW,
        "next_check_at": NOW + 86_400,
        "source": "subreddit_new",
        "normalizer_version": 1,
        "raw_json": "{}",
        "content_state": "live",
        "removed_by_category": None,
    }
    values.update(overrides)
    return values


PostInserter = Callable[..., int]


@pytest.fixture
def insert_post(engine: Engine, subreddit_pk: int) -> PostInserter:
    """Insert a minimal live post (override any column); returns its pk."""

    def _insert(reddit_id: str, **overrides: Any) -> int:
        values = _post_values(reddit_id, subreddit_pk, **overrides)
        columns = ", ".join(values)
        params = ", ".join(f":{name}" for name in values)
        with engine.begin() as conn:
            result = conn.execute(text(f"INSERT INTO posts ({columns}) VALUES ({params})"), values)
        return int(result.lastrowid)

    return _insert


@pytest.fixture
def insert_comment(engine: Engine) -> PostInserter:
    """Insert a minimal live comment under ``post_pk`` (override any column); returns its pk."""

    def _insert(reddit_id: str, post_pk: int, **overrides: Any) -> int:
        values: dict[str, Any] = {
            "reddit_id": reddit_id,
            "fullname": f"t1_{reddit_id}",
            "post_pk": post_pk,
            "parent_fullname": "t3_parent",
            "author": "commenter",
            "author_fullname": "t2_commenter",
            "body": f"comment body {reddit_id}",
            "created_utc": NOW - 1800,
            "first_seen_at": NOW,
            "last_fetched_at": NOW,
            "source": "comments",
            "normalizer_version": 1,
            "raw_json": "{}",
            "content_state": "live",
        }
        values.update(overrides)
        columns = ", ".join(values)
        params = ", ".join(f":{name}" for name in values)
        with engine.begin() as conn:
            result = conn.execute(
                text(f"INSERT INTO comments ({columns}) VALUES ({params})"), values
            )
        return int(result.lastrowid)

    return _insert
