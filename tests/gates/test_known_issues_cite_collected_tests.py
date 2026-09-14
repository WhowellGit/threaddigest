"""G40: a regression test or positive control cited in the runbook must exist.

Birth incident (Wes, 2026-09-13): a written rule is not enforcement. ``KNOWN_ISSUES.md`` says
every fixed bug points at its regression test and ``GUARDS.md`` says every guard names the
positive control that proves it can go red, but nothing checked that either node id still
resolved. A renamed or deleted test would leave the register reading green while the thing it
cites had evaporated -- the "installed-ness, not existence" failure, one level up.

Resolution is structural and offline: the file is parsed with ``ast`` and the named function (or
``Class::method``) must be defined in it, so the check costs no pytest collection subprocess and
cannot be fooled by a collection error elsewhere. A parametrised id (``name[case]``) resolves on
the function name. ``::name`` on its own continues the previous path in the same cell, which is
how ``GUARDS.md`` lists a second control from the same file. HTML comments are stripped first
(with their line breaks kept, so line numbers stay true), because the format example in
``KNOWN_ISSUES.md`` is documentation, not a row.
"""

from __future__ import annotations

import ast
import re
from collections.abc import Iterable
from pathlib import Path

import pytest
from tools.ratchet import is_separator_row, split_row

ROOT = Path(__file__).resolve().parents[2]
KNOWN_ISSUES = Path("docs") / "runbook" / "KNOWN_ISSUES.md"
GUARDS = Path("docs") / "runbook" / "GUARDS.md"
ISSUES_COLUMN = "Regression test (node id)"
GUARDS_COLUMN = "Positive control node"
COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
NODE = re.compile(r"tests/[\w./-]+\.py(?:::[\w.\[\]-]+)*|::[\w.\[\]-]+")


def strip_comments(text: str) -> str:
    """Drop HTML comments, keeping their newlines so reported line numbers stay true."""
    return COMMENT.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def cells_under(text: str, column: str) -> list[tuple[int, str]]:
    """``(line number, cell)`` for that column of every markdown table that declares it."""
    found: list[tuple[int, str]] = []
    index: int | None = None
    for number, line in enumerate(strip_comments(text).splitlines(), start=1):
        cells = split_row(line)
        if not cells:
            index = None
        elif column in cells:
            index = cells.index(column)
        elif index is not None and index < len(cells) and not is_separator_row(cells):
            found.append((number, cells[index]))
    return found


def defines(tree: ast.Module, names: list[str]) -> bool:
    """True when ``names`` is a chain of definitions in ``tree`` (``Class::method``)."""
    body: list[ast.stmt] = tree.body
    for name in names:
        wanted = name.split("[", 1)[0]
        node = next(
            (
                stmt
                for stmt in body
                if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef)
                and stmt.name == wanted
            ),
            None,
        )
        if node is None:
            return False
        body = node.body
    return True


def _split_node(node_id: str, previous: str | None) -> tuple[str | None, list[str]]:
    if node_id.startswith("::"):
        return previous, node_id.lstrip(":").split("::")
    path, _, tail = node_id.partition("::")
    return path, tail.split("::") if tail else []


def unresolved(root: Path, doc: Path, column: str) -> list[str]:
    """Every node id in that column of ``doc`` that does not name something that exists."""
    problems: list[str] = []
    for number, cell in cells_under((root / doc).read_text(encoding="utf-8"), column):
        previous: str | None = None
        for node_id in NODE.findall(cell.replace("`", "")):
            path, names = _split_node(node_id, previous)
            where = f"{doc.as_posix()}:{number}"
            if path is None:
                problems.append(f"{where}: {node_id} continues a path that is not in the cell")
                continue
            previous = path
            file = root / path
            if not file.is_file():
                problems.append(f"{where}: {path} does not exist")
            elif names and not defines(ast.parse(file.read_text(encoding="utf-8")), names):
                problems.append(f"{where}: {path} defines no {'::'.join(names)}")
    return problems


def test_every_known_issues_row_cites_a_regression_test_that_exists() -> None:
    problems = unresolved(ROOT, KNOWN_ISSUES, ISSUES_COLUMN)
    assert not problems, "KNOWN_ISSUES.md cites tests that do not exist:\n" + "\n".join(problems)


def test_every_guards_positive_control_node_exists() -> None:
    problems = unresolved(ROOT, GUARDS, GUARDS_COLUMN)
    assert not problems, "GUARDS.md cites controls that do not exist:\n" + "\n".join(problems)


def test_the_registers_cite_at_least_one_node_each() -> None:
    """A parser that silently found no rows would pass both checks above forever."""
    issues = cells_under((ROOT / KNOWN_ISSUES).read_text(encoding="utf-8"), ISSUES_COLUMN)
    guards = cells_under((ROOT / GUARDS).read_text(encoding="utf-8"), GUARDS_COLUMN)
    assert [cell for _, cell in issues if "::" in cell], "no node id parsed from KNOWN_ISSUES.md"
    assert [cell for _, cell in guards if "::" in cell], "no node id parsed from GUARDS.md"


def _register(tmp_path: Path, rows: Iterable[str]) -> Path:
    root = tmp_path
    (root / "tests").mkdir(parents=True)
    (root / "tests" / "test_real.py").write_text(
        "class TestThing:\n    def test_method(self):\n        pass\n\n\n"
        "def test_ok():\n    pass\n",
        encoding="utf-8",
    )
    (root / "docs" / "runbook").mkdir(parents=True)
    (root / KNOWN_ISSUES).write_text(
        "# known issues\n\n| ID | Symptom | Regression test (node id) | Status |\n"
        "|---|---|---|---|\n" + "".join(rows) + "\n<!-- | KI-0XX | example |"
        " tests/web/test_ghost.py::test_example | fixed | -->\n",
        encoding="utf-8",
    )
    return root


@pytest.mark.gate("G40")
def test_positive_control_a_dangling_node_id_is_red(tmp_path: Path) -> None:
    root = _register(
        tmp_path,
        [
            "| KI-1 | a | tests/test_real.py::test_ok | fixed |\n",
            "| KI-2 | b | tests/test_real.py::TestThing::test_method | fixed |\n",
            "| KI-3 | c | tests/test_real.py::test_renamed_away | fixed |\n",
            "| KI-4 | d | tests/test_deleted.py::test_gone | fixed |\n",
            "| KI-5 | e |  | open |\n",
        ],
    )

    problems = unresolved(root, KNOWN_ISSUES, ISSUES_COLUMN)

    assert len(problems) == 2, problems
    assert problems[0].endswith("tests/test_real.py defines no test_renamed_away")
    assert problems[1].endswith("tests/test_deleted.py does not exist")


@pytest.mark.gate("G40")
def test_positive_control_a_second_control_from_the_same_file_resolves(tmp_path: Path) -> None:
    root = _register(tmp_path, ["| KI-1 | a | `tests/test_real.py::test_ok`, `::test_ok` | f |\n"])
    assert unresolved(root, KNOWN_ISSUES, ISSUES_COLUMN) == []

    root = _register(
        tmp_path / "b", ["| KI-1 | a | `tests/test_real.py::test_ok`, `::nope` | f |\n"]
    )
    assert unresolved(root, KNOWN_ISSUES, ISSUES_COLUMN) == [
        "docs/runbook/KNOWN_ISSUES.md:5: tests/test_real.py defines no nope"
    ]
