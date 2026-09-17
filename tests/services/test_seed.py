"""``services/seed.py``: ``config/seed.yaml`` applied idempotently and scoped to one
workspace (design-round5.md §2.1, §10.3 step 7 / T14, §18.6).

``services/seed.py`` does not exist yet -- every test here is expected to fail on
``ModuleNotFoundError`` until step 6 implements it.

Tranche A seeds ``subreddits`` only, not themes (Wes's scoped decision, §18.6): the shipped
``config/seed.yaml`` also carries a ``themes:`` key, and a seed file that ignores it without
raising is part of the contract this file pins.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from sqlalchemy import Engine, insert

from threaddigest.db import repo
from threaddigest.db.schema import Base
from threaddigest.services import seed


def _write_seed(path: Path, *, subreddits: list[str], with_themes: bool = False) -> Path:
    payload: dict[str, object] = {"subreddits": subreddits}
    if with_themes:
        payload["themes"] = [{"name": "Crashes", "match": ["crash", "crashes"]}]
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(payload, handle)
    return path


def test_apply_seed_inserts_every_configured_subreddit(
    engine: Engine, tmp_path: Path, now: int
) -> None:
    seed_path = _write_seed(tmp_path / "seed.yaml", subreddits=["Premiere", "VideoEditing"])
    with engine.connect() as conn:
        workspace_pk = repo.default_workspace_pk(conn)

    with engine.begin() as conn:
        added = seed.apply_seed(conn, workspace_pk=workspace_pk, now=now, seed_path=seed_path)

    assert added == 2
    with engine.connect() as conn:
        rows = repo.enabled_subreddits(conn, workspace_pk)
    assert {row.name_lower for row in rows} == {"premiere", "videoediting"}


def test_apply_seed_is_idempotent(engine: Engine, tmp_path: Path, now: int) -> None:
    seed_path = _write_seed(tmp_path / "seed.yaml", subreddits=["premiere", "editors"])
    with engine.connect() as conn:
        workspace_pk = repo.default_workspace_pk(conn)

    with engine.begin() as conn:
        first = seed.apply_seed(conn, workspace_pk=workspace_pk, now=now, seed_path=seed_path)
    with engine.begin() as conn:
        second = seed.apply_seed(conn, workspace_pk=workspace_pk, now=now + 60, seed_path=seed_path)

    assert first == 2
    assert second == 0
    with engine.connect() as conn:
        rows = repo.enabled_subreddits(conn, workspace_pk)
    assert len(rows) == 2


def test_apply_seed_merges_case_insensitively_with_an_existing_row(
    engine: Engine, tmp_path: Path, now: int
) -> None:
    """``ON CONFLICT(workspace_pk, name_lower) DO NOTHING`` (§10.3 step 7): a source already
    present under a different casing is not duplicated."""
    seed_path = _write_seed(tmp_path / "seed.yaml", subreddits=["PREMIERE"])
    with engine.connect() as conn:
        workspace_pk = repo.default_workspace_pk(conn)
    with engine.begin() as conn:
        repo.seed_subreddits(conn, workspace_pk=workspace_pk, names=["premiere"], now=now)

    with engine.begin() as conn:
        added = seed.apply_seed(conn, workspace_pk=workspace_pk, now=now, seed_path=seed_path)

    assert added == 0
    with engine.connect() as conn:
        rows = repo.enabled_subreddits(conn, workspace_pk)
    assert len(rows) == 1


def test_apply_seed_ignores_the_themes_key(engine: Engine, tmp_path: Path, now: int) -> None:
    """§18.6: seeding themes is narrowed out of tranche A. A ``themes:`` key must not raise,
    and the M1a schema has no table it could seed into even if it tried."""
    seed_path = _write_seed(tmp_path / "seed.yaml", subreddits=["premiere"], with_themes=True)
    with engine.connect() as conn:
        workspace_pk = repo.default_workspace_pk(conn)

    with engine.begin() as conn:
        added = seed.apply_seed(conn, workspace_pk=workspace_pk, now=now, seed_path=seed_path)

    assert added == 1


def test_apply_seed_is_scoped_to_the_given_workspace(
    engine: Engine, tmp_path: Path, now: int
) -> None:
    """Seeding one workspace must not touch a second one, even if it shares a source name
    (``Subreddit`` is one row per ``(workspace, subreddit)`` -- §5.1)."""
    seed_path = _write_seed(tmp_path / "seed.yaml", subreddits=["premiere"])
    workspaces = Base.metadata.tables["workspaces"]
    with engine.begin() as conn:
        other_pk = conn.execute(
            insert(workspaces)
            .values(slug="other", name="Other", ranking="distinct_authors", created_at=now)
            .returning(workspaces.c.pk)
        ).scalar_one()
    with engine.connect() as conn:
        default_pk = repo.default_workspace_pk(conn)

    with engine.begin() as conn:
        added = seed.apply_seed(conn, workspace_pk=other_pk, now=now, seed_path=seed_path)

    assert added == 1
    with engine.connect() as conn:
        default_rows = repo.enabled_subreddits(conn, default_pk)
        other_rows = repo.enabled_subreddits(conn, int(other_pk))
    assert default_rows == []
    assert {row.name_lower for row in other_rows} == {"premiere"}


def test_apply_seed_with_no_seed_path_reads_the_shipped_config_file(
    engine: Engine, now: int
) -> None:
    """The default is the real ``config/seed.yaml`` -- the file ``db init`` actually reads
    (§10.3 step 7) and ``config/seed.yaml``'s six subreddits (D-37; §11.7's demo-fixture
    coupling)."""
    with engine.connect() as conn:
        workspace_pk = repo.default_workspace_pk(conn)

    with engine.begin() as conn:
        added = seed.apply_seed(conn, workspace_pk=workspace_pk, now=now)

    assert added == 6
    with engine.connect() as conn:
        rows = repo.enabled_subreddits(conn, workspace_pk)
    assert {row.name_lower for row in rows} == {
        "premiere",
        "premierepro",
        "editors",
        "videoediting",
        "aftereffects",
        "aivideo",
    }


def test_apply_seed_rejects_an_empty_subreddit_list(
    engine: Engine, tmp_path: Path, now: int
) -> None:
    seed_path = _write_seed(tmp_path / "seed.yaml", subreddits=[])
    with engine.connect() as conn:
        workspace_pk = repo.default_workspace_pk(conn)

    with engine.begin() as conn:
        added = seed.apply_seed(conn, workspace_pk=workspace_pk, now=now, seed_path=seed_path)

    assert added == 0


# --- the malformed-file branches: a bad seed must fail loudly, never seed nothing quietly -----


def test_read_seed_names_of_an_empty_file_is_empty(tmp_path: Path) -> None:
    path = tmp_path / "seed.yaml"
    path.write_text("", encoding="utf-8")
    assert seed.read_seed_names(path) == []


def test_read_seed_names_refuses_a_file_whose_top_level_is_not_a_mapping(tmp_path: Path) -> None:
    """A bare list is the natural typo for this file's shape. Refusing it is the point: a
    seed that silently added nothing would leave ``db init`` reporting ``ok`` over a
    workspace with no sources."""
    path = tmp_path / "seed.yaml"
    path.write_text("- premiere\n- editors\n", encoding="utf-8")
    with pytest.raises(TypeError, match="must be a mapping"):
        seed.read_seed_names(path)


def test_read_seed_names_refuses_subreddits_that_is_not_a_list_of_strings(tmp_path: Path) -> None:
    path = tmp_path / "seed.yaml"
    path.write_text("subreddits:\n  premiere: true\n", encoding="utf-8")
    with pytest.raises(TypeError, match="list of strings"):
        seed.read_seed_names(path)
