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
import subprocess
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


# ------------------------------------------------- the reverse direction and hashes (2026-09-14)
#
# Widened after a fresh-context audit found seven gate files carrying ``@pytest.mark.gate(...)``
# with no ledger row -- G40 proved ledger -> test and nothing proved test -> ledger, so the
# quarterly review read a ledger describing a subset of the guards -- and one cited commit hash
# that no longer resolved, in the § Swept table, one commit after the commit that remapped
# hashes. Both are the same failure as the original: a register that reads as complete.

GATE_MARKER = re.compile(r"pytest\.mark\.gate\(\s*\"([^\"]+)\"\s*\)")
ID_COLUMN = "ID"
GATES_DIR = Path("tests") / "gates"
#: ``commit abc1234`` or a backticked hash; at least one letter, so a date is not a hash.
HASH_IN_PROSE = re.compile(r"(?:\bcommit\s+|`)([0-9a-f]{7,40})(?=`|\b)")
HASH_SOURCES = ("CLAUDE.md",)
HASH_GLOBS = ("docs/**/*.md", "memory-snapshot/*.md")
HASH_EXCLUDED = ("docs/reference/earlier-project-retrospectives/",)


def ledger_ids(text: str) -> set[str]:
    """Every id in an ``ID`` column; a cell such as ``G08/G09`` names two."""
    ids: set[str] = set()
    for _, cell in cells_under(text, ID_COLUMN):
        ids.update(part.strip() for part in re.split(r"[/,]", cell.strip("*` ")) if part.strip())
    return ids


def marker_ids(root: Path) -> list[tuple[str, str]]:
    """``(gate file, id)`` for every ``gate`` marker that names an id (space-separated ids)."""
    out: list[tuple[str, str]] = []
    for path in sorted((root / GATES_DIR).glob("test_*.py")):
        rel = path.relative_to(root).as_posix()
        for m in GATE_MARKER.finditer(path.read_text(encoding="utf-8")):
            out += [(rel, ident) for ident in m.group(1).split()]
    return out


def gate_files_missing_from_ledger(root: Path, ledger: str) -> list[str]:
    return [
        rel
        for path in sorted((root / GATES_DIR).glob("test_*.py"))
        if (rel := path.relative_to(root).as_posix()) not in ledger
    ]


def marker_ids_missing_from_ledger(root: Path, ledger: str) -> list[str]:
    ids = ledger_ids(ledger)
    return sorted({f"{rel}: {ident}" for rel, ident in marker_ids(root) if ident not in ids})


def cited_hashes(root: Path) -> list[tuple[str, int, str]]:
    """``(file, line, hash)`` for every commit hash cited in the curated documents."""
    files = [root / s for s in HASH_SOURCES] + [p for g in HASH_GLOBS for p in root.glob(g)]
    out: list[tuple[str, int, str]] = []
    for path in sorted({p for p in files if p.is_file()}):
        rel = path.relative_to(root).as_posix()
        if rel.startswith(HASH_EXCLUDED):
            continue
        text = strip_comments(path.read_text(encoding="utf-8"))
        for number, line in enumerate(text.splitlines(), start=1):
            out += [
                (rel, number, m.group(1))
                for m in HASH_IN_PROSE.finditer(line)
                if re.search(r"[a-f]", m.group(1))
            ]
    return out


def resolves_in_git(root: Path, sha: str) -> bool:
    proc = subprocess.run(
        ["git", "-C", str(root), "cat-file", "-e", f"{sha}^{{commit}}"],
        capture_output=True,
        timeout=60,
    )
    return proc.returncode == 0


def test_every_gate_file_and_marker_id_has_a_ledger_row() -> None:
    ledger = (ROOT / GUARDS).read_text(encoding="utf-8")
    missing_files = gate_files_missing_from_ledger(ROOT, ledger)
    missing_ids = marker_ids_missing_from_ledger(ROOT, ledger)
    assert not missing_files and not missing_ids, "gates with no row in GUARDS.md:\n" + "\n".join(
        missing_files + missing_ids
    )


def test_every_cited_commit_hash_resolves() -> None:
    found = [
        f"{rel}:{n}: {sha}" for rel, n, sha in cited_hashes(ROOT) if not resolves_in_git(ROOT, sha)
    ]
    assert not found, "commit hashes cited in documents that no longer exist:\n" + "\n".join(found)


@pytest.mark.gate("G40")
def test_positive_control_a_gate_file_or_marker_id_without_a_row_is_red(tmp_path: Path) -> None:
    gates = tmp_path / GATES_DIR
    gates.mkdir(parents=True)
    (gates / "test_a.py").write_text(
        "import pytest\n\n@pytest.mark." + 'gate("G01 G02")\ndef test_x() -> None:\n    pass\n',
        encoding="utf-8",
    )
    (gates / "test_b.py").write_text("def test_y() -> None:\n    pass\n", encoding="utf-8")
    ledger = "| ID | Name |\n|---|---|\n| G01 | a (`tests/gates/test_a.py`) |\n| G08/G09 | two |\n"
    assert gate_files_missing_from_ledger(tmp_path, ledger) == ["tests/gates/test_b.py"]
    assert marker_ids_missing_from_ledger(tmp_path, ledger) == ["tests/gates/test_a.py: G02"]
    assert ledger_ids(ledger) == {"G01", "G08", "G09"}


@pytest.mark.gate("G40")
def test_positive_control_a_dangling_commit_hash_is_red(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "CLAUDE.md").write_text(
        "see commit 0badc0d, `feedback-plan`, and `20260913`\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "x.md").write_text(
        "<!-- commit abcdef1 inside a comment is documentation -->\n`abcdef2` is a citation\n",
        encoding="utf-8",
    )
    assert cited_hashes(tmp_path) == [("CLAUDE.md", 1, "0badc0d"), ("docs/x.md", 2, "abcdef2")]
    assert not resolves_in_git(ROOT, "0badc0d")
    head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "--short", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()
    assert resolves_in_git(ROOT, head)


@pytest.mark.gate("G40")
def test_positive_control_a_guard_without_a_control_is_counted(tmp_path: Path) -> None:
    """The ratchet's ``guards_without_control`` ceiling counts Active rows and only those."""
    from tools.ratchet import measure_guards

    ledger = tmp_path / GUARDS
    ledger.parent.mkdir(parents=True)
    ledger.write_text(
        "# g\n\n## Active\n\n| ID | Positive control node |\n|---|---|\n"
        "| G1 | `tests/gates/test_a.py::test_x` |\n| G2 | none yet |\n"
        "| G3 | external control: pre-commit, seen red 2026-09-14 |\n\n"
        "## Retired\n\n| ID | Positive control node |\n|---|---|\n| G9 | none |\n",
        encoding="utf-8",
    )
    hits: list[str] = []
    notes: list[str] = []
    assert measure_guards(tmp_path, hits, notes) == 1
    assert len(hits) == 1 and "G2" in hits[0] and "guard-without-control" in hits[0]
