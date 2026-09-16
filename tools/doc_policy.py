#!/usr/bin/env python3
"""The document contract: purpose, update policy, mirrors, and the checks that keep them honest.

Wes's ask (2026-09-15): the earlier project's reference corpus grew by ad-hoc requests, agents
appended rather than rewrote, dated annotations piled up, and nothing tied a changed fact to the
documents that repeated it. This tool makes the writing side mechanical, the way the routing
gates made the reading side mechanical. What it checks, and honestly what it does not:

- **Contract.** Every living document under ``docs/`` (everything except ``reference/``) opens with
  YAML front matter naming its ``purpose``, its ``update-policy`` from a fixed vocabulary, the
  documents it ``mirrors`` (paths that must exist; mirroring between living documents must be
  declared from both sides), and, for the policies that are rewritten, the milestone it was
  ``verified-at``. The mirror list is a declaration the sweep reads; the tool does not compare a
  document's text with its mirrors, the live-facts table does that for the facts it lists.
- **Append-only by the diff, against the branch base.** A document declared ``append-only`` may
  gain lines anywhere and may carry a dated parenthetical inserted into an existing line, but no
  line committed at the merge base with ``main`` may disappear, move, or change otherwise. The
  baseline is the merge base, not ``HEAD``, so committing a deletion does not launder it. The
  policy that governs the diff is the one declared at the base, so a document cannot exempt
  itself by changing its own declaration. Sections named in ``exempt-sections`` are outside the
  diff (a table column filled at milestones).
- **Records are added, never edited.** Under ``docs/reference/`` a file that existed at the base
  must be byte-identical, except the review register (append-only) and the templates (reviewed
  like code).
- **Accretion.** Dated annotations in the prose of a prune-stale, versioned, or rewritten document
  (parentheticals, brackets, dash-delimited asides; table rows excluded, because the registers
  date their rows by design) are counted into a ratchet ceiling (``.ratchets/docs.txt``). This is a
  pressure, not a proof: a reshaped annotation escapes it, and the milestone pass reads the count.
- **Milestone lag.** The status page's front matter names the current milestone; a prune-stale or
  versioned document may lag it by at most one and may not be stamped ahead of it.
- **Dangling references.** Every backticked or linked ``*.md`` path carrying a directory, in a
  rewritten document or the working agreement, resolves to a file. A bare file name is not judged.
- **Live facts.** The machine-read table in the decisions log must exist, parse, and hold at least
  one row; every mirror must contain the literal (outside code fences and comments); a
  configuration, code, or file home must agree with the literal.
- **Identifiers.** A rewritten document or the working agreement that names a repository path, a
  ``make`` target, a test id, an ``threaddigest`` command line, a package module or attribute, or a
  ``table.column`` in backticks names something that exists in the tree. A token is exempt when
  its own neighbourhood on the line (the text between it and the next backticked token either
  side) names a milestone later than the status page's, the word "planned", a tranche, or a
  retirement word; a marker beside one token says nothing about the others. A table row whose own
  cell is a milestone or "planned" (the built/planned tables) is the designed home for a planned
  identifier and is exempt whole; a row dated in its first cell is a record of that day. Two
  ceilings in ``.ratchets/docs.txt``: a class-like name (``SearchIndex``) that no Python code uses
  as an identifier (strings and comments stripped) is counted rather than failed, because a design
  may name a class before it exists; and an identifier exempted by a marker in prose is counted,
  because the annotation route is the one the accretion rule resists. Born 2026-09-16: the plan,
  the decisions log, and the runbook described a search-index port and a ``VACUUM INTO`` backup
  that the database layer never had, written before the build and carried through the plan's
  second version; only the identifier-shaped part of that drift is mechanical. Its refute pass the
  same day found the column check dead against the one-line committed schema, the exemptions
  line-wide, and the annotation route uncounted; all three are closed here.

Usage: ``--check`` (exit 1 with every problem), ``--write PATH`` (the JSON report the ratchet
reads), ``--report`` (print the report); ``--write --check`` is what ``make check`` runs. The gate
is ``tests/gates/test_doc_policy.py``.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = Path("docs")
DECISIONS = DOCS / "decisions" / "DECISIONS.md"
STATUS = DOCS / "recent" / "STATUS.md"
WORKING_AGREEMENT = Path("CLAUDE.md")
REPORT = Path(".build") / "doc_policy.json"
REFERENCE = "reference/"
REFERENCE_APPEND_ONLY = ("reference/reviews/REGISTER.md",)
REFERENCE_EDITABLE = ("reference/reviews/templates/",)

POLICIES = ("append-only", "prune-stale", "rewritten", "versioned")
LAG_POLICIES = ("prune-stale", "versioned")
ACCRETION_POLICIES = ("prune-stale", "versioned", "rewritten")
MILESTONES = ("D0", "M0", "M1a-A", "M1a-B", "M1b", "M1c", "M1d", "M2", "M3", "M4", "MB", "M5")
MAX_MILESTONE_LAG = 1
FACTS_SECTION = "## Live facts (machine-read)"

FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
DATE = r"(?<![-/_\w])20\d\d-\d\d-\d\d(?![-\w])"
#: A prose aside: a parenthetical (one nested level allowed), a bracket, or a dash-delimited
#: clause. An aside is an annotation when it carries a date that is not part of a path or name.
ASIDE = re.compile(r"\((?:[^()]|\([^()]*\))*\)|\[[^\[\]]*\]|[—–][^—–]*[—–]")
PARENTHETICAL = re.compile(r"\s*\*?\((?:[^()]|\([^()]*\))*\)\*?")
DATE_RE = re.compile(DATE)


def dated_asides(line: str) -> list[str]:
    return [m.group(0) for m in ASIDE.finditer(line) if DATE_RE.search(m.group(0))]


def _without_dated_parentheticals(line: str) -> str:
    return PARENTHETICAL.sub(lambda m: "" if DATE_RE.search(m.group(0)) else m.group(0), line)


DOC_TOKEN = re.compile(r"`([A-Za-z0-9_./-]+\.md)`|\]\(([A-Za-z0-9_./-]+\.md)\)")
FACT_ROW = re.compile(r"^\|\s*(F-\d+)\s*\|([^|]*)\|([^|]*)\|\s*`([^`]*)`\s*\|([^|]*)\|\s*$")
FACT_LIKE = re.compile(r"^\|\s*F-\d+\s*\|")
BACKTICKED = re.compile(r"`([^`]+)`")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
FENCE = re.compile(r"^(```|~~~)")


# ------------------------------------------------------------------------- front matter


def front_matter(text: str) -> dict[str, object] | None:
    """The parsed front matter, ``{}`` when the block is empty, ``None`` when there is none."""
    m = FRONT.match(text)
    if m is None:
        return None
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def strip_front_matter(text: str) -> str:
    return FRONT.sub("", text, count=1)


def prose_only(text: str) -> str:
    """The text with HTML comments and fenced code removed, for searches that mean prose."""
    lines: list[str] = []
    in_code = False
    for line in HTML_COMMENT.sub("", text).splitlines():
        if FENCE.match(line):
            in_code = not in_code
            continue
        if not in_code:
            lines.append(line)
    return "\n".join(lines)


def living_documents(root: Path) -> list[Path]:
    docs = root / DOCS
    return sorted(
        p for p in docs.rglob("*.md") if not p.relative_to(docs).as_posix().startswith(REFERENCE)
    )


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _policy(data: dict[str, object] | None) -> str | None:
    value = (data or {}).get("update-policy")
    return value if isinstance(value, str) else None


def contract_problems(root: Path, path: Path, declared: dict[str, dict[str, object]]) -> list[str]:
    """Why one document's front matter fails the contract; empty when it holds."""
    rel = _rel(root, path)
    data = front_matter(path.read_text(encoding="utf-8"))
    if data is None:
        return [f"{rel}: no front matter (purpose, update-policy, mirrors, verified-at)"]
    found: list[str] = []
    purpose = data.get("purpose")
    if not isinstance(purpose, str) or not purpose.strip():
        found.append(f"{rel}: purpose missing")
    policy = _policy(data)
    if policy not in POLICIES:
        found.append(f"{rel}: update-policy {policy!r} not one of {', '.join(POLICIES)}")
    mirrors = data.get("mirrors", [])
    if not isinstance(mirrors, list):
        found.append(f"{rel}: mirrors must be a list of paths")
    else:
        for m in mirrors:
            if not isinstance(m, str) or not (root / m).is_file():
                found.append(f"{rel}: mirror {m!r} does not exist")
            elif m in declared and rel not in (declared[m].get("mirrors") or []):
                found.append(f"{rel}: declares {m} as a mirror, which does not declare it back")
    verified = data.get("verified-at")
    if policy in LAG_POLICIES and verified not in MILESTONES:
        found.append(f"{rel}: verified-at {verified!r} not one of {', '.join(MILESTONES)}")
    elif verified is not None and verified not in MILESTONES:
        found.append(f"{rel}: verified-at {verified!r} not one of {', '.join(MILESTONES)}")
    if policy == "rewritten" and data.get("milestone") not in MILESTONES:
        found.append(f"{rel}: a rewritten document names the current milestone")
    return found


# --------------------------------------------------------------------------- append-only


def _git(root: Path, *args: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False, timeout=60
    )
    return proc.stdout if proc.returncode == 0 else None


def baseline_ref(root: Path) -> str | None:
    """The merge base with ``main`` when it exists, else ``HEAD``; ``None`` outside a repository."""
    if _git(root, "rev-parse", "--verify", "HEAD") is None:
        return None
    base = _git(root, "merge-base", "HEAD", "main")
    return base.strip() if base else "HEAD"


def base_text(root: Path, ref: str, rel: str) -> str | None:
    """The file at the baseline, or ``None`` when it did not exist there."""
    return _git(root, "show", f"{ref}:{rel}")


def _norm(line: str) -> str:
    """A line with its dated parentheticals removed and its spacing collapsed."""
    return " ".join(_without_dated_parentheticals(line).split())


def _exempt_ranges(text: str, headings: list[str]) -> set[int]:
    """Line numbers (1-based) inside sections whose heading line starts with an exempt prefix."""
    exempt: set[int] = set()
    level = 0
    for number, line in enumerate(text.splitlines(), start=1):
        m = re.match(r"^(#{1,6})\s+", line)
        if m:
            depth = len(m.group(1))
            if level and depth <= level:
                level = 0
            if not level and any(line.startswith(h) for h in headings):
                level = depth
        if level:
            exempt.add(number)
    return exempt


def append_only_violations(
    old: str, new: str, rel: str, exempt_sections: list[str] | None = None
) -> list[str]:
    """Every baseline line that the new text does not keep, in order, with at most a dated
    parenthetical inserted or a suffix appended; a moved, hidden, or rewritten line is a loss."""
    exempt = _exempt_ranges(old, exempt_sections or [])
    new_lines = [line.rstrip() for line in HTML_COMMENT.sub("", new).splitlines()]
    found: list[str] = []
    cursor = 0
    for number, raw in enumerate(old.splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip() or number in exempt:
            continue
        target = _norm(line)
        hit = next(
            (
                i
                for i in range(cursor, len(new_lines))
                if new_lines[i] == line
                or new_lines[i].startswith(line)
                or _norm(new_lines[i]) == target
                or _norm(new_lines[i]).startswith(target)
            ),
            None,
        )
        if hit is None:
            found.append(f"{rel}:{number}: append-only document lost a line: {line[:80]!r}")
        else:
            cursor = hit + 1
    return found


def append_only_problems(root: Path, ref: str | None) -> list[str]:
    """The diff check for every append-only document and every reference record."""
    if ref is None:
        return ["append-only baseline unavailable: not a git repository"]
    found: list[str] = []
    for path in living_documents(root):
        rel = _rel(root, path)
        new = path.read_text(encoding="utf-8")
        old = base_text(root, ref, rel)
        if old is None:
            continue  # new on this branch
        old_data = front_matter(old)
        old_policy = _policy(old_data) or _policy(front_matter(new))
        if old_policy != "append-only":
            continue
        if _policy(front_matter(new)) != "append-only":
            found.append(f"{rel}: append-only at the base; the policy may not be changed in place")
        exempt = (old_data or {}).get("exempt-sections") or []
        found += append_only_violations(old, new, rel, [str(h) for h in exempt])
    reference = root / DOCS / "reference"
    for path in sorted(reference.rglob("*")) if reference.is_dir() else []:
        if not path.is_file():
            continue
        rel = _rel(root, path)
        short = path.relative_to(root / DOCS).as_posix()
        if short.startswith(REFERENCE_EDITABLE):
            continue
        old = base_text(root, ref, rel)
        if old is None:
            continue
        new = path.read_text(encoding="utf-8") if path.suffix == ".md" else path.read_bytes().hex()
        if short in REFERENCE_APPEND_ONLY:
            found += append_only_violations(old, new, rel)
        elif old != new:
            found.append(f"{rel}: a reference record was edited; records are added, never edited")
    return found


# ------------------------------------------------------------------------------ accretion


def dated_annotations(text: str) -> list[tuple[int, str]]:
    """``(line, snippet)`` for every dated annotation in prose: outside front matter, fences,
    and table rows (the registers date their rows by design)."""
    found: list[tuple[int, str]] = []
    in_code = False
    body = strip_front_matter(text)
    skipped = text[: len(text) - len(body)].count("\n")
    for number, line in enumerate(body.splitlines(), start=skipped + 1):
        if FENCE.match(line):
            in_code = not in_code
            continue
        if in_code or line.lstrip().startswith("|"):
            continue
        found += [(number, aside[:60]) for aside in dated_asides(line)]
    return found


# ------------------------------------------------------------------------- milestone lag


def current_milestone(root: Path) -> str | None:
    if not (root / STATUS).is_file():
        return None
    value = (front_matter((root / STATUS).read_text(encoding="utf-8")) or {}).get("milestone")
    return value if isinstance(value, str) and value in MILESTONES else None


def milestone_lag_problems(root: Path) -> list[str]:
    current = current_milestone(root)
    if current is None:
        return [f"{STATUS.as_posix()}: front matter names no current milestone"]
    found: list[str] = []
    for path in living_documents(root):
        data = front_matter(path.read_text(encoding="utf-8")) or {}
        if _policy(data) not in LAG_POLICIES:
            continue
        verified = data.get("verified-at")
        if verified not in MILESTONES:
            continue  # the contract check reports it
        lag = MILESTONES.index(current) - MILESTONES.index(str(verified))
        if lag > MAX_MILESTONE_LAG:
            found.append(
                f"{_rel(root, path)}: verified at {verified}, the status page is at {current}: "
                f"re-read and rewrite or re-verify it (lag {lag}, allowed {MAX_MILESTONE_LAG})"
            )
        elif lag < 0:
            found.append(
                f"{_rel(root, path)}: verified at {verified}, ahead of the status page ({current})"
            )
    return found


# ---------------------------------------------------------------------- dangling references


def _resolves(root: Path, source: Path, token: str, corpus: list[str]) -> bool:
    """A path resolves at the root, under ``docs/``, beside the source, or as a suffix of any
    corpus file. A bare file name is not judged; a path with a directory must resolve."""
    if "<" in token or "*" in token:
        return True  # a template, not a path
    candidates = [root / token, root / DOCS / token, source.parent / token]
    if any(c.is_file() for c in candidates):
        return True
    if any(rel.endswith("/" + token) or rel == token for rel in corpus):
        return True
    return "/" not in token


def dangling_document_references(root: Path) -> list[str]:
    """Rewritten documents and the working agreement may not point at a document that is gone;
    append-only logs describe the past and may name files that no longer exist."""
    corpus = [p.relative_to(root / DOCS).as_posix() for p in (root / DOCS).rglob("*.md")]
    sources = [
        p
        for p in living_documents(root)
        if _policy(front_matter(p.read_text(encoding="utf-8"))) in ACCRETION_POLICIES
    ]
    sources.append(root / WORKING_AGREEMENT)
    found: list[str] = []
    for path in sources:
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for a, b in DOC_TOKEN.findall(line):
                token = a or b
                if not _resolves(root, path, token, corpus):
                    found.append(f"{_rel(root, path)}:{number}: `{token}` does not exist")
    return found


# ---------------------------------------------------------------------- identifier resolution

#: Suffixes that make a backticked token a repository path. ``.md`` paths belong to the dangling
#: reference check above, which has a deliberately weaker rule for bare names.
CODE_SUFFIXES = (
    ".py", ".sh", ".yaml", ".yml", ".toml", ".sql", ".txt", ".json", ".jsonl", ".css", ".html",
    ".cfg", ".ini", ".mode", ".plist", ".lock",
)  # fmt: skip
NOT_A_PATH = ("data/", ".build/", ".env", "~", "/", "http")
TEMPLATE_CHARS = "<>{}*…"
NODE_ID = re.compile(r"^(tests/[\w./-]+\.py)::([\w-]+)(?:\[[^\]]*\])?(?:::[\w-]+)?$")
MAKE_TARGET = re.compile(r"^make\s+([\w.-]+)")
COMMAND_LINE = re.compile(r"^(?:uv run\s+)?threaddigest\s+(.*)$")
PACKAGE_REF = re.compile(
    r"^(?:threaddigest\.)?(?:core|db|services|adapters|web|ports|cli|settings|tools)"
    r"(?:\.\w+)+(?:\(\))?$"
)
TABLE_COLUMN = re.compile(r"^([a-z_]+)\.([a-z_]+)$")
CLASS_NAME = re.compile(r"^[A-Z][a-z0-9]+(?:[A-Z][a-z0-9]+)+$")
PATH_TOKEN = re.compile(r"^\.?[\w.-]+(?:/[\w.-]+)*/?$")
DATED_ROW = re.compile(r"^\|\s*20\d\d-\d\d-\d\d\s*\|")
#: A retirement word beside a token says the token is the past. A decision id is not one: it
#: says something was decided, not that the thing named beside it is gone.
RETIRED = re.compile(
    r"\b(?:cut|retired|superseded|downgraded|dropped|deferred|declined|replaced|removed|renamed)\b",
    re.IGNORECASE,
)


def future_marker(current: str | None) -> re.Pattern[str]:
    """A milestone later than ``current``, the word planned, or a tranche, beside a token."""
    later = MILESTONES[MILESTONES.index(current) + 1 :] if current in MILESTONES else MILESTONES
    names = "|".join(re.escape(m) for m in later)
    return re.compile(rf"(?<![\w-])(?:{names})(?![\w-])|\b(?:planned|tranche [AB])\b")


def _status_cell_marks_future(line: str, future: re.Pattern[str]) -> bool:
    """A table row whose own cell is a milestone or the word planned is the designed home for
    a planned identifier (the built/planned tables); the whole row is exempt and not counted."""
    if not line.lstrip().startswith("|"):
        return False
    cells = [c.strip() for c in line.strip().strip("|").split("|")]
    # A cell made only of milestones, "planned", tranches, and range punctuation (M1b–M3).
    return any(c and not re.sub(r"[\s\-–—+,/]", "", future.sub("", c)) for c in cells)


#: Docstrings, string literals, and comments in a Python file: a class name mentioned there is
#: talk about the class, not the class.
PY_NOISE = re.compile(
    r'"""[\s\S]*?"""|\'\'\'[\s\S]*?\'\'\'|"(?:\\.|[^"\\\n])*"|\'(?:\\.|[^\'\\\n])*\'|#[^\n]*'
)
#: A one-line string literal: a file name the code reads or writes lives in one of these.
STRING_LITERAL = re.compile(r'"([^"\\\n]{1,120})"|\'([^\'\\\n]{1,120})\'')
#: Structured configuration the system reads: a name there (a hook event in the settings file,
#: a key in a launchd plist) is an identifier, unlike a word in a note or a shell comment.
STRUCTURED_SUFFIXES = (".json", ".plist", ".yaml", ".yml", ".toml")


def _code_only(text: str) -> str:
    return PY_NOISE.sub(" ", text)


@dataclass(frozen=True)
class Tree:
    """What the tree offers a backticked token to resolve against: ``files`` is the file list (a
    bare file name resolves only against it, never against text); ``code_corpus`` is the Python
    with its strings and comments removed (a class name resolves only where code uses it as an
    identifier); ``corpus`` is every non-document file as written, kept for future checks."""

    root: Path
    files: tuple[str, ...]
    corpus: str
    code_corpus: str
    string_literals: frozenset[str]
    top_dirs: frozenset[str]
    package_dirs: frozenset[str]
    make_targets: frozenset[str]
    cli_text: str
    schema_sql: str
    settings: dict[str, object]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def load_tree(root: Path) -> Tree:
    """Tracked and untracked (not ignored) files, and the text of every non-document file."""
    listed = _git(root, "ls-files", "--cached", "--others", "--exclude-standard")
    files = tuple(sorted(set(listed.split()))) if listed else ()
    texts: list[str] = []
    code: list[str] = []
    literals: set[str] = set()
    for rel in files:
        path = root / rel
        if rel.endswith(".md") or rel.startswith("memory-snapshot/") or not path.is_file():
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        texts.append(text)
        if rel.endswith(".py"):
            code.append(_code_only(text))
            literals.update(a or b for a, b in STRING_LITERAL.findall(text))
        elif rel.endswith(STRUCTURED_SUFFIXES):
            code.append(text)  # keys and values the system reads: a hook event, a plist key
    package = "src/threaddigest/"
    settings_path = root / "config" / "settings.yaml"
    try:
        settings = yaml.safe_load(_read(settings_path)) if settings_path.is_file() else {}
    except yaml.YAMLError:
        settings = {}
    return Tree(
        root=root,
        files=files,
        corpus="\n".join(texts),
        code_corpus="\n".join(code),
        string_literals=frozenset(literals),
        settings=settings if isinstance(settings, dict) else {},
        top_dirs=frozenset(f.split("/")[0] for f in files if "/" in f),
        package_dirs=frozenset(
            f[len(package) :].split("/")[0]
            for f in files
            if f.startswith(package) and f[len(package) :].count("/") >= 1
        ),
        make_targets=frozenset(re.findall(r"^([\w.-]+):", _read(root / "Makefile"), re.M)),
        cli_text=_read(root / "src" / "threaddigest" / "cli.py"),
        schema_sql=_read(root / "src" / "threaddigest" / "db" / "schema.sql"),
    )


def _defined_in(name: str, text: str) -> bool:
    pattern = rf"^\s*(?:async\s+)?(?:def|class)\s+{re.escape(name)}\b"
    return re.search(pattern, text, re.M) is not None


def _word_in(name: str, text: str) -> bool:
    return re.search(rf"\b{re.escape(name)}\b", text) is not None


def _path_resolves(tree: Tree, source: Path, token: str) -> bool:
    token = token.rstrip("/")
    bases = (tree.root, tree.root / DOCS, tree.root / "src" / "threaddigest", tree.root / "tools")
    for base in (*bases, source.parent):
        if any((base / cand).exists() for cand in (token, token + ".py")):
            return True
    if any(f == token or f.endswith("/" + token) for f in tree.files):
        return True
    if "/" not in token and (
        any(f.rsplit("/", 1)[-1] == token for f in tree.files) or token in tree.string_literals
    ):
        return True  # a bare name some tracked file has, or one the code names in a string
    ignored = subprocess.run(
        ["git", "-C", str(tree.root), "check-ignore", "-q", token],
        capture_output=True,
        check=False,
        timeout=60,
    )
    return ignored.returncode == 0  # a declared generated artifact


def _looks_like_path(tree: Tree, token: str) -> bool:
    if not PATH_TOKEN.match(token):
        return False
    if token.endswith(CODE_SUFFIXES):
        return True
    return "/" in token and token.split("/")[0] in (tree.top_dirs | tree.package_dirs)


def _package_ref_resolves(tree: Tree, token: str) -> bool:
    parts = token.removesuffix("()").removeprefix("threaddigest.").split(".")
    for k in range(len(parts), 0, -1):
        for base in ("src/threaddigest", ""):
            stem = "/".join(([base] if base else []) + parts[:k])
            for cand in (stem + ".py", stem + "/__init__.py"):
                path = tree.root / cand
                if not path.is_file():
                    continue
                attrs = parts[k:]
                return not attrs or _word_in(attrs[0], _code_only(path.read_text(encoding="utf-8")))
    return False


def _table_block(schema_sql: str, table: str) -> str | None:
    """The column list of ``CREATE TABLE table (...)``, whether the statement is written on one
    line (the committed ``schema.sql``) or many; ``None`` when the table is not in the schema."""
    m = re.search(rf'CREATE TABLE "?{re.escape(table)}"?\s*\(', schema_sql)
    if m is None:
        return None
    depth, start = 1, m.end()
    for i in range(start, len(schema_sql)):
        depth += {"(": 1, ")": -1}.get(schema_sql[i], 0)
        if depth == 0:
            return schema_sql[start:i]
    return None


def _command_missing(tree: Tree, rest: str) -> list[str]:
    """The command words and ``--options`` of an ``threaddigest`` line the CLI does not define;
    a word written as alternatives (``init/upgrade/current``) needs every alternative."""
    missing: list[str] = []
    for word in rest.split()[:2]:
        if word.startswith(("-", "[", "<")):
            break
        for name in word.split("/"):
            quoted = f'"{name}"' in tree.cli_text
            if not (quoted or _defined_in(name.replace("-", "_"), tree.cli_text)):
                missing.append(name)
    missing += [opt for opt in re.findall(r"--[a-z][\w-]*", rest) if opt not in tree.cli_text]
    return missing


def _settings_key_resolves(settings: dict[str, object], parts: list[str]) -> bool:
    """``a.b.c`` names a nested key of ``config/settings.yaml``."""
    node: object = settings
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return True


Verdict = tuple[str, str]
OK: Verdict = ("ok", "")


def _not_judged(token: str) -> bool:
    return (
        not token
        or any(c in token for c in TEMPLATE_CHARS)
        or token.startswith(NOT_A_PATH)
        or token.endswith(".md")
    )


def _judge_invocation(tree: Tree, token: str) -> Verdict | None:
    """A test id, a make target, or a command line; ``None`` when the token is none of those."""
    if m := NODE_ID.match(token):
        path = tree.root / m.group(1)
        if path.is_file() and _defined_in(m.group(2), path.read_text(encoding="utf-8")):
            return OK
        return "problem", "names a test that does not exist"
    if m := MAKE_TARGET.match(token):
        if not tree.make_targets or m.group(1) in tree.make_targets:
            return OK
        return "problem", "names a make target that does not exist"
    if m := COMMAND_LINE.match(token):
        missing = _command_missing(tree, m.group(1)) if tree.cli_text else []
        if not missing:
            return OK
        return "problem", f"names a command or option the CLI does not have ({', '.join(missing)})"
    return None


def _judge_reference(tree: Tree, source: Path, token: str) -> Verdict:
    """A package reference that resolves, else a path (a token with a code suffix is a path
    before it is anything else), else an unresolved package reference, a settings key, a table
    column, or a class-like name."""
    if PACKAGE_REF.match(token) and _package_ref_resolves(tree, token):
        return OK  # ``services.lock`` is a module before ``.lock`` is a file suffix
    if token.endswith(CODE_SUFFIXES) or _looks_like_path(tree, token):
        return OK if _path_resolves(tree, source, token) else ("problem", "does not exist")
    if PACKAGE_REF.match(token):
        return "problem", "names a module or attribute that does not exist"
    if "." in token and _settings_key_resolves(tree.settings, token.split(".")):
        return OK  # ``comments.replace_more_limit`` is a configuration key, not a column
    if m := TABLE_COLUMN.match(token):
        block = _table_block(tree.schema_sql, m.group(1))
        if block is None or _word_in(m.group(2), block):
            return OK
        return "problem", f"names a column that table {m.group(1)} does not have"
    if CLASS_NAME.match(token) and not _word_in(token, tree.code_corpus):
        return "class", ""
    return OK


def judge(tree: Tree, source: Path, token: str) -> Verdict:
    """``("ok", "")``, ``("problem", why)``, or ``("class", "")`` for a class-like name that no
    code file uses."""
    token = token.strip()
    if _not_judged(token):
        return OK
    return _judge_invocation(tree, token) or _judge_reference(tree, source, token)


def _prose_lines(text: str) -> list[tuple[int, str]]:
    """``(number, line)`` for every line outside fences and HTML comments, with the comment
    fragments cut out of the line."""
    out: list[tuple[int, str]] = []
    in_code = in_comment = False
    for number, raw in enumerate(text.splitlines(), start=1):
        if FENCE.match(raw):
            in_code = not in_code
            continue
        if in_code:
            continue
        line = HTML_COMMENT.sub("", raw)
        if in_comment:
            if "-->" not in line:
                continue
            in_comment, line = False, line.split("-->", 1)[1]
        if "<!--" in line:
            in_comment, line = True, line.split("<!--", 1)[0]
        out.append((number, line))
    return out


SENTENCE_BOUNDARY = re.compile(r"[.;]\s")
LEADING_PARENTHETICAL = re.compile(r"^\s*\([^)]*\)")


def tokens_with_context(line: str) -> list[tuple[str, str]]:
    """``(token, neighbourhood)`` for every backticked token. The neighbourhood is the text
    from the previous backticked token (or the cell, line, or sentence start) to the next one
    (or the cell, line, or sentence end), minus a parenthetical that opens the span, which
    belongs to the previous token. A marker exempts a token only when it sits in that token's
    own neighbourhood, so an annotation on one token says nothing about the others on the
    line, and a marker in one sentence says nothing about the next."""
    matches = list(BACKTICKED.finditer(line))
    out: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        prev_end = matches[i - 1].end() if i else 0
        next_start = matches[i + 1].start() if i + 1 < len(matches) else len(line)
        before = line[prev_end : m.start()].split("|")[-1]
        before = SENTENCE_BOUNDARY.split(LEADING_PARENTHETICAL.sub(" ", before))[-1]
        after = SENTENCE_BOUNDARY.split(line[m.end() : next_start].split("|")[0])[0]
        out.append((m.group(1), before + " " + after))
    return out


@dataclass
class IdentifierReport:
    problems: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    exempted: list[str] = field(default_factory=list)


def identifier_problems(root: Path) -> IdentifierReport:
    """Unresolved identifiers in rewritten documents and the working agreement (problems), the
    class-like names no code uses (a ceiling), and the identifiers a marker in prose exempted
    (a ceiling: the built/planned tables are the home for a planned identifier, and an
    annotation in prose is the route the accretion rule resists)."""
    tree = load_tree(root)
    future = future_marker(current_milestone(root))
    sources = [
        p
        for p in living_documents(root)
        if _policy(front_matter(p.read_text(encoding="utf-8"))) in ACCRETION_POLICIES
    ]
    sources.append(root / WORKING_AGREEMENT)
    rep = IdentifierReport()
    for path in sources:
        if not path.is_file():
            continue
        rel = _rel(root, path)
        for number, line in _prose_lines(path.read_text(encoding="utf-8")):
            if DATED_ROW.match(line) or _status_cell_marks_future(line, future):
                continue
            for token, context in tokens_with_context(line):
                token = token.strip()
                kind, why = judge(tree, path, token)
                if kind == "ok":
                    continue  # a marker beside a token that resolves changes nothing
                if future.search(context) or RETIRED.search(context):
                    rep.exempted.append(f"exempted_identifier {rel}:{number} `{token}`")
                elif kind == "problem":
                    rep.problems.append(f"{rel}:{number}: `{token}` {why}")
                else:
                    rep.classes.append(f"unresolved_class_name {rel}:{number} `{token}`")
    return rep


# ------------------------------------------------------------------------------ live facts


@dataclass(frozen=True)
class Fact:
    fact_id: str
    fact: str
    home: str
    literal: str
    mirrors: tuple[str, ...] = field(default_factory=tuple)


def live_facts(decisions_text: str) -> tuple[list[Fact], list[str]]:
    """The parsed rows and the problems: a missing section, an empty table, an unparsed row."""
    if FACTS_SECTION not in decisions_text:
        return [], [f"{DECISIONS.as_posix()}: no {FACTS_SECTION!r} section"]
    section = decisions_text.split(FACTS_SECTION, 1)[1].split("\n## ", 1)[0]
    facts: list[Fact] = []
    problems: list[str] = []
    for line in section.splitlines():
        m = FACT_ROW.match(line)
        if m:
            mirrors = tuple(BACKTICKED.findall(m.group(5)))
            facts.append(
                Fact(m.group(1), m.group(2).strip(), m.group(3).strip(), m.group(4), mirrors)
            )
        elif FACT_LIKE.match(line):
            problems.append(f"{DECISIONS.as_posix()}: unparsed live-facts row: {line[:60]!r}")
    if not facts:
        problems.append(f"{DECISIONS.as_posix()}: the live-facts table has no rows")
    return facts, problems


def _home_value(root: Path, home: str) -> str | None:
    """The value the canonical home holds, or ``None`` when the home form needs no lookup."""
    kind, _, rest = home.partition(":")
    if kind == "text":
        return None
    if kind == "file":
        return (
            prose_only((root / rest).read_text(encoding="utf-8")) if (root / rest).is_file() else ""
        )
    if kind == "yaml":
        path, _, dotted = rest.partition(":")
        data = yaml.safe_load((root / path).read_text(encoding="utf-8"))
        for part in dotted.split("."):
            data = data[part] if isinstance(data, dict) and part in data else None
        return "" if data is None else str(data)
    if kind == "python":
        module, _, name = rest.partition(":")
        return str(getattr(importlib.import_module(module), name))
    msg = f"unknown fact home {home!r}"
    raise ValueError(msg)


def fact_problems(root: Path) -> list[str]:
    if not (root / DECISIONS).is_file():
        return [f"{DECISIONS.as_posix()}: missing"]
    facts, found = live_facts((root / DECISIONS).read_text(encoding="utf-8"))
    for f in facts:
        try:
            value = _home_value(root, f.home)
        except (ValueError, ImportError, AttributeError, OSError) as exc:
            found.append(f"{f.fact_id}: home {f.home!r} unreadable: {exc}")
            continue
        if value is not None and (
            (f.home.startswith("file:") and f.literal not in value)
            or (not f.home.startswith("file:") and value != f.literal)
        ):
            found.append(
                f"{f.fact_id}: home {f.home} holds {value!r}, the table says `{f.literal}`"
            )
        for mirror in f.mirrors:
            path = root / mirror
            if not path.is_file():
                found.append(f"{f.fact_id}: mirror {mirror} does not exist")
            elif (
                f.literal.casefold() not in prose_only(path.read_text(encoding="utf-8")).casefold()
            ):
                found.append(f"{f.fact_id}: mirror {mirror} does not state `{f.literal}`")
    return found


# ------------------------------------------------------------------------------- the report


def report(root: Path = ROOT) -> dict[str, object]:
    """Counts for the ratchet, hits for the summary, problems for the gate."""
    declared = {
        _rel(root, p): front_matter(p.read_text(encoding="utf-8")) or {}
        for p in living_documents(root)
    }
    identifiers = identifier_problems(root)
    problems: dict[str, list[str]] = {
        "contract": [],
        "append_only": append_only_problems(root, baseline_ref(root)),
        "milestone_lag": milestone_lag_problems(root),
        "dangling": dangling_document_references(root),
        "identifiers": identifiers.problems,
        "facts": fact_problems(root),
    }
    hits: list[str] = []
    total = 0
    for path in living_documents(root):
        rel = _rel(root, path)
        text = path.read_text(encoding="utf-8")
        problems["contract"] += contract_problems(root, path, declared)
        if _policy(front_matter(text)) in ACCRETION_POLICIES:
            annotations = dated_annotations(text)
            total += len(annotations)
            hits += [f"dated_annotation {rel}:{n} {snippet}" for n, snippet in annotations]
    hits += identifiers.classes + identifiers.exempted
    return {
        "values": {
            "dated_annotations": total,
            "unresolved_class_names": len(identifiers.classes),
            "exempted_in_prose": len(identifiers.exempted),
        },
        "hits": hits,
        "problems": problems,
    }


def flat_problems(rep: dict[str, object]) -> list[str]:
    problems = rep["problems"]
    assert isinstance(problems, dict)
    return [line for group in problems.values() for line in group]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", type=Path, default=None, help="write the JSON report here")
    parser.add_argument("--report", action="store_true", help="print the JSON report")
    parser.add_argument("--check", action="store_true", help="exit 1 on any problem")
    args = parser.parse_args(argv)
    rep = report(args.root)
    if args.write is not None:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    if args.report:
        print(json.dumps(rep, indent=2))
    found = flat_problems(rep)
    print("\n".join(found) if found else "doc policy: contracts, records, and facts hold")
    return 1 if (found and args.check) else 0


if __name__ == "__main__":
    sys.exit(main())
