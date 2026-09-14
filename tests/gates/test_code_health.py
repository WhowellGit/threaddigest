"""G51: the code-health measurement counts planted offenders, names each one, and refuses to
run without its analyzers (a missing tool is red, never a zero).

``tools/code_health.py`` is run the way ``make check`` runs it (a subprocess with the same
interpreter) against a throwaway tree that plants one offender per count: a function too
knotty on every axis, a module too large to keep maintainability rank A, a dead function, a
whitelisted one, and a block duplicated across two modules.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.gate("G51")

REPO_ROOT = Path(__file__).resolve().parents[2]
TOOL = REPO_ROOT / "tools" / "code_health.py"
PACKAGE = Path("src") / "insightminer"

CLEAN = '''"""A clean module."""


def used(x: int) -> int:
    return x + 1


RESULT = used(1)


def listed_but_unused() -> None:
    """Whitelisted on purpose: the positive control for the counted whitelist."""
'''

DUPLICATE = '''"""Planted duplicate: the same block lives in two modules."""


def same_{name}(items):
    out = []
    for item in items:
        if item is None:
            continue
        if isinstance(item, str):
            out.append(item.strip())
        elif isinstance(item, int):
            out.append(str(item))
        else:
            out.append(repr(item))
    return out


USED = (same_{name},)
'''

WHITELIST = """# Dead-code whitelist for the throwaway tree.
from insightminer import clean

WHITELISTED = (
    clean.listed_but_unused,  # planted: counted by dead_code_whitelisted, not by dead_code
)
"""


def knotty_module() -> str:
    """One function over every function-level threshold: seven arguments (PLR0913), sixteen
    branches (PLR0912), cognitive 16 and cyclomatic 17; plus a dead function."""
    branches = "\n".join(f"    if a == {i}:\n        total += {i}" for i in range(16))
    return (
        '"""Planted offenders."""\n\n\n'
        "def tangled(a, b, c, d, e, f, g):\n"
        "    total = b + c + d + e + f + g\n"
        f"{branches}\n"
        "    return total\n\n\n"
        "def never_called():\n"
        "    return 1\n\n\n"
        "USED = (tangled,)\n"
    )


def huge_module() -> str:
    """Three hundred small branchy functions: far too much volume for rank A, none of them
    complex on its own, all referenced so vulture does not count them."""
    parts = ['"""Planted: too large and branchy to keep maintainability rank A."""', ""]
    parts.extend(
        f"def f{i}(x):\n    if x > {i}:\n        return x - {i}\n    return x + {i}\n\n"
        for i in range(300)
    )
    parts.append("USED = (" + ", ".join(f"f{i}" for i in range(300)) + ")\n")
    return "\n".join(parts)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    pkg = root / PACKAGE
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "clean.py").write_text(CLEAN, encoding="utf-8")
    (pkg / "knotty.py").write_text(knotty_module(), encoding="utf-8")
    (pkg / "huge.py").write_text(huge_module(), encoding="utf-8")
    (pkg / "dup_a.py").write_text(DUPLICATE.format(name="a"), encoding="utf-8")
    (pkg / "dup_b.py").write_text(DUPLICATE.format(name="b"), encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tools").mkdir()
    (root / "tools" / "vulture_whitelist.py").write_text(WHITELIST, encoding="utf-8")
    return root


def run_tool(
    root: Path, *args: str, env: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(TOOL), "--root", str(root), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
        timeout=300,
        env=env,
    )


def report(root: Path) -> dict[str, object]:
    return json.loads((root / ".build" / "code_health.json").read_text(encoding="utf-8"))


def test_planted_offenders_are_counted_and_named(project: Path) -> None:
    proc = run_tool(project)
    assert proc.returncode == 0, proc.stderr
    data = report(project)
    assert data["values"] == {
        "cognitive_over_15": 1,
        "cyclomatic_over_15": 1,
        "mi_below_a": 1,
        "size_rule_violations": 2,
        "dead_code": 1,
        "dead_code_whitelisted": 1,
        "duplicate_blocks": 1,
    }
    hits = "\n".join(str(hit) for hit in data["hits"])
    assert "knotty.py tangled cognitive 16" in hits
    assert "knotty.py:4 tangled cyclomatic 17" in hits
    assert "huge.py maintainability" in hits and "rank" in hits
    assert "PLR0913" in hits and "PLR0912" in hits
    assert "knotty.py:" in hits and "unused function never_called" in hits
    assert "tools/vulture_whitelist.py:5 clean.listed_but_unused" in hits
    assert "dup_" in hits and "duplicate-code" in hits
    assert proc.stdout.count("HIT       ") == len(data["hits"])
    assert "code_health.cognitive_over_15" in proc.stdout


def test_a_clean_tree_measures_zero_except_the_whitelist(project: Path) -> None:
    for name in ("knotty.py", "huge.py", "dup_a.py", "dup_b.py"):
        (project / PACKAGE / name).unlink()
    proc = run_tool(project)
    assert proc.returncode == 0, proc.stderr
    values = report(project)["values"]
    assert values == {
        "cognitive_over_15": 0,
        "cyclomatic_over_15": 0,
        "mi_below_a": 0,
        "size_rule_violations": 0,
        "dead_code": 0,
        "dead_code_whitelisted": 1,
        "duplicate_blocks": 0,
    }


def test_a_missing_analyzer_is_red_not_zero(project: Path, tmp_path: Path) -> None:
    """Fail, never skip: without its analyzers the tool exits non-zero and writes no report,
    so the ratchet cannot read a zero that means nothing."""
    empty = tmp_path / "no-bin"
    empty.mkdir()
    env = {**os.environ, "PATH": str(empty)}
    proc = run_tool(project, "--bin-dir", str(empty), env=env)
    assert proc.returncode != 0
    assert "analyzer 'complexipy' not found" in proc.stderr
    assert not (project / ".build" / "code_health.json").exists()
