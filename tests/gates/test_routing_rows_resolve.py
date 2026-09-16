"""G44: every routing pointer resolves to a document, a section, and (for rule files) a path.

Birth incident (Wes, 2026-09-14): the memory system routes agents to reference documents
through three tables (the working agreement's routing table, the doc router's door and routing
tables) and through the path-scoped rule files, and nothing checked that a pointer still landed
anywhere. A routing row that names a renamed document, a section heading that was reworded, or a
rule file whose ``paths:`` globs match nothing is a router that fails silently: the agent reads
nothing and proceeds. The first run found two: a section cited as "migrations" that the runbook
titles "Migrate", and rule files naming package-relative paths. Wes asked for the test to be
future-facing, so it checks whatever the tables say at the time rather than a fixed list, and a
memory topic file that names a repo path is checked the same way through the committed snapshot.

What resolves: a backticked path token exists (relative to the repo root; to ``docs/`` for the
router; to the package for rule files and memory); a ``§`` reference after it names a heading in
that document, either by code (``§ 4``, ``§B.6``, ``§1–§2``) or by text (``§ Collector algorithm``
is a prefix of the heading, or the heading's text is a prefix of the reference); every rule file
has at least one ``paths:`` glob that matches a tracked file, so a rule written for a module that
does not exist yet still has a live twin. Outside the check, and therefore review: whether the
routed document is the right one.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import pytest
from tools.ratchet import is_separator_row, split_row

from tools import memory_snapshot

ROOT = Path(__file__).resolve().parents[2]

#: (file, heading that opens the table, columns whose pointers are checked)
ROUTING_TABLES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("CLAUDE.md", "## Routing: read before you touch", ("Read first",)),
    ("docs/INDEX.md", "## Start here: which of these are you about to do?", ("Read", "Then")),
    ("docs/INDEX.md", "## Routing table (task → read first)", ("Read",)),
)
RULE_FILES_GLOB = ".claude/rules/*.md"
#: Memory topic files are read where this machine keeps them. They left the tree on 2026-09-16
#: (D-35): the snapshot is private, so it is read from the private home when there is one and
#: from live memory otherwise. A machine with neither -- CI, a fresh clone -- checks no memory
#: pointer; that is the price of taking the working notes out of a public repository, and it is
#: recorded on G44's row in the guards ledger.
MEMORY_LABEL = "memory/"
ROUTER_SOURCES = ("CLAUDE.md", "docs/INDEX.md")

PATH_TOKEN = re.compile(r"`([^`\s]+)`")
#: A path-looking token: has a slash or a document suffix, is not a home path or a glob.
PATH_LIKE = re.compile(r"^(?![~/])(?!.*[*{}]).*(?:/|\.(?:md|py|sh|toml|yaml|yml|txt|json))$")
SECTION_REF = re.compile(r"§\s*([^`§|]*)")
ALIASES = {"Plan": "docs/PLAN.md"}
ALIASES_PATTERN = re.compile(r"\b(" + "|".join(map(re.escape, ALIASES)) + r")\s+§")
#: Where a heading reference ends and commentary begins.
REF_TERMINATOR = re.compile(
    r"\s+\(|\s+→|,|;|:|\)|\.\s*$|[\"“”]|\s+(?:and|first|with|then|in)(?:\s|$)"
)
CODE = re.compile(r"^[A-Z]?\d*(?:\.\d+)*$")
HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*$")
HEADING_CODE = re.compile(r"^(?:§\s*)?([A-Z]?\d*(?:\.\d+)*)[.):\s]+")


@dataclass(frozen=True)
class Pointer:
    source: str
    line: int
    path: str
    section: str | None = None

    def __str__(self) -> str:
        where = f"{self.source}:{self.line}: `{self.path}`"
        return where if self.section is None else f"{where} § {self.section}"


def cells_under(text: str, opening: str, columns: Iterable[str]) -> list[tuple[int, str]]:
    """``(line, cell)`` for the named columns of the first table after the ``opening`` heading."""
    found: list[tuple[int, str]] = []
    wanted = set(columns)
    index: dict[str, int] | None = None
    seen_opening = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip() == opening:
            seen_opening = True
            continue
        if not seen_opening:
            continue
        cells = split_row(line)
        if not cells:
            if index is not None:
                break
            continue
        if index is None:
            if wanted & set(cells):
                index = {c: i for i, c in enumerate(cells) if c in wanted}
            continue
        if is_separator_row(cells):
            continue
        found += [(number, cells[i]) for i in index.values() if i < len(cells)]
    return found


def _cut(text: str) -> str:
    text = text.strip().strip("*").lstrip('"“” ')
    m = REF_TERMINATOR.search(text)
    return (text[: m.start()] if m else text).strip()


QUOTED = re.compile(r'["“”]([^"“”]+)["“”]')


def clean_ref(ref: str) -> str:
    """Cut commentary off a section reference: ``Robustness → "Guard design rules"`` keeps
    the arrow's target as a second reference, and every quoted target after the arrow is kept
    (widened 2026-09-15: a router row named a retired section as its second quoted target and
    only the first was checked); ``Swept with how it was checked`` keeps ``Swept``.
    """
    if "→" in ref:
        head, target = ref.split("→", 1)
        targets = QUOTED.findall(target) or [target]
        return "\x00".join([_cut(head), *(_cut(t) for t in targets)])
    return _cut(ref)


def split_range(ref: str) -> list[str]:
    """``1–2`` and ``B.6–B.7`` name their two ends; ``A\\x00B`` (an arrow) names both parts."""
    parts: list[str] = []
    for piece in ref.split("\x00"):
        piece = piece.strip()
        if not piece:
            continue
        ends = [e.strip() for e in re.split(r"\s*[–-]\s*", piece) if e.strip()]
        if len(ends) == 2 and all(CODE.match(e) for e in ends):
            parts.extend(ends)
        else:
            parts.append(piece)
    return parts


def pointers_in(source: str, line: int, cell: str) -> list[Pointer]:
    """Every path token in ``cell`` and every ``§`` reference that follows it."""
    out: list[Pointer] = []
    cell = ALIASES_PATTERN.sub(lambda m: f"`{ALIASES[m.group(1)]}` §", cell)
    tokens = [(m.start(), m.end(), m.group(1)) for m in PATH_TOKEN.finditer(cell)]
    for i, (_, end, token) in enumerate(tokens):
        if not PATH_LIKE.match(token):
            continue
        if source not in ROUTER_SOURCES and "/" not in token:
            continue  # a bare file name in prose (a memory note about a config file) is not a route
        stop = tokens[i + 1][0] if i + 1 < len(tokens) else len(cell)
        tail = re.sub(r"([–-])\s*§\s*", r"\1", cell[end:stop])  # ``§1–§2`` is one range
        refs = [ref for ref in SECTION_REF.findall(tail) if ref.strip()]
        if not refs:
            out.append(Pointer(source, line, token))
        for ref in refs:
            out += [Pointer(source, line, token, part) for part in split_range(clean_ref(ref))]
    return out


def resolve_path(root: Path, source: str, token: str) -> Path | None:
    """Router tokens may be relative to ``docs/``; rule files and memory may name a package path."""
    bases = [root]
    if source.startswith("docs/"):
        bases.append(root / "docs")
    if source.startswith((".claude/", MEMORY_LABEL)):
        bases.append(root / "src" / "threaddigest")
    for base in bases:
        candidate = base / token
        if candidate.exists():
            return candidate
    return None


def headings(text: str) -> list[str]:
    return [m.group(1) for line in text.splitlines() if (m := HEADING.match(line))]


def heading_matches(heading: str, ref: str) -> bool:
    ref = ref.strip()
    first = ref.split(" ", 1)[0]
    if first and CODE.match(first):
        m = HEADING_CODE.match(heading)
        if m and m.group(1) == first:
            return True
        if CODE.match(ref):
            return False
    body = HEADING_CODE.sub("", heading, count=1) if HEADING_CODE.match(heading) else heading
    body = re.sub(r"\s+", " ", body.strip("§ ").lower())
    wanted = re.sub(r"\s+", " ", ref.lower())
    if len(wanted) < 4 or len(body) < 4:
        return False
    return body.startswith(wanted) or wanted.startswith(body)


def section_resolves(document: Path, ref: str) -> bool:
    return any(heading_matches(h, ref) for h in headings(document.read_text(encoding="utf-8")))


def dangling(root: Path, pointers: Iterable[Pointer]) -> list[str]:
    found: list[str] = []
    for p in pointers:
        target = resolve_path(root, p.source, p.path)
        if target is None:
            found.append(f"{p}: no such file")
        elif p.section is not None and target.suffix == ".md":
            if not section_resolves(target, p.section):
                found.append(f"{p}: no heading matches")
    return found


def table_pointers(root: Path) -> list[Pointer]:
    out: list[Pointer] = []
    for source, opening, columns in ROUTING_TABLES:
        text = (root / source).read_text(encoding="utf-8")
        for line, cell in cells_under(text, opening, columns):
            out += pointers_in(source, line, cell)
    return out


def pointers_in_files(paths: Iterable[Path], root: Path) -> list[Pointer]:
    out: list[Pointer] = []
    for path in paths:
        try:
            source = path.relative_to(root).as_posix()
        except ValueError:  # outside the tree: a memory file in the private home
            source = MEMORY_LABEL + path.name
        for line, text in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            out += pointers_in(source, line, text)
    return out


def file_pointers(root: Path, pattern: str) -> list[Pointer]:
    return pointers_in_files(sorted(root.glob(pattern)), root)


def memory_files(root: Path) -> list[Path]:
    """The memory topic files this machine has: the private snapshot, else live memory."""
    memory, snapshot = memory_snapshot.default_paths(root)
    for folder in (snapshot, memory):
        if folder.is_dir():
            return sorted(folder.glob("*.md"))
    return []


def rule_globs(root: Path) -> list[tuple[str, list[str]]]:
    """``(rule file, its paths: globs)`` from each rule file's frontmatter."""
    out: list[tuple[str, list[str]]] = []
    for path in sorted(root.glob(RULE_FILES_GLOB)):
        text = path.read_text(encoding="utf-8")
        globs: list[str] = []
        if text.startswith("---"):
            front = text.split("---", 2)[1]
            globs = re.findall(r'^\s*-\s*"?([^"\n]+?)"?\s*$', front, flags=re.MULTILINE)
        out.append((path.relative_to(root).as_posix(), globs))
    return out


def glob_matches(glob: str, files: Iterable[str]) -> bool:
    if glob.endswith("/**"):
        prefix = glob[:-2]
        return any(f.startswith(prefix) for f in files)
    return any(fnmatch.fnmatch(f, glob) for f in files)


def tracked(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=True, timeout=60
    ).stdout
    return out.split()


def unmatched_rule_files(root: Path, files: Iterable[str]) -> list[str]:
    files = list(files)
    return [
        f"{rule}: no paths: glob matches a tracked file ({globs or 'no globs'})"
        for rule, globs in rule_globs(root)
        if not any(glob_matches(g, files) for g in globs)
    ]


# --------------------------------------------------------------------------- the gate


def test_the_routing_tables_carry_pointers() -> None:
    """A parser that silently found nothing would pass forever; pin that it reads the tables."""
    pointers = table_pointers(ROOT)
    assert len(pointers) > 20, [str(p) for p in pointers]
    assert any(p.section for p in pointers)


def test_every_routing_pointer_resolves() -> None:
    pointers = table_pointers(ROOT) + file_pointers(ROOT, RULE_FILES_GLOB)
    pointers += pointers_in_files(memory_files(ROOT), ROOT)
    found = dangling(ROOT, pointers)
    assert not found, "routing pointers that resolve to nothing:\n" + "\n".join(found)


def test_the_memory_files_are_read_when_this_machine_has_them() -> None:
    """A parser that silently found nothing would pass forever, and since 2026-09-16 the memory
    is outside the tree, so it can be absent. Where it exists -- Wes's machine, with the private
    snapshot or live memory -- it must yield pointers; where it does not (CI, a fresh clone) the
    check above reads no memory at all, which is the cost of a private snapshot."""
    files = memory_files(ROOT)
    if files:
        assert pointers_in_files(files, ROOT), sorted(p.name for p in files)


def test_every_rule_file_matches_a_tracked_file() -> None:
    found = unmatched_rule_files(ROOT, tracked(ROOT))
    assert not found, "\n".join(found)


# --------------------------------------------------------------------------- positive controls

TABLE = """\
# working agreement

## Routing: read before you touch

| If you are about to… | Read first |
|---|---|
| Real | `docs/REAL.md` § Collector algorithm |
| Ghost file | `docs/GHOST.md` |
| Ghost section | `docs/REAL.md` § No such heading |
| Code | `docs/REAL.md` §2 and `docs/REAL.md` §B.6–B.7 |
| Ghost code | `docs/REAL.md` § 9 |
| Arrow | `docs/REAL.md` § Robustness → "Guard design rules" |

## Something else

| Not | a routing table |
|---|---|
| `docs/NOT-CHECKED.md` | ignored |
"""

REAL = """\
# Real

## Collector algorithm (daily)

## 2. Guard design rules

### B.6 Reconcile

### B.7 Scrub

## Robustness, enforcement and portability
"""


def _tree(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    (tmp_path / "CLAUDE.md").write_text(TABLE, encoding="utf-8")
    (tmp_path / "docs" / "REAL.md").write_text(REAL, encoding="utf-8")
    return tmp_path


@pytest.mark.gate("G44")
def test_positive_control_dangling_file_section_and_code_are_red(tmp_path: Path) -> None:
    root = _tree(tmp_path)
    text = (root / "CLAUDE.md").read_text(encoding="utf-8")
    pointers = [
        p
        for line, cell in cells_under(text, "## Routing: read before you touch", ("Read first",))
        for p in pointers_in("CLAUDE.md", line, cell)
    ]
    found = dangling(root, pointers)
    assert sorted(f.split(": ", 2)[2] for f in found) == [
        "no heading matches",  # § No such heading
        "no heading matches",  # § 9
        "no such file",  # GHOST.md
    ], found
    assert not any("NOT-CHECKED" in str(p) for p in pointers), "a non-routing table was read"


@pytest.mark.gate("G44")
def test_positive_control_the_matcher_accepts_codes_ranges_text_and_arrows() -> None:
    assert heading_matches("Collector algorithm (daily)", "Collector algorithm")
    assert heading_matches("2. Guard design rules", "2")
    assert heading_matches("2. Guard design rules", "guard design rules")
    assert heading_matches("B.6 Reconcile", "B.6")
    assert not heading_matches("B.6 Reconcile", "B")  # a code names one heading, not a family
    assert not heading_matches("10. Material", "1")
    assert split_range("1–2") == ["1", "2"]
    assert split_range("B.6–B.7") == ["B.6", "B.7"]
    assert split_range("Robustness\x00Guard design rules") == ["Robustness", "Guard design rules"]
    assert clean_ref("Swept with how it was checked") == "Swept"
    assert clean_ref("Data model (content-state machine)") == "Data model"
    assert clean_ref("settled negatives first (do not rebuild)") == "settled negatives"
    assert clean_ref('Robustness → "Guard design rules",') == "Robustness\x00Guard design rules"
    assert (
        clean_ref('Robustness → "Guard design rules" and "Adversarial review: what changed"')
        == "Robustness\x00Guard design rules\x00Adversarial review"  # cut at the colon, as ever
    )
    assert clean_ref("Collector algorithm and") == "Collector algorithm"


@pytest.mark.gate("G44")
def test_positive_control_a_rule_file_matching_nothing_is_red(tmp_path: Path) -> None:
    rules = tmp_path / ".claude" / "rules"
    rules.mkdir(parents=True)
    (rules / "live.md").write_text('---\npaths:\n  - "src/x/**"\n---\n# x\n', encoding="utf-8")
    (rules / "dead.md").write_text(
        '---\npaths:\n  - "src/gone/**"\n---\n# gone\n', encoding="utf-8"
    )
    (rules / "bare.md").write_text("# no frontmatter\n", encoding="utf-8")
    found = unmatched_rule_files(tmp_path, ["src/x/a.py", "tests/x/test_a.py"])
    assert [f.split(":")[0] for f in found] == [".claude/rules/bare.md", ".claude/rules/dead.md"]
