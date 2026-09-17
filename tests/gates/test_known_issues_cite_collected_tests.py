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
``KNOWN_ISSUES.md`` is documentation, not a row; since 2026-09-16 every row-shaped line must be
one the parser returned, because the strip had hidden thirteen real rows (KI-034).
"""

from __future__ import annotations

import ast
import re
import subprocess
from collections.abc import Iterable, Mapping
from pathlib import Path

import pytest
from tools.hash_remap import load_remap, successors
from tools.ratchet import is_separator_row, split_row

ROOT = Path(__file__).resolve().parents[2]
KNOWN_ISSUES = Path("docs") / "runbook" / "KNOWN_ISSUES.md"
GUARDS = Path("docs") / "runbook" / "GUARDS.md"
DECISIONS = Path("docs") / "decisions" / "DECISIONS.md"
CLAIMS = Path("docs") / "reference" / "reviews" / "templates" / "claims.md"
TEST_STRATEGY = Path("docs") / "TEST_STRATEGY.md"
ISSUES_COLUMN = "Regression test (node id)"
GUARDS_COLUMN = "Positive control node"
CLAIMS_COLUMN = "Backed by (node id)"
STRATEGY_COLUMN = "Reason if cut/changed"
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


def duplicate_ids(text: str, pattern: str) -> list[str]:
    """Ids that head more than one table row (``KI-009``, ``G23``): a register whose ids are not
    unique cannot be cited. Birth incident 2026-09-14: two open rows reused KI-005 and KI-006,
    which already named fixed bugs, and nothing noticed."""
    seen: dict[str, int] = {}
    for line in strip_comments(text).splitlines():
        cells = split_row(line)
        match = re.match(pattern, cells[0]) if cells else None
        if match:
            seen[match.group(0)] = seen.get(match.group(0), 0) + 1
    return sorted(key for key, count in seen.items() if count > 1)


def test_register_ids_are_unique() -> None:
    issues = duplicate_ids((ROOT / KNOWN_ISSUES).read_text(encoding="utf-8"), r"KI-\d+")
    guards = duplicate_ids((ROOT / GUARDS).read_text(encoding="utf-8"), r"G\d+(?:/G\d+)*")
    decisions = duplicate_ids((ROOT / DECISIONS).read_text(encoding="utf-8"), r"[DN]-\d+")
    assert not issues, "KNOWN_ISSUES.md reuses ids: " + ", ".join(issues)
    assert not guards, "GUARDS.md reuses ids: " + ", ".join(guards)
    assert not decisions, "DECISIONS.md reuses ids: " + ", ".join(decisions)


def test_positive_control_a_reused_id_is_red() -> None:
    table = "| ID | Date |\n|---|---|\n| KI-001 | a |\n| KI-002 | b |\n| KI-001 | c |\n"
    assert duplicate_ids(table, r"KI-\d+") == ["KI-001"]
    assert duplicate_ids(table.replace("| KI-001 | c |", "| KI-003 | c |"), r"KI-\d+") == []


def test_every_known_issues_row_cites_a_regression_test_that_exists() -> None:
    problems = unresolved(ROOT, KNOWN_ISSUES, ISSUES_COLUMN)
    assert not problems, "KNOWN_ISSUES.md cites tests that do not exist:\n" + "\n".join(problems)


def test_every_guards_positive_control_node_exists() -> None:
    problems = unresolved(ROOT, GUARDS, GUARDS_COLUMN)
    assert not problems, "GUARDS.md cites controls that do not exist:\n" + "\n".join(problems)


def test_every_claim_cites_a_test_that_exists() -> None:
    """The claims list travels in every external review packet (2026-09-14); a claim backed by
    a test that does not exist would send a reviewer chasing a ghost."""
    problems = unresolved(ROOT, CLAIMS, CLAIMS_COLUMN)
    assert not problems, "claims.md cites tests that do not exist:\n" + "\n".join(problems)


def test_every_test_strategy_citation_exists() -> None:
    """The test-strategy rows name the shipped test for each spec item; the test-methodology
    seat (external round one panel, 2026-09-15) found several fresh citations lived only here,
    ungated, so a renamed test would rot silently. Now every node id in the strategy's
    Reason/Status column must resolve, like the other registers."""
    problems = unresolved(ROOT, TEST_STRATEGY, STRATEGY_COLUMN)
    assert not problems, "TEST_STRATEGY.md cites tests that do not exist:\n" + "\n".join(problems)


def test_the_registers_cite_at_least_one_node_each() -> None:
    """A parser that silently found no rows would pass the checks above forever."""
    issues = cells_under((ROOT / KNOWN_ISSUES).read_text(encoding="utf-8"), ISSUES_COLUMN)
    guards = cells_under((ROOT / GUARDS).read_text(encoding="utf-8"), GUARDS_COLUMN)
    claims = cells_under((ROOT / CLAIMS).read_text(encoding="utf-8"), CLAIMS_COLUMN)
    assert [cell for _, cell in issues if "::" in cell], "no node id parsed from KNOWN_ISSUES.md"
    assert [cell for _, cell in guards if "::" in cell], "no node id parsed from GUARDS.md"
    assert [cell for _, cell in claims if "::" in cell], "no node id parsed from claims.md"


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


# --------------------------------------------------- rows the parser never reached (2026-09-16)
#
# Birth incident (KI-034): thirteen rows, KI-015 to KI-027, had been appended inside the HTML
# comment that holds the runbook's format example, by sessions that added a row at the end of what
# looked like the table without noticing that the comment opened above the example and closed
# fifteen lines below it, and three more, KI-028 to KI-030, below the blank line that ended
# the table. ``strip_comments`` dropped the thirteen before parsing -- rightly for the
# example, whose test does not exist -- and the blank line cut the other three off, so the
# checks above resolved nothing for any of the sixteen, the page did not render them, and
# the rule the register enforces was unenforced for every one. A parser that
# silently skips a row is the register-that-reads-as-complete failure one level down, so every
# row-shaped line must now be one the parser returned.

#: A register row's first cell: a real id, or the placeholder the format example uses, however
#: decorated (bold, backticked), after a blockquote mark, or after a comment opener and any text
#: before the first pipe (``<!-- | KI-0XX | ... | -->`` on one line is still that row). The review
#: seat of 2026-09-16 planted the decorated and the prefixed forms and found them unseen.
KI_SHAPED = re.compile(r"^\s*(?:<!--[^|]*)?(?:>\s*)*\|\s*[*`]*(KI-(?:\d+|0[Xx]{2}))[*`]*\s*\|")
#: The same first cell found anywhere on a line rather than only at its start. Everything above
#: is keyed on the line, so a row written onto the end of another row's line is a row no check
#: has an opinion about: Markdown renders it as extra columns of the first, ``cells_under``
#: returns the first row's cell for that line number, and ``KI_SHAPED`` stops at the first id.
#: The landing seat of 2026-09-16 found KI-029 living that way on the end of KI-028's line, seen
#: by neither the parser nor the widened check above.
KI_ANYWHERE = re.compile(r"\|\s*[*`]*(KI-(?:\d+|0[Xx]{2}))[*`]*\s*\|")
EXAMPLE_ID = "KI-0XX"


def commented_lines(text: str) -> set[int]:
    """Line numbers that fall inside an HTML comment, both ends inclusive."""
    inside: set[int] = set()
    for match in COMMENT.finditer(text):
        first = text.count("\n", 0, match.start()) + 1
        last = text.count("\n", 0, match.end()) + 1
        inside.update(range(first, last + 1))
    return inside


def rows_the_parser_missed(text: str, column: str) -> list[str]:
    """Every row-shaped line that ``cells_under`` did not return for ``column``, with why.

    One line may escape: the format example, whose id is the placeholder ``KI-0XX``, inside a
    comment, once. A real id inside a comment, a row cut off from its table by a blank line or
    sitting under a header without the column, a second placeholder, or the placeholder outside
    the comment is reported with its line number.
    """
    parsed = {number for number, _ in cells_under(text, column)}
    inside = commented_lines(text)
    missed: list[str] = []
    example_seen = False
    for number, line in enumerate(text.splitlines(), start=1):
        match = KI_SHAPED.match(line)
        if not match or number in parsed:
            continue
        ident = match.group(1)
        if ident.upper() == EXAMPLE_ID and number in inside and not example_seen:
            example_seen = True
        elif ident.upper() == EXAMPLE_ID:
            missed.append(
                f"{number}: {ident} is the format example; one is allowed, inside the comment"
            )
        elif number in inside:
            missed.append(
                f"{number}: {ident} sits inside an HTML comment, where the gate cannot see it"
            )
        else:
            missed.append(f"{number}: {ident} is outside every table that declares '{column}'")
    return missed


def parsed_rows_the_shape_missed(text: str, column: str) -> list[str]:
    """The floor under the row shape: every row the parser returned for ``column`` must also
    match ``KI_SHAPED``, so a shape that quietly stops matching real ids is red here rather than
    blind in ``rows_the_parser_missed`` (the review seat narrowed the shape to one digit and the
    check above saw nothing and passed)."""
    lines = text.splitlines()
    return [
        f"{number}: {split_row(lines[number - 1])[0]} is a parsed row the row shape does not match"
        for number, _ in cells_under(text, column)
        if not KI_SHAPED.match(lines[number - 1])
    ]


def rows_sharing_a_line(text: str) -> list[str]:
    """Every id written onto a line that already carries a row, which is a row in nobody's sight.

    The two checks above are keyed on the line number, so they can only ever have an opinion
    about the first row on a line. A second one is rendered as extra columns of the first, and
    the parser hands the first row's regression-test cell to the citation check, so the second
    row's citation is resolved by nothing and its absence is reported by nothing.
    """
    found: list[str] = []
    for number, line in enumerate(text.splitlines(), start=1):
        found += [
            f"{number}: {match.group(1)} is written onto another row's line, where it is neither "
            "a row the parser returns nor a cell any check reads"
            for match in list(KI_ANYWHERE.finditer(line))[1:]
        ]
    return found


def test_every_known_issues_row_is_in_the_parsed_table() -> None:
    """The checks above see only what the parser returns; a row it never reached is a row the
    rule is not enforced for. The second assertion is the floor: the shape sees every parsed row,
    so the first assertion cannot pass by seeing nothing. The third closes the gap both leave,
    a row sharing a physical line with the row in front of it (the landing seat, 2026-09-16)."""
    text = (ROOT / KNOWN_ISSUES).read_text(encoding="utf-8")
    missed = rows_the_parser_missed(text, ISSUES_COLUMN)
    assert not missed, "KNOWN_ISSUES.md rows the gate cannot see:\n" + "\n".join(missed)
    unshaped = parsed_rows_the_shape_missed(text, ISSUES_COLUMN)
    assert not unshaped, "KNOWN_ISSUES.md rows the row shape misses:\n" + "\n".join(unshaped)
    doubled = rows_sharing_a_line(text)
    assert not doubled, "KNOWN_ISSUES.md rows sharing a line:\n" + "\n".join(doubled)


@pytest.mark.gate("G40")
def test_positive_control_a_row_the_parser_cannot_see_is_red() -> None:
    """Each way a row escapes the parser is planted and named; the clean shape is silent."""
    table = f"| ID | {ISSUES_COLUMN} |\n|---|---|\n| KI-101 | tests/a.py::t |\n"
    example = "<!-- example:\n| KI-0XX | tests/x.py::t |\n-->\n"
    assert rows_the_parser_missed(table + example, ISSUES_COLUMN) == []
    assert parsed_rows_the_shape_missed(table + example, ISSUES_COLUMN) == []

    hidden = table + "<!-- example:\n| KI-0XX | tests/x.py::t |\n| KI-102 | tests/a.py::t |\n-->\n"
    assert rows_the_parser_missed(hidden, ISSUES_COLUMN) == [
        "6: KI-102 sits inside an HTML comment, where the gate cannot see it"
    ]
    cut_off = table + "\n| KI-103 | tests/a.py::t |\n" + example
    assert rows_the_parser_missed(cut_off, ISSUES_COLUMN) == [
        f"5: KI-103 is outside every table that declares '{ISSUES_COLUMN}'"
    ]
    twice = table + example + "<!-- | KI-0XX | tests/y.py::t | -->\n"
    assert rows_the_parser_missed(twice, ISSUES_COLUMN) == [
        "7: KI-0XX is the format example; one is allowed, inside the comment"
    ]
    stray = table + "\n| KI-0xx | tests/x.py::t |\n"
    assert rows_the_parser_missed(stray, ISSUES_COLUMN) == [
        "5: KI-0xx is the format example; one is allowed, inside the comment"
    ]
    other_header = table + "\n| ID | Symptom |\n|---|---|\n| KI-104 | no test column |\n"
    assert rows_the_parser_missed(other_header, ISSUES_COLUMN) == [
        f"7: KI-104 is outside every table that declares '{ISSUES_COLUMN}'"
    ]
    decorated = (
        table + example + "<!-- note | **KI-105** | t | -->\n> | `KI-106` | t |\n|KI-107|t|\n"
    )
    assert rows_the_parser_missed(decorated, ISSUES_COLUMN) == [
        "7: KI-105 sits inside an HTML comment, where the gate cannot see it",
        f"8: KI-106 is outside every table that declares '{ISSUES_COLUMN}'",
        f"9: KI-107 is outside every table that declares '{ISSUES_COLUMN}'",
    ]
    assert commented_lines("a\n<!-- b\nc -->\nd\n<!-- e -->\n") == {2, 3, 5}


@pytest.mark.gate("G40")
def test_positive_control_a_second_row_on_one_line_is_red() -> None:
    """The shape that found KI-029 on the end of KI-028's line, driven both ways: the doubled
    line is named wherever it sits, and the ordinary one-row-per-line file is silent.

    The two rows are the real ones this repository carried on 2026-09-16, cut down to the two
    cells the checks read, so the control is red against the shape of the defect rather than
    against a shape invented for it.
    """
    header = f"| ID | {ISSUES_COLUMN} |\n|---|---|\n"
    first = "| KI-028 | tests/gates/test_doc_policy.py::t | fixed |"
    second = "| KI-029 | tests/services/test_probe.py::t | fixed |"
    assert rows_sharing_a_line(header + first + "\n" + second + "\n") == []
    assert rows_sharing_a_line(header + first + second + "\n") == [
        "3: KI-029 is written onto another row's line, where it is neither a row the parser "
        "returns nor a cell any check reads"
    ]
    # Inside the table it is invisible to both checks above, which is why this one exists.
    doubled = header + first + second + "\n"
    assert rows_the_parser_missed(doubled, ISSUES_COLUMN) == []
    assert parsed_rows_the_shape_missed(doubled, ISSUES_COLUMN) == []
    # And outside it, where the parser misses the line, only the first row is ever named.
    cut_off = header + "\n" + first + second + "\n"
    assert rows_the_parser_missed(cut_off, ISSUES_COLUMN) == [
        f"4: KI-028 is outside every table that declares '{ISSUES_COLUMN}'"
    ]
    assert rows_sharing_a_line(cut_off) == [
        "4: KI-029 is written onto another row's line, where it is neither a row the parser "
        "returns nor a cell any check reads"
    ]


@pytest.mark.gate("G40")
def test_positive_control_a_parsed_row_the_shape_misses_is_red() -> None:
    """A parsed row whose id the shape does not match is named, so the shape cannot narrow
    itself past the rows it exists to see."""
    table = f"| ID | {ISSUES_COLUMN} |\n|---|---|\n| KI-101 | tests/a.py::t |\n| G40 | t |\n"
    assert parsed_rows_the_shape_missed(table, ISSUES_COLUMN) == [
        "4: G40 is a parsed row the row shape does not match"
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
#: The memory snapshot left the tree on 2026-09-16 (D-35): it is private, and a citation in it
#: is checked by nothing here because nothing here can read it. The documents are the corpus.
HASH_GLOBS = ("docs/**/*.md",)
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
    """True when ``sha`` names a commit that is an ancestor of ``HEAD``.

    Existence is not enough: after a history rewrite the old objects can linger in the object
    store (or come back with a fetched bundle) while no branch reaches them, and a citation of
    such a commit is dead for every clone. Ancestry of ``HEAD`` covers ``main`` locally, a
    branch built on it, and a pull request head in CI.
    """
    proc = subprocess.run(
        ["git", "-C", str(root), "merge-base", "--is-ancestor", sha, "HEAD"],
        capture_output=True,
        timeout=60,
    )
    return proc.returncode == 0


def citation_resolves(root: Path, sha: str) -> bool:
    """``sha`` is an ancestor of ``HEAD``, or a recorded history rewrite turned it into one.

    A rewrite (2026-09-16: purging the memory snapshot) changes the hash of every commit after
    the first rewritten one, and three of the documents that cite hashes may not be edited to
    follow -- the append-only decisions log, the append-only register, and the reference
    records. The rewrite records what each commit became (``docs/reference/hash-remap-*.tsv``)
    and a citation is followed through that map. What does not change: the destination must
    still be an ancestor of ``HEAD``, so a map cannot rescue a citation that points nowhere.
    """
    if resolves_in_git(root, sha):
        return True
    return any(resolves_in_git(root, s) for s in successors(load_remap(root), sha))


def test_every_gate_file_and_marker_id_has_a_ledger_row() -> None:
    ledger = (ROOT / GUARDS).read_text(encoding="utf-8")
    missing_files = gate_files_missing_from_ledger(ROOT, ledger)
    missing_ids = marker_ids_missing_from_ledger(ROOT, ledger)
    assert not missing_files and not missing_ids, "gates with no row in GUARDS.md:\n" + "\n".join(
        missing_files + missing_ids
    )


def test_every_cited_commit_hash_resolves() -> None:
    found = [
        f"{rel}:{n}: {sha}"
        for rel, n, sha in cited_hashes(ROOT)
        if not citation_resolves(ROOT, sha)
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


def exists_in_git(root: Path, sha: str) -> bool:
    """``sha`` names a commit object in this repository, wherever it sits."""
    proc = subprocess.run(
        ["git", "-C", str(root), "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}"],
        capture_output=True,
        timeout=60,
    )
    return proc.returncode == 0


def rows_a_citation_follows(root: Path, remap: Mapping[str, str]) -> set[tuple[str, str]]:
    """Every ``(old, new)`` map row some document's citation walks through, chains included."""
    reachable: set[tuple[str, str]] = set()
    seen: set[str] = set()
    frontier = [sha for _, _, sha in cited_hashes(root)]
    while frontier:
        current = frontier.pop()
        if current in seen:
            continue
        seen.add(current)
        for old, new in remap.items():
            if old.startswith(current):
                reachable.add((old, new))
                frontier.append(new)
    return reachable


@pytest.mark.gate("G40")
def test_every_rewrite_a_citation_follows_lands_on_a_commit_that_exists() -> None:
    """A map is only as good as its right-hand column where a citation walks down it: every
    commit a rewrite claims to have produced, and that some document's citation is followed
    into, must be a commit this repository has.

    Existence, not ancestry. A rewrite moves every branch, so a map row may name a commit that
    lives only on a side branch and is not reachable from ``HEAD`` -- a branch under review the
    day the history was rewritten. Ancestry stays where it belongs, on the citation: a document
    that cites a commit still needs that commit to be an ancestor of ``HEAD``, whether it cites
    it directly or through this map.

    Reach, and why it stops where it does (2026-09-16, KI-032). Demanding existence for *every*
    row asked a question about the machine that ran the rewrite rather than about the
    repository: an unmerged local branch is in nobody else's clone, so the row for a commit on
    one is red in CI and on every fresh checkout for as long as the branch is unpushed, while
    the map itself is a reference record and may not be edited to drop the row. A row no
    document cites cannot make a citation fail, and the day one does, the citation is followed
    into the row and both this test and ``test_every_cited_commit_hash_resolves`` go red. What
    the map may never do -- make a dead citation look alive -- is still checked here and there.
    """
    remap = load_remap(ROOT)
    dead = sorted(
        f"{old[:7]} -> {new[:7]}"
        for old, new in rows_a_citation_follows(ROOT, remap)
        if not exists_in_git(ROOT, new)
    )
    assert not dead, "cited rewrites whose commit is not in this repository:\n" + "\n".join(dead)


@pytest.mark.gate("G40")
def test_positive_control_only_the_rows_a_citation_follows_are_demanded(tmp_path: Path) -> None:
    """Both halves of that reach, driven against a throwaway document tree: the rows a citation
    walks through -- the whole chain, not just the first hop -- are the rows the gate demands,
    and a row nothing cites is left alone."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "x.md").write_text("`0badc0d` is a citation\n", encoding="utf-8")
    cited, middle, end = ("0badc0d" + "0" * 33, "b0bbed0" + "0" * 33, "decade0" + "0" * 33)
    uncited, elsewhere = ("a11ce55" + "0" * 33, "d0omed0" + "0" * 33)
    remap = {cited: middle, middle: end, uncited: elsewhere}
    assert rows_a_citation_follows(tmp_path, remap) == {(cited, middle), (middle, end)}
    assert rows_a_citation_follows(tmp_path, {uncited: elsewhere}) == set()
    assert not exists_in_git(ROOT, elsewhere), "the uncited row points nowhere and is tolerated"


@pytest.mark.gate("G40")
def test_positive_control_a_remap_resolves_a_citation_and_rescues_nothing_else() -> None:
    """The map's two halves, both driven against this repository: a hash the map sends to a real
    commit resolves, and a hash the map does not name -- or sends somewhere dead -- does not."""
    head = subprocess.run(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout.strip()
    gone = "0badc0d" + "0" * 33
    other = "d0omed01" + "0" * 32

    assert successors({gone: head}, "0badc0d") == [head]
    assert not resolves_in_git(ROOT, "0badc0d")
    assert any(resolves_in_git(ROOT, s) for s in successors({gone: head}, "0badc0d"))
    assert successors({gone: head}, "d0omed0") == [], "a map entry rescues only the hash it names"
    assert not any(resolves_in_git(ROOT, s) for s in successors({gone: other}, "0badc0d")), (
        "a map that points at a commit nobody has must not make a citation resolve"
    )
    assert successors({gone: other, other: head}, "0badc0d") == [other, head], "chained rewrites"


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
