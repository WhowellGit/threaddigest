"""section 19.6: ``sqlite3.connect`` is banned by ruff's ``TID251`` only package-wide for
``db/``, one level coarser than the rule reads. This gate AST-scans ``src/`` itself and
asserts the only ``import sqlite3`` / ``from sqlite3 import ...`` is ``db/backup.py``, with
a positive control proving the scanner can go red.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SRC_ROOT = Path(__file__).resolve().parents[2] / "src" / "threaddigest"

#: The one module allowed to import sqlite3 directly (design-round5.md section 10.1).
ALLOWED = "db/backup.py"


def _imports_sqlite3(path: Path) -> bool:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            if any(
                alias.name == "sqlite3" or alias.name.startswith("sqlite3.") for alias in node.names
            ):
                return True
        elif isinstance(node, ast.ImportFrom):
            if node.module == "sqlite3" or (node.module or "").startswith("sqlite3."):
                return True
    return False


def _offenders(root: Path) -> list[str]:
    return sorted(
        str(path.relative_to(root)).replace("\\", "/")
        for path in root.rglob("*.py")
        if _imports_sqlite3(path)
    )


def test_only_backup_module_imports_sqlite3() -> None:
    assert _offenders(SRC_ROOT) == [ALLOWED]


def test_the_scanner_catches_a_planted_import(tmp_path: Path) -> None:
    """Positive control: a scanner that finds nothing is not proof of anything."""
    fake_root = tmp_path / "threaddigest"
    fake_root.mkdir()
    (fake_root / "some_module.py").write_text("import sqlite3\n", encoding="utf-8")
    assert _offenders(fake_root) == ["some_module.py"]


@pytest.mark.parametrize(
    "source",
    ["import sqlite3", "import sqlite3 as sql3", "from sqlite3 import connect"],
)
def test_every_import_shape_is_caught(tmp_path: Path, source: str) -> None:
    path = tmp_path / "m.py"
    path.write_text(source + "\n", encoding="utf-8")
    assert _imports_sqlite3(path) is True


def test_an_unrelated_module_does_not_false_positive(tmp_path: Path) -> None:
    path = tmp_path / "m.py"
    path.write_text("import json\nfrom pathlib import Path\n", encoding="utf-8")
    assert _imports_sqlite3(path) is False
