"""G33: ``docs/INDEX.md`` and ``docs/**/*.md`` must agree in both directions.

A router that drifts from the tree is worse than no router. The check is structural: every
bullet under "Documents in this corpus" names a file that exists, every markdown file under
``docs/`` is listed exactly once, and nothing is listed twice.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
SECTION = "## Documents in this corpus"
BULLET = re.compile(r"^- `([^`]+\.md)`")


def listed_paths(index_text: str) -> list[str]:
    section = index_text.split(SECTION, 1)[1]
    return [m.group(1) for line in section.splitlines() if (m := BULLET.match(line))]


def on_disk(docs: Path) -> set[str]:
    return {p.relative_to(docs).as_posix() for p in docs.rglob("*.md")}


def diff(docs: Path) -> tuple[set[str], set[str], list[str]]:
    listed = listed_paths((docs / "INDEX.md").read_text(encoding="utf-8"))
    dupes = sorted({p for p in listed if listed.count(p) > 1})
    disk = on_disk(docs)
    return set(listed) - disk, disk - set(listed), dupes


def test_index_matches_docs_tree() -> None:
    missing, unlisted, dupes = diff(DOCS)
    assert not missing, f"INDEX lists files that do not exist: {sorted(missing)}"
    assert not unlisted, f"files under docs/ not listed in INDEX: {sorted(unlisted)}"
    assert not dupes, f"listed more than once: {dupes}"


@pytest.mark.gate
def test_positive_control_orphan_ghost_and_duplicate(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "INDEX.md").write_text(
        f"# x\n\n{SECTION}\n\n- `INDEX.md` — router\n- `ghost.md` — missing\n- `ghost.md` — dup\n",
        encoding="utf-8",
    )
    (docs / "orphan.md").write_text("orphan\n", encoding="utf-8")
    missing, unlisted, dupes = diff(docs)
    assert missing == {"ghost.md"}
    assert unlisted == {"orphan.md"}
    assert dupes == ["ghost.md"]
