"""G54: the harness page's inventory block is derived from the tree, never narrated.

Birth incident (documentation-practices assessment, 2026-09-13, and Wes's ask of 2026-09-15 for
a harness document of this project's own): the earlier project's hand-written harness document
was never opened after it was written and drifted to naming a mechanism deleted weeks earlier.
Here the mechanisms are files, so the inventory is rendered from them by
``tools/harness_page.py`` and this gate goes red when the committed block and the tree disagree:
a new hook script, gate file, ratchet key, rule file, skill, tool, or ``make`` target that is
not reflected on the page fails ``make check`` until the block is regenerated.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from tools import harness_page

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.gate("G54")


def test_the_page_exists_with_markers() -> None:
    text = (ROOT / harness_page.PAGE).read_text(encoding="utf-8")
    assert harness_page.split_page(text) is not None, f"{harness_page.PAGE} lacks the markers"


def test_committed_block_matches_the_tree() -> None:
    found = harness_page.problems(ROOT)
    assert not found, "\n".join(found)


def _mini_tree(tmp_path: Path) -> Path:
    """A small repository shape: one hook script, one gate file, one ratchet, the page."""
    root = tmp_path / "repo"
    (root / "tools" / "hooks").mkdir(parents=True)
    (root / "tools" / "hooks" / "a.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    (root / ".claude").mkdir()
    settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": '"$D"/tools/hooks/a.sh'}],
                }
            ]
        }
    }
    (root / ".claude" / "settings.json").write_text(json.dumps(settings), encoding="utf-8")
    (root / "tests" / "gates").mkdir(parents=True)
    (root / "tests" / "gates" / "test_one.py").write_text("# GUARDS.md\n", encoding="utf-8")
    (root / ".ratchets").mkdir()
    (root / ".ratchets" / "x.txt").write_text("k=1\nk.hard_after=2026-01-01\n", encoding="utf-8")
    (root / "docs" / "runbook").mkdir(parents=True)
    (root / "docs" / "runbook" / "GUARDS.md").write_text(
        "# L\n\n## Active\n\n| ID | N |\n|---|---|\n| G01 | a |\n| G02 | b |\n\n"
        "## Retired\n\n| ID | N |\n|---|---|\n| | |\n",  # a placeholder row is not a row
        encoding="utf-8",
    )
    page = root / harness_page.PAGE
    page.write_text(
        "# H\n\nprose\n\n" + harness_page.render(root) + "\nmore prose\n", encoding="utf-8"
    )
    return root


def test_render_reads_the_mechanisms(tmp_path: Path) -> None:
    root = _mini_tree(tmp_path)
    block = harness_page.render(root)
    assert "- `tools/hooks/a.sh`: PreToolUse `Bash`" in block
    assert "`test_one`" in block
    assert "- `.ratchets/x.txt`: `k`" in block  # the hard_after line is not a key
    assert "Active 2" in block and "Retired 0" in block
    assert "`docs/runbook/GUARDS.md`: read by `test_one.py`" in block
    assert harness_page.problems(root) == []


def test_positive_control_a_new_hook_script_makes_the_page_stale(tmp_path: Path) -> None:
    root = _mini_tree(tmp_path)
    (root / "tools" / "hooks" / "b.sh").write_text("#!/bin/sh\n", encoding="utf-8")
    found = harness_page.problems(root)
    assert found and found[0].endswith("inventory block is stale:")
    assert any("b.sh" in line and "NOT REGISTERED" in line for line in found)
    # --write repairs it and keeps the prose on both sides of the block.
    harness_page.write(root)
    text = (root / harness_page.PAGE).read_text(encoding="utf-8")
    assert text.startswith("# H\n\nprose\n\n") and text.endswith("\nmore prose\n")
    assert harness_page.problems(root) == []


def test_positive_control_missing_page_or_markers_is_red(tmp_path: Path) -> None:
    root = _mini_tree(tmp_path)
    page = root / harness_page.PAGE
    page.write_text("# H\n\nno markers here\n", encoding="utf-8")
    assert harness_page.problems(root) == [
        f"{harness_page.PAGE} has no {harness_page.BEGIN} … {harness_page.END} markers"
    ]
    shutil.rmtree(root / "docs")
    assert harness_page.problems(root) == [f"{harness_page.PAGE} is missing"]
