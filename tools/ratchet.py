#!/usr/bin/env python3
"""Ratchet floors for Thread Digest: measure, compare, bump, loosen. Standard library only.

Usage (from the repo root; the Makefile wraps these):

    uv run python tools/ratchet.py measure [--write PATH]
    uv run python tools/ratchet.py compare [--main-ref REF|none]
    uv run python tools/ratchet.py bump
    uv run python tools/ratchet.py loosen KEY=<family>.<key>[=<value>] REASON="<why>" \
        [HARD_AFTER=YYYY-MM-DD]
    uv run python tools/ratchet.py approve KEY=<family>.<key> [DAYS=14]

Families, one file each under ``.ratchets/`` (``key=value`` lines, sorted, LF, trailing
newline). Direction says which way a value may move without approval.

    coverage.txt      line_percent           up    slack 0.5 point
        totals.percent_covered in .build/coverage.json (0.00 when the report is missing)
    tests.txt         collected              up    slack 2%
        ``def test*`` functions and ``Test*`` methods in test files under tests/ (AST)
                      asserts                up    slack 2%
        ``assert`` statements in test files (AST)
    skips.txt         count                  down  slack 0
        pytest.mark.skip/skipif/xfail and pytest.skip/xfail/importorskip under tests/ (AST)
    suppressions.txt  noqa                   down  slack 0
        ``# noqa`` comments in src/ and tests/ (tokenizer)
                      type_ignore            down  slack 0
        ``# type: ignore`` comments
                      pragma_no_cover        down  slack 0
        ``# pragma: no cover`` comments
                      filterwarnings_ignore  down  slack 0
        filterwarnings/simplefilter("ignore...") calls (AST) and pyproject filterwarnings entries
                      mypy_overrides         down  slack 0
        ``[[tool.mypy.overrides]]`` entries in pyproject.toml
    review_only_rules.txt
                      count                  down  slack 0
        rows of the "Rules and what enforces them" table in CLAUDE.md whose "Enforced by"
        cell names no enforcer that resolves (an existing path, a pytest marker, a ruff
        rule code, a make target) and says "review" instead; each is printed with its
        file:line on every run. ``tests/gates/test_rules_name_their_enforcer.py`` is the
        gate: a row that neither resolves nor says "review" fails there, and this ceiling
        is what keeps the review-only count going down and never up.
    docs.txt          dated_annotations      down  slack 0
        read from .build/doc_policy.json, which tools/doc_policy.py writes: the dated
        parenthetical annotations in prune-stale, rewritten, and versioned documents (an
        accreting annotation count means a rewrite is due, never another annotation)
    code_health.txt   cognitive_over_15      down  slack 0
                      cyclomatic_over_15     down  slack 0
                      mi_below_a             down  slack 0
                      size_rule_violations   down  slack 0
                      dead_code              down  slack 0
                      dead_code_whitelisted  down  slack 0
                      duplicate_blocks       down  slack 0
        read from .build/code_health.json, which tools/code_health.py writes from complexipy,
        radon, ruff's size rules, vulture with a counted whitelist, and pylint's duplicate-code
        (Wes, 2026-09-14: maintainability passes on its own, judged by analysis, never by a
        model). A missing or partial report is an error, never a zero, and every offender the
        report names is printed with its location.

Counting is structural (AST and tokenizer), so a marker inside a string literal is not a
suppression and a comment rewrap cannot hide one. Every skip and suppression is printed
with its file:line on every run.

A relaxed line may carry an expiry date on the line below it:

    count=3
    count.hard_after=2026-11-12

``compare`` prints every live relaxation on every run and turns RED once today is past the
date, naming the metric and the way back (tighten it, or re-approve through ``loosen``), so
a deliberate relaxation cannot quietly become permanent. ``bump`` carries the dates over
untouched, and clears one once a ceiling has reached zero (the relaxation is over; a date
left behind would go red for nothing); ``loosen`` writes one when given
``HARD_AFTER=YYYY-MM-DD``, which is also how an existing relaxation gets a date without
hand-editing ``.ratchets/``.

``compare`` makes three comparisons and exits 0 (ok), 1 (red, stale or expired) or 3
(loosening):

1. measured vs file: a move against direction beyond the slack is RED;
2. file vs ``render(measured)``: a floor lagging the measurement beyond the slack, an
   unknown or missing key, or non-canonical formatting is STALE ("run make ratchet-bump");
3. file vs ``git show <main>:.ratchets/<family>.txt``: a value moved against direction
   relative to main, or a key removed, is a LOOSENING that needs approval and a row in
   docs/runbook/GUARDS.md (which ``loosen`` writes). The ref is ``--main-ref``, else
   ``$RATCHET_MAIN_REF``, else the first of ``main`` / ``origin/main`` that exists; when
   none exists the run is red (CI must fetch main). ``--main-ref none`` skips it.

``bump`` writes the measured values, keeping (never moving) any value that would go
against direction; it exits 1 when a kept value is outside the slack, i.e. when only
``loosen`` can make the tree green. ``loosen`` writes one value, refuses anything looser
than the measurement, and appends a ledger row under ``## Loosenings`` in GUARDS.md; with
``HARD_AFTER`` and the value the file already holds it only stamps the expiry date.

``approve`` is the third step, and the one a person takes (KI-056, 2026-09-18). Comparison
3 keeps reporting a loosening until the loosened value is itself on main, and it could not
get there: the merge guard wants the green stamp ``make check`` writes only after a green
comparison, so the first real loosening had no way to land. ``approve`` reads the move
waiting on this tree (the value on main against the value here), refuses unless ``loosen``
has already put its reason in the ledger, prints the move with that reason, and asks for a
line of confirmation typed at a terminal -- refusing outright when stdin is not one, so the
agent that wrote the loosening cannot also permit it. What it writes is one small file per
key beside the floors, naming the key, the two values, and a date after which it stops
covering anything (fourteen days by default, ninety at most). A comparison finds it and
reports APPROVED instead of LOOSENING; a move to any other value, or a date gone by, is a
loosening again. ``bump`` removes an approval once it has expired, and anything it cannot
read as one, because the ledger row is the permanent record and a permission that covers
nothing is litter on an enforcement surface.
"""

from __future__ import annotations

import argparse
import ast
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
import tokenize
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

RATCHET_DIR = ".ratchets"
HARD_AFTER = "hard_after"
DATE_TEXT = re.compile(r"^\d{4}-\d{2}-\d{2}$")
LEDGER_PATH = Path("docs") / "runbook" / "GUARDS.md"
LEDGER_HEADING = "## Loosenings"
LEDGER_HEADER = "| Date | Key | From | To | Reason | PR |"
LEDGER_SEPARATOR = "|---|---|---|---|---|---|"
COVERAGE_JSON = Path(".build") / "coverage.json"
CODE_HEALTH_JSON = Path(".build") / "code_health.json"
DOC_POLICY_JSON = Path(".build") / "doc_policy.json"
MAIN_REF_ENV = "RATCHET_MAIN_REF"
DEFAULT_MAIN_REFS = ("main", "origin/main")
APPROVALS_DIR = Path(RATCHET_DIR) / "approvals"
APPROVAL_DAYS = 14
MAX_APPROVAL_DAYS = 90

EXIT_OK = 0
EXIT_RED = 1
EXIT_LOOSENING = 3
EPS = 1e-9
UP = "up"
DOWN = "down"

Number = int | float


def fail(message: str) -> NoReturn:
    """Exit 1 with a one-line reason on stderr."""
    raise SystemExit(message)


@dataclass(frozen=True)
class Spec:
    family: str
    key: str
    direction: str
    slack_abs: float = 0.0
    slack_pct: float = 0.0
    is_float: bool = False

    @property
    def name(self) -> str:
        return f"{self.family}.{self.key}"

    @property
    def bound(self) -> str:
        return "floor" if self.direction == UP else "ceiling"

    def tolerance(self, reference: Number) -> float:
        return self.slack_abs + self.slack_pct * abs(reference)

    def parse(self, raw: str) -> Number:
        return float(raw) if self.is_float else int(raw)

    def fmt(self, value: Number) -> str:
        return f"{value:.2f}" if self.is_float else str(int(value))

    def against(self, new: Number, old: Number) -> bool:
        """True when ``new`` moves against this ratchet's direction relative to ``old``."""
        return new < old if self.direction == UP else new > old


SPECS: tuple[Spec, ...] = (
    Spec("coverage", "line_percent", UP, slack_abs=0.5, is_float=True),
    Spec("tests", "collected", UP, slack_pct=0.02),
    Spec("tests", "asserts", UP, slack_pct=0.02),
    Spec("skips", "count", DOWN),
    Spec("suppressions", "noqa", DOWN),
    Spec("suppressions", "type_ignore", DOWN),
    Spec("suppressions", "pragma_no_cover", DOWN),
    Spec("suppressions", "filterwarnings_ignore", DOWN),
    Spec("suppressions", "mypy_overrides", DOWN),
    Spec("review_only_rules", "count", DOWN),
    Spec("review_only_rules", "guards_without_control", DOWN),
    Spec("code_health", "cognitive_over_15", DOWN),
    Spec("code_health", "cyclomatic_over_15", DOWN),
    Spec("code_health", "mi_below_a", DOWN),
    Spec("code_health", "size_rule_violations", DOWN),
    Spec("code_health", "dead_code", DOWN),
    Spec("code_health", "dead_code_whitelisted", DOWN),
    Spec("code_health", "duplicate_blocks", DOWN),
    Spec("docs", "dated_annotations", DOWN),
    Spec("docs", "unresolved_class_names", DOWN),
    Spec("docs", "exempted_in_prose", DOWN),
)
FAMILIES: tuple[str, ...] = tuple(dict.fromkeys(spec.family for spec in SPECS))


def specs_for(family: str) -> list[Spec]:
    return sorted((spec for spec in SPECS if spec.family == family), key=lambda spec: spec.key)


def spec_by_name(name: str) -> Spec | None:
    return next((spec for spec in SPECS if spec.name == name), None)


# --------------------------------------------------------------------------- measuring


@dataclass
class Measurement:
    values: dict[str, dict[str, Number]]
    hits: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    def to_json(self) -> dict[str, object]:
        out: dict[str, object] = {family: dict(self.values[family]) for family in FAMILIES}
        out["hits"] = list(self.hits)
        out["notes"] = list(self.notes)
        return out


def _py_files(base: Path) -> list[Path]:
    if not base.is_dir():
        return []
    return sorted(p for p in base.rglob("*.py") if "__pycache__" not in p.parts)


def _test_files(root: Path) -> list[Path]:
    return [
        p
        for p in _py_files(root / "tests")
        if p.name.startswith("test_") or p.name.endswith("_test.py")
    ]


def _parse_module(path: Path) -> ast.Module:
    try:
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError as exc:
        msg = f"ratchet: cannot parse {path}: {exc}"
        raise SystemExit(msg) from exc


def _dotted(node: ast.expr) -> str:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if not isinstance(node, ast.Name):
        return ""
    parts.append(node.id)
    return ".".join(reversed(parts))


def _is_test_function(node: ast.stmt) -> bool:
    return isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test")


def count_tests(tree: ast.Module) -> int:
    total = 0
    for node in tree.body:
        if _is_test_function(node):
            total += 1
        elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            total += sum(1 for sub in node.body if _is_test_function(sub))
    return total


def count_asserts(tree: ast.Module) -> int:
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.Assert))


SKIP_MARKS = frozenset({"skip", "skipif", "xfail"})
SKIP_CALLS = frozenset({"skip", "xfail", "importorskip"})


def skip_hits(tree: ast.Module, rel: str) -> list[str]:
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Attribute):
            continue
        base = _dotted(node.value)
        if base.endswith("mark") and node.attr in SKIP_MARKS:
            hits.append(f"{rel}:{node.lineno} pytest.mark.{node.attr}")
        elif base == "pytest" and node.attr in SKIP_CALLS:
            hits.append(f"{rel}:{node.lineno} pytest.{node.attr}")
    return hits


COMMENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "noqa": re.compile(r"#\s*noqa\b", re.IGNORECASE),
    "type_ignore": re.compile(r"#\s*type:\s*ignore\b"),
    "pragma_no_cover": re.compile(r"#\s*pragma:\s*no\s+cover\b"),
}


def comment_hits(path: Path, rel: str) -> list[tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    try:
        tokens = list(tokenize.generate_tokens(io.StringIO(text).readline))
    except tokenize.TokenError as exc:
        msg = f"ratchet: cannot tokenize {path}: {exc}"
        raise SystemExit(msg) from exc
    hits = []
    for tok in tokens:
        if tok.type != tokenize.COMMENT:
            continue
        for key, pattern in COMMENT_PATTERNS.items():
            hits.extend((key, f"{rel}:{tok.start[0]} {key}") for _ in pattern.finditer(tok.string))
    return hits


WARNING_FILTER_CALLS = frozenset({"filterwarnings", "simplefilter"})


def _string_arg(node: ast.expr | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def warning_filter_hits(tree: ast.Module, rel: str) -> list[str]:
    hits = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        name = _dotted(node.func).rsplit(".", 1)[-1]
        if name not in WARNING_FILTER_CALLS:
            continue
        action = _string_arg(node.args[0]) if node.args else None
        for keyword in node.keywords:
            if keyword.arg == "action":
                action = _string_arg(keyword.value)
        if action is not None and action.startswith("ignore"):
            hits.append(f"{rel}:{node.lineno} {name}({action!r})")
    return hits


def pyproject_hits(root: Path) -> tuple[list[str], list[str]]:
    path = root / "pyproject.toml"
    if not path.is_file():
        return [], []
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    tool = data.get("tool", {})
    filters = tool.get("pytest", {}).get("ini_options", {}).get("filterwarnings", [])
    if isinstance(filters, str):
        filters = [filters]
    filter_hits = [
        f"pyproject.toml filterwarnings {entry!r}"
        for entry in filters
        if str(entry).startswith("ignore")
    ]
    overrides = tool.get("mypy", {}).get("overrides", [])
    override_hits = [
        f"pyproject.toml [[tool.mypy.overrides]] module={entry.get('module')!r}"
        for entry in overrides
    ]
    return filter_hits, override_hits


def measure_coverage(path: Path, notes: list[str]) -> float:
    if not path.is_file():
        notes.append(f"coverage report {path} missing; line_percent measured as 0.00")
        return 0.0
    data = json.loads(path.read_text(encoding="utf-8"))
    return round(float(data["totals"]["percent_covered"]), 2)


def measure_code_health(path: Path, hits: list[str]) -> dict[str, Number]:
    """The counts ``tools/code_health.py`` measured, with its offenders as hits.

    A missing or partial report is an error rather than a zero: a ceiling read as zero would be
    green for the wrong reason (fail, never skip). ``make check`` writes the report first, and
    ``make ratchet-bump`` / ``make ratchet-loosen`` depend on the same target.
    """
    if not path.is_file():
        fail(f"ratchet: code health report {path} missing; run make code-health (make check does)")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        values: dict[str, Number] = {
            spec.key: int(data["values"][spec.key]) for spec in specs_for("code_health")
        }
    except (ValueError, KeyError, TypeError) as exc:
        msg = f"ratchet: code health report {path} unreadable: {exc!r}"
        raise SystemExit(msg) from exc
    reported = data.get("hits", [])
    if not isinstance(reported, list):
        fail(f"ratchet: code health report {path} unreadable: hits is not a list")
    hits.extend(f"{hit} [code-health]" for hit in reported)
    return values


def measure_docs(path: Path, hits: list[str]) -> dict[str, Number]:
    """The counts ``tools/doc_policy.py`` measured, with each dated annotation as a hit.

    Like the code-health report: missing or partial is an error, never a zero.
    """
    if not path.is_file():
        fail(f"ratchet: doc policy report {path} missing; run make doc-policy (make check does)")
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        values: dict[str, Number] = {
            spec.key: int(data["values"][spec.key]) for spec in specs_for("docs")
        }
    except (ValueError, KeyError, TypeError) as exc:
        msg = f"ratchet: doc policy report {path} unreadable: {exc!r}"
        raise SystemExit(msg) from exc
    reported = data.get("hits", [])
    if not isinstance(reported, list):
        fail(f"ratchet: doc policy report {path} unreadable: hits is not a list")
    hits.extend(f"{hit} [doc-policy]" for hit in reported)
    return values


def measure(
    root: Path,
    coverage_json: Path,
    code_health_json: Path | None = None,
    doc_policy_json: Path | None = None,
) -> Measurement:
    notes: list[str] = []
    hits: list[str] = []
    counts = {"noqa": 0, "type_ignore": 0, "pragma_no_cover": 0, "filterwarnings_ignore": 0}
    collected = asserts = skips = 0

    for path in _test_files(root):
        tree = _parse_module(path)
        collected += count_tests(tree)
        asserts += count_asserts(tree)

    for path in _py_files(root / "tests"):
        rel = path.relative_to(root).as_posix()
        found = skip_hits(_parse_module(path), rel)
        skips += len(found)
        hits.extend(found)

    for base in ("src", "tests"):
        for path in _py_files(root / base):
            rel = path.relative_to(root).as_posix()
            for key, hit in comment_hits(path, rel):
                counts[key] += 1
                hits.append(hit)
            found = warning_filter_hits(_parse_module(path), rel)
            counts["filterwarnings_ignore"] += len(found)
            hits.extend(found)

    filter_hits, override_hits = pyproject_hits(root)
    counts["filterwarnings_ignore"] += len(filter_hits)
    hits.extend(filter_hits)
    hits.extend(override_hits)

    values: dict[str, dict[str, Number]] = {
        "coverage": {"line_percent": measure_coverage(coverage_json, notes)},
        "tests": {"collected": collected, "asserts": asserts},
        "skips": {"count": skips},
        "suppressions": {**counts, "mypy_overrides": len(override_hits)},
        "review_only_rules": {
            "count": measure_rules(root, hits, notes),
            "guards_without_control": measure_guards(root, hits, notes),
        },
        "code_health": measure_code_health(code_health_json or root / CODE_HEALTH_JSON, hits),
        "docs": measure_docs(doc_policy_json or root / DOC_POLICY_JSON, hits),
    }
    return Measurement(values=values, hits=hits, notes=notes)


# ----------------------------------------------------------- rules and their enforcers

RULES_DOC = "CLAUDE.md"
RULES_SECTION = "## Rules and what enforces them"
CELL_SPLIT = re.compile(r"(?<!\\)\|")
BACKTICKED = re.compile(r"`([^`]+)`")
REVIEW_WORD = re.compile(r"review", re.IGNORECASE)
RUFF_CODE = re.compile(r"^[A-Z]{1,5}\d{0,4}\*?$")
MAKE_INVOCATION = re.compile(r"^make\s+([A-Za-z0-9_.-]+)$")
MAKE_TARGET = re.compile(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", re.MULTILINE)

ENFORCED = "enforced"
REVIEW_ONLY = "review-only"
UNENFORCED = "unenforced"


def split_row(line: str) -> list[str]:
    r"""Cells of a markdown table row, honouring ``\|`` escapes inside a cell."""
    stripped = line.strip()
    if not stripped.startswith("|"):
        return []
    return [cell.strip() for cell in CELL_SPLIT.split(stripped)[1:-1]]


def is_separator_row(cells: list[str]) -> bool:
    return bool(cells) and all(cell and set(cell) <= set("-: ") for cell in cells)


@dataclass(frozen=True)
class Rule:
    """One row of the rules table: the rule, what the row claims enforces it, and whether
    that claim resolves to something installed."""

    line: int
    rule: str
    enforcer: str
    status: str
    resolved: tuple[str, ...] = ()

    def describe(self) -> str:
        return f"{RULES_DOC}:{self.line} {self.rule}"


@dataclass(frozen=True)
class Enforcers:
    """What a backticked token in an "Enforced by" cell may resolve to: a path in the tree
    (a test, a hook script, a tool, a config file), a declared pytest marker, a selected
    ruff rule code, or a target the Makefile actually defines."""

    root: Path
    markers: frozenset[str]
    ruff_codes: tuple[str, ...]
    make_targets: frozenset[str]

    def is_path(self, token: str) -> bool:
        head = token.split("::", 1)[0].strip()
        if not head or " " in head or ".." in head or head.startswith(("/", "-")):
            return False
        return (self.root / head).exists()

    def is_ruff_code(self, token: str) -> bool:
        if not RUFF_CODE.match(token):
            return False
        code = token.rstrip("*")
        return any(code.startswith(sel) or sel.startswith(code) for sel in self.ruff_codes)

    def is_make_target(self, token: str) -> bool:
        match = MAKE_INVOCATION.match(token)
        return match is not None and match.group(1) in self.make_targets

    def resolves(self, token: str) -> bool:
        return (
            self.is_path(token)
            or token in self.markers
            or self.is_ruff_code(token)
            or self.is_make_target(token)
        )


def enforcers_for(root: Path) -> Enforcers:
    markers: set[str] = set()
    codes: list[str] = []
    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        tool = tomllib.loads(pyproject.read_text(encoding="utf-8")).get("tool", {})
        for entry in tool.get("pytest", {}).get("ini_options", {}).get("markers", []):
            markers.add(str(entry).split(":", 1)[0].strip())
        codes = [str(code) for code in tool.get("ruff", {}).get("lint", {}).get("select", [])]
    makefile = root / "Makefile"
    targets: list[str] = []
    if makefile.is_file():
        targets = MAKE_TARGET.findall(makefile.read_text(encoding="utf-8"))
    return Enforcers(root, frozenset(markers), tuple(codes), frozenset(targets))


def rule_rows(text: str) -> list[tuple[int, list[str]]]:
    """``(line number, cells)`` for every data row of the rules table in CLAUDE.md."""
    rows: list[tuple[int, list[str]]] = []
    inside = False
    for number, line in enumerate(text.splitlines(), start=1):
        if line.strip() == RULES_SECTION:
            inside = True
            continue
        if not inside:
            continue
        if line.startswith("## "):
            break
        cells = split_row(line)
        if not cells or is_separator_row(cells):
            continue
        if [cell.lower() for cell in cells] == ["rule", "enforced by"]:
            continue
        rows.append((number, cells))
    return rows


def classify_rules(root: Path) -> list[Rule]:
    """Every rule row with the status of its "Enforced by" cell.

    A cell naming at least one enforcer that resolves is ``enforced``, even when it also
    mentions review: what makes a rule review-only is having nothing mechanical behind it,
    and counting the belt-and-braces rows would inflate the ceiling and leave room for a
    genuinely unenforced rule to slip in under it. A cell with no resolving enforcer that
    says "review" is ``review-only`` (Wes 2026-09-13: label it, do not pretend); anything
    else is ``unenforced`` and fails the gate.
    """
    path = root / RULES_DOC
    if not path.is_file():
        return []
    enforcers = enforcers_for(root)
    rules: list[Rule] = []
    for number, cells in rule_rows(path.read_text(encoding="utf-8")):
        if len(cells) != 2:
            rules.append(Rule(number, " | ".join(cells), "", UNENFORCED))
            continue
        rule, enforcer = cells
        resolved = tuple(t for t in BACKTICKED.findall(enforcer) if enforcers.resolves(t))
        if resolved:
            status = ENFORCED
        elif REVIEW_WORD.search(enforcer):
            status = REVIEW_ONLY
        else:
            status = UNENFORCED
        rules.append(Rule(number, rule, enforcer, status, resolved))
    return rules


def rules_with(rules: Iterable[Rule], status: str) -> list[Rule]:
    return [rule for rule in rules if rule.status == status]


def measure_rules(root: Path, hits: list[str], notes: list[str]) -> int:
    """Count the review-only rules, printing each one the way a suppression is printed."""
    if not (root / RULES_DOC).is_file():
        notes.append(f"{RULES_DOC} missing; review_only_rules measured as 0")
        return 0
    review_only = rules_with(classify_rules(root), REVIEW_ONLY)
    hits.extend(f"{rule.describe()} [review-only]" for rule in review_only)
    return len(review_only)


GUARDS_DOC = "docs/runbook/GUARDS.md"
GUARDS_ACTIVE_HEADING = "## Active"
CONTROL_COLUMN = "Positive control node"
NODE_ID_IN_CELL = re.compile(r"tests/[\w./-]+\.py")
EXTERNAL_CONTROL = re.compile(r"\bexternal\b", re.IGNORECASE)


def measure_guards(root: Path, hits: list[str], notes: list[str]) -> int:
    """Count the Active guards ledger rows with no positive control (2026-09-14).

    The ledger's own preamble calls a blank control cell a failure, and three rows read
    ``none yet`` regardless. A row counts unless its control cell names a test file or says the
    control is external (a hook or a pre-commit stage that cannot be planted from inside the
    suite and carries a dated "seen red" line instead). Printed like a suppression; the count is
    a ceiling in ``.ratchets/review_only_rules.txt`` that only goes down.
    """
    path = root / GUARDS_DOC
    if not path.is_file():
        notes.append(f"{GUARDS_DOC} missing; guards_without_control measured as 0")
        return 0
    count = 0
    index: int | None = None
    in_active = False
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if line.startswith("## "):
            in_active = line.strip() == GUARDS_ACTIVE_HEADING
            index = None
            continue
        if not in_active:
            continue
        cells = split_row(line)
        if not cells:
            index = None
        elif CONTROL_COLUMN in cells:
            index = cells.index(CONTROL_COLUMN)
        elif index is not None and index < len(cells) and not is_separator_row(cells):
            cell = cells[index]
            if not NODE_ID_IN_CELL.search(cell) and not EXTERNAL_CONTROL.search(cell):
                count += 1
                hits.append(
                    f"{GUARDS_DOC}:{number}: {cells[0]} has no positive control "
                    "[guard-without-control]"
                )
    return count


# --------------------------------------------------------------------------- files


def date_key(key: str) -> str:
    """The ``hard_after`` line that belongs to ``key``; it sorts right after it."""
    return f"{key}.{HARD_AFTER}"


def render_family(
    family: str, values: dict[str, Number], dates: dict[str, str] | None = None
) -> str:
    dates = dates or {}
    lines: list[str] = []
    for spec in specs_for(family):
        lines.append(f"{spec.key}={spec.fmt(values[spec.key])}\n")
        if spec.key in dates:
            lines.append(f"{date_key(spec.key)}={dates[spec.key]}\n")
    return "".join(lines)


def parse_family_text(text: str) -> dict[str, str]:
    raw: dict[str, str] = {}
    for line in text.splitlines():
        if not line.strip():
            continue
        key, sep, value = line.partition("=")
        if not sep:
            msg = f"line without '=': {line!r}"
            raise ValueError(msg)
        raw[key.strip()] = value.strip()
    return raw


def family_path(root: Path, family: str) -> Path:
    return root / RATCHET_DIR / f"{family}.txt"


def read_family_text(root: Path, family: str) -> str | None:
    """Raw file text with line endings preserved, so CRLF is visible to the canonical check."""
    path = family_path(root, family)
    if not path.is_file():
        return None
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def read_family_values(root: Path, family: str) -> dict[str, Number]:
    """Lenient read: known keys that parse; missing file or bad lines yield fewer keys."""
    text = read_family_text(root, family)
    if text is None:
        return {}
    try:
        raw = parse_family_text(text)
    except ValueError:
        return {}
    values: dict[str, Number] = {}
    for spec in specs_for(family):
        try:
            values[spec.key] = spec.parse(raw[spec.key])
        except (KeyError, ValueError):
            continue
    return values


def read_family_dates(root: Path, family: str) -> dict[str, str]:
    """Lenient read of the ``<key>.hard_after`` lines, so bump and loosen carry them over."""
    text = read_family_text(root, family)
    if text is None:
        return {}
    try:
        raw = parse_family_text(text)
    except ValueError:
        return {}
    return {
        spec.key: raw[date_key(spec.key)] for spec in specs_for(family) if date_key(spec.key) in raw
    }


def write_family(
    root: Path, family: str, values: dict[str, Number], dates: dict[str, str] | None = None
) -> None:
    path = family_path(root, family)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_family(family, values, dates))
    os.replace(tmp, path)


# --------------------------------------------------------------------------- git


def _git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return proc.stdout if proc.returncode == 0 else None


def ref_exists(root: Path, ref: str) -> bool:
    return _git(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}") is not None


def resolve_main_ref(root: Path, explicit: str | None) -> str | None:
    """The ref holding the committed floors, or None when the check is explicitly skipped."""
    chosen = explicit or os.environ.get(MAIN_REF_ENV)
    if chosen:
        if chosen.lower() == "none":
            return None
        if not ref_exists(root, chosen):
            fail(f"ratchet: main ref {chosen!r} not found in {root}")
        return chosen
    for candidate in DEFAULT_MAIN_REFS:
        if ref_exists(root, candidate):
            return candidate
    fail(
        "ratchet: no main baseline found (neither 'main' nor 'origin/main' exists); "
        "fetch main, pass --main-ref REF, or --main-ref none to skip the loosening check"
    )


def main_family_values(root: Path, ref: str, family: str) -> dict[str, Number] | None:
    text = _git(root, "show", f"{ref}:{RATCHET_DIR}/{family}.txt")
    if text is None:
        return None
    try:
        raw = parse_family_text(text)
    except ValueError:
        return None
    values: dict[str, Number] = {}
    for spec in specs_for(family):
        try:
            values[spec.key] = spec.parse(raw[spec.key])
        except (KeyError, ValueError):
            continue
    return values


# --------------------------------------------------------------------------- approvals


@dataclass(frozen=True)
class Approval:
    """One operator approval: this key may move from ``frm`` to ``to``, until ``expires``.

    Birth incident, 2026-09-18 (KI-056): the loosening comparison reads the floors here
    against the floors committed on main, so a loosening keeps firing until the loosened
    value is itself on main -- and it could not get there, because the merge guard wants the
    green stamp ``make check`` writes only after a green comparison. The approval is the way
    through, and it is deliberately narrow: it names one key and one move, it is written only
    by ``approve`` (which a person drives at a terminal), and it stops covering anything once
    it expires, so a permission cannot outlive the change it was granted for.
    """

    key: str
    frm: Number
    to: Number
    granted: dt.date
    expires: dt.date


def approval_path(root: Path, spec: Spec) -> Path:
    return root / APPROVALS_DIR / f"{spec.name}.txt"


def render_approval(spec: Spec, approval: Approval) -> str:
    return (
        f"key={approval.key}\n"
        f"from={spec.fmt(approval.frm)}\n"
        f"to={spec.fmt(approval.to)}\n"
        f"granted={approval.granted.isoformat()}\n"
        f"expires={approval.expires.isoformat()}\n"
    )


def read_approval(root: Path, spec: Spec) -> Approval | None:
    """Fail closed: anything that is not a readable approval for this key is no approval."""
    path = approval_path(root, spec)
    if not path.is_file():
        return None
    try:
        raw = parse_family_text(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return None
    granted = parse_date(raw.get("granted", ""))
    expires = parse_date(raw.get("expires", ""))
    if granted is None or expires is None or raw.get("key") != spec.name:
        return None
    try:
        return Approval(spec.name, spec.parse(raw["from"]), spec.parse(raw["to"]), granted, expires)
    except (KeyError, ValueError):
        return None


def write_approval(root: Path, spec: Spec, approval: Approval) -> Path:
    path = approval_path(root, spec)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_approval(spec, approval))
    os.replace(tmp, path)
    return path


def clear_spent_approvals(root: Path, today: dt.date | None = None) -> None:
    """``bump`` sweeps approvals that have expired, and anything there it cannot read.

    An approval that covers nothing is litter on an enforcement surface, which is the thing
    this project is built to avoid; the ledger row under ``## Loosenings`` is the permanent
    record, so removing the permission loses no history. Both branches are announced.
    """
    directory = root / APPROVALS_DIR
    if not directory.is_dir():
        return
    now = today or dt.date.today()
    for path in sorted(directory.glob("*.txt")):
        spec = spec_by_name(path.stem)
        approval = read_approval(root, spec) if spec is not None else None
        if approval is None:
            path.unlink()
            print(f"SPENT     {path.stem:<34} removed; not a readable approval for a known key")
        elif now > approval.expires:
            path.unlink()
            print(
                f"SPENT     {path.stem:<34} approval removed, expired "
                f"{approval.expires.isoformat()}; the GUARDS.md row is the record"
            )


def ledger_reason(root: Path, spec: Spec, frm: Number, to: Number) -> str | None:
    """The reason cell of the last ``## Loosenings`` row for exactly this move, or None.

    The reason is read rather than retyped so the operator approves against what the ledger
    will say, not against a second description of it (one home per fact).
    """
    path = root / LEDGER_PATH
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if LEDGER_HEADING not in text:
        return None
    section = text.split(LEDGER_HEADING, 1)[1].split("\n## ", 1)[0]
    found: str | None = None
    for line in section.splitlines():
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        # Cells 1 to 3 are Key, From and To, all of them before the reason, so a reason
        # carrying an escaped pipe cannot shift the columns this match reads.
        if len(cells) >= 5 and [cells[1], cells[2], cells[3]] == [
            spec.name,
            spec.fmt(frm),
            spec.fmt(to),
        ]:
            found = cells[4]
    return found


# --------------------------------------------------------------------------- compare


@dataclass(frozen=True)
class Finding:
    status: str
    subject: str
    detail: str

    def line(self) -> str:
        return f"{self.status:<9} {self.subject:<34} {self.detail}"


def _compare_values(spec: Spec, floor: Number, measured: Number) -> Finding:
    tol = spec.tolerance(floor)
    gap = abs(measured - floor)
    if spec.against(measured, floor) and gap > tol + EPS:
        word = "below" if spec.direction == UP else "above"
        return Finding(
            "RED",
            spec.name,
            f"measured {spec.fmt(measured)} is {word} the {spec.bound} {spec.fmt(floor)} "
            f"(slack {tol:g})",
        )
    if gap > tol + EPS:
        return Finding(
            "STALE",
            spec.name,
            f"{spec.bound} {spec.fmt(floor)} lags measured {spec.fmt(measured)} "
            f"(slack {tol:g}); run make ratchet-bump",
        )
    return Finding("OK", spec.name, f"{spec.bound}={spec.fmt(floor)} measured={spec.fmt(measured)}")


def parse_date(raw: str) -> dt.date | None:
    if not DATE_TEXT.match(raw):
        return None
    try:
        return dt.date.fromisoformat(raw)
    except ValueError:
        return None


def _compare_expiry(spec: Spec, raw_date: str, today: dt.date | None = None) -> Finding:
    """Every live relaxation is printed on every run; past its date it is RED.

    Wes, 2026-09-13: a deliberately relaxed check carries a date after which it turns red
    unless re-approved, so "temporary" cannot quietly become permanent.
    """
    deadline = parse_date(raw_date)
    if deadline is None:
        return Finding("RED", f"{spec.name}.{HARD_AFTER}", f"{raw_date!r} is not YYYY-MM-DD")
    if (today or dt.date.today()) > deadline:
        return Finding(
            "EXPIRED",
            spec.name,
            f"relaxation expired {raw_date}: tighten the {spec.bound}, or re-approve with "
            f'make ratchet-loosen KEY={spec.name} REASON="..." HARD_AFTER=<new date>',
        )
    return Finding(
        "RELAXED",
        spec.name,
        f"relaxed {spec.bound}, hard_after={raw_date}: red from the day after unless "
        "tightened or re-approved",
    )


def compare_family_file(
    root: Path, family: str, measured: dict[str, Number]
) -> tuple[list[Finding], dict[str, Number] | None]:
    """Comparisons 1 and 2. Returns findings and the parsed file values (None if unusable)."""
    text = read_family_text(root, family)
    if text is None:
        return [
            Finding("RED", family, f"{RATCHET_DIR}/{family}.txt missing; run make ratchet-bump")
        ], None
    try:
        raw = parse_family_text(text)
    except ValueError as exc:
        return [Finding("STALE", family, f"unparseable ({exc}); run make ratchet-bump")], None

    findings: list[Finding] = []
    values: dict[str, Number] = {}
    dates: dict[str, str] = {}
    for spec in specs_for(family):
        if spec.key not in raw:
            findings.append(Finding("STALE", spec.name, "missing from file; run make ratchet-bump"))
            continue
        try:
            values[spec.key] = spec.parse(raw[spec.key])
        except ValueError:
            findings.append(Finding("STALE", spec.name, f"unparseable value {raw[spec.key]!r}"))
        if date_key(spec.key) in raw:
            raw_date = raw[date_key(spec.key)]
            if parse_date(raw_date) is None:
                findings.append(
                    Finding("RED", f"{spec.name}.{HARD_AFTER}", f"{raw_date!r} is not YYYY-MM-DD")
                )
            else:
                dates[spec.key] = raw_date
    known = {spec.key for spec in specs_for(family)}
    for key in raw:
        if key not in known and key not in {date_key(k) for k in known}:
            findings.append(
                Finding("STALE", f"{family}.{key}", "unknown key; run make ratchet-bump")
            )
    if findings:
        return findings, None

    if text != render_family(family, values, dates):
        findings.append(
            Finding(
                "STALE",
                family,
                f"{family}.txt is not canonical (hand-edited?); run make ratchet-bump",
            )
        )
    findings.extend(
        _compare_values(spec, values[spec.key], measured[spec.key]) for spec in specs_for(family)
    )
    findings.extend(
        _compare_expiry(spec, dates[spec.key]) for spec in specs_for(family) if spec.key in dates
    )
    return findings, values


def _judge_loosening(
    root: Path, spec: Spec, frm: Number, to: Number, ref: str, today: dt.date | None = None
) -> Finding:
    """A loosening is red until an approval on file names this exact move and is still live."""
    move = f"{spec.fmt(frm)} on {ref} -> {spec.fmt(to)} here"
    rel = (APPROVALS_DIR / f"{spec.name}.txt").as_posix()
    approval = read_approval(root, spec)
    if approval is None:
        return Finding(
            "LOOSENING",
            spec.name,
            f"{move}; needs approval and a GUARDS.md row (make ratchet-loosen, then "
            f"make ratchet-approve KEY={spec.name})",
        )
    if (approval.frm, approval.to) != (frm, to):
        return Finding(
            "LOOSENING",
            spec.name,
            f"{move}; the approval in {rel} is for {spec.fmt(approval.frm)} -> "
            f"{spec.fmt(approval.to)}, not this move; re-approve",
        )
    if (today or dt.date.today()) > approval.expires:
        return Finding(
            "LOOSENING",
            spec.name,
            f"{move}; the approval in {rel} expired {approval.expires.isoformat()}; "
            f"re-approve with make ratchet-approve KEY={spec.name}",
        )
    return Finding(
        "APPROVED",
        spec.name,
        f"{move}; approved {approval.granted.isoformat()}, expires "
        f"{approval.expires.isoformat()} ({rel})",
    )


def compare_family_main(
    root: Path, family: str, values: dict[str, Number], ref: str
) -> list[Finding]:
    """Comparison 3: the file against the floors committed on main."""
    on_main = main_family_values(root, ref, family)
    if on_main is None:
        return [Finding("NOTE", family, f"no baseline on {ref} (new family)")]
    findings = []
    for spec in specs_for(family):
        if spec.key not in on_main:
            continue
        if spec.key not in values:
            # A removed key has no "to" value, so no approval can name the move; the way
            # back is to restore the key with bump, not to approve its absence.
            findings.append(Finding("LOOSENING", spec.name, f"present on {ref}, removed here"))
        elif spec.against(values[spec.key], on_main[spec.key]):
            findings.append(_judge_loosening(root, spec, on_main[spec.key], values[spec.key], ref))
    return findings


def compare(root: Path, measurement: Measurement, main_ref: str | None) -> list[Finding]:
    findings: list[Finding] = []
    if main_ref is None:
        findings.append(Finding("NOTE", "main", "loosening check skipped (--main-ref none)"))
    for family in FAMILIES:
        file_findings, values = compare_family_file(root, family, measurement.values[family])
        findings.extend(file_findings)
        if values is not None and main_ref is not None:
            findings.extend(compare_family_main(root, family, values, main_ref))
    return findings


def exit_code(findings: Iterable[Finding]) -> int:
    statuses = {finding.status for finding in findings}
    if statuses & {"RED", "STALE", "EXPIRED"}:
        return EXIT_RED
    if "LOOSENING" in statuses:
        return EXIT_LOOSENING
    return EXIT_OK


# --------------------------------------------------------------------------- bump / loosen


def bump(root: Path, measurement: Measurement) -> int:
    rc = EXIT_OK
    clear_spent_approvals(root)
    for family in FAMILIES:
        current = read_family_values(root, family)
        dates = read_family_dates(root, family)
        new: dict[str, Number] = {}
        for spec in specs_for(family):
            measured = measurement.values[family][spec.key]
            old = current.get(spec.key)
            if old is not None and spec.against(measured, old):
                new[spec.key] = old
                beyond = abs(measured - old) > spec.tolerance(old) + EPS
                print(
                    f"KEPT      {spec.name:<34} measured {spec.fmt(measured)} would loosen the "
                    f"{spec.bound} {spec.fmt(old)}; refusing (use make ratchet-loosen "
                    f'KEY={spec.name} REASON="...")'
                )
                if beyond:
                    rc = EXIT_RED
            else:
                new[spec.key] = measured
                was = f" (was {spec.fmt(old)})" if old is not None else ""
                print(f"SET       {spec.name:<34} {spec.fmt(measured)}{was}")
            if spec.key in dates:
                if spec.direction == DOWN and new[spec.key] == 0:
                    print(
                        f"CLEARED   {spec.name:<34} hard_after={dates.pop(spec.key)} "
                        "(the ceiling reached zero, so the relaxation is over)"
                    )
                else:
                    print(f"RELAXED   {spec.name:<34} hard_after={dates[spec.key]} (kept)")
        write_family(root, family, new, dates)
    return rc


def _is_placeholder_row(line: str) -> bool:
    cells = line.strip().strip("|").split("|")
    return all(not cell.strip() for cell in cells)


def append_ledger_row(path: Path, cells: list[str]) -> None:
    row = "| " + " | ".join(cells) + " |"
    text = path.read_text(encoding="utf-8") if path.is_file() else "# Guards ledger\n"
    lines = text.splitlines()
    try:
        heading = lines.index(LEDGER_HEADING)
    except ValueError:
        if lines and lines[-1].strip():
            lines.append("")
        lines.extend([LEDGER_HEADING, "", LEDGER_HEADER, LEDGER_SEPARATOR, row])
    else:
        end = next(
            (i for i in range(heading + 1, len(lines)) if lines[i].startswith("## ")), len(lines)
        )
        table = [i for i in range(heading + 1, end) if lines[i].lstrip().startswith("|")]
        if len(table) < 2:
            insert_at = heading + 1
            lines[insert_at:insert_at] = ["", LEDGER_HEADER, LEDGER_SEPARATOR, row, ""]
        elif len(table) >= 3 and _is_placeholder_row(lines[table[-1]]):
            lines[table[-1]] = row
        else:
            lines.insert(table[-1] + 1, row)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write("\n".join(lines) + "\n")


@dataclass(frozen=True)
class LoosenRequest:
    name: str
    raw_value: str | None
    reason: str
    hard_after: str | None = None


def parse_loosen_args(tokens: list[str]) -> LoosenRequest:
    """Parse ``KEY=family.key[=value]``, ``REASON=...`` and ``HARD_AFTER=...`` (any order)."""
    assignment = reason = None
    hard_after = None
    for token in tokens:
        head, sep, rest = token.partition("=")
        if not sep:
            fail(f"ratchet: unexpected argument {token!r}")
        if head.upper() == "KEY":
            assignment = rest
        elif head.upper() == "REASON":
            reason = rest
        elif head.upper() == HARD_AFTER.upper():
            hard_after = rest.strip()
        elif "." in head:
            assignment = token
        else:
            fail(f"ratchet: unexpected argument {token!r}")
    if not assignment:
        fail("ratchet: loosen needs KEY=<family>.<key>[=<value>]")
    if reason is None or not reason.strip():
        fail('ratchet: loosen needs REASON="<why>"')
    name, sep, value = assignment.partition("=")
    return LoosenRequest(name.strip(), value.strip() if sep else None, reason.strip(), hard_after)


def _loosen_value(spec: Spec, raw_value: str | None, measured: Number) -> Number:
    try:
        return spec.parse(raw_value) if raw_value is not None else measured
    except ValueError as exc:
        msg = f"ratchet: {spec.name}: cannot parse value {raw_value!r}"
        raise SystemExit(msg) from exc


def _check_loosening(spec: Spec, value: Number, old: Number, measured: Number) -> None:
    """A loosening moves against direction and never past the measurement."""
    if not spec.against(value, old):
        fail(
            f"ratchet: {spec.name}={spec.fmt(value)} is not a loosening of the {spec.bound} "
            f"{spec.fmt(old)}; use make ratchet-bump for tightenings"
        )
    tol = spec.tolerance(value)
    if abs(value - measured) > tol + EPS:
        relation = "looser" if spec.against(value, measured) else "still red"
        fail(
            f"ratchet: {spec.name}={spec.fmt(value)} is {relation} against the measured "
            f"{spec.fmt(measured)} (slack {tol:g}); floors track measurement, so the "
            f"value must be {spec.fmt(measured)} (omit the value to use it)"
        )


def loosen(root: Path, measurement: Measurement, request: LoosenRequest) -> int:
    spec = spec_by_name(request.name)
    if spec is None:
        known = ", ".join(s.name for s in SPECS)
        fail(f"ratchet: unknown key {request.name!r}; known keys: {known}")
    if request.hard_after is not None and parse_date(request.hard_after) is None:
        fail(f"ratchet: HARD_AFTER={request.hard_after!r} is not a YYYY-MM-DD date")
    measured = measurement.values[spec.family][spec.key]
    value = _loosen_value(spec, request.raw_value, measured)

    current = read_family_values(root, spec.family)
    if spec.key not in current:
        fail(f"ratchet: {request.name} has no committed value yet; run make ratchet-bump first")
    old = current[spec.key]
    # A HARD_AFTER on the value the file already holds only stamps an expiry on a relaxation
    # that is already committed; anything that moves the number is a loosening as before.
    stamp_only = request.hard_after is not None and value == old
    if not stamp_only:
        _check_loosening(spec, value, old, measured)

    dates = read_family_dates(root, spec.family)
    if request.hard_after is not None:
        dates[spec.key] = request.hard_after
    current[spec.key] = value
    write_family(root, spec.family, current, dates)
    expiry = f" hard_after={request.hard_after}" if request.hard_after else ""
    safe_reason = " ".join(request.reason.replace("|", "\\|").split()) + expiry
    append_ledger_row(
        root / LEDGER_PATH,
        [dt.date.today().isoformat(), spec.name, spec.fmt(old), spec.fmt(value), safe_reason, ""],
    )
    verb = "STAMPED " if stamp_only else "LOOSENED"
    print(
        f"{verb}  {spec.name:<34} {spec.fmt(old)} -> {spec.fmt(value)}{expiry}; "
        f"row appended to {LEDGER_PATH}"
    )
    return EXIT_OK


# --------------------------------------------------------------------------- approve


@dataclass(frozen=True)
class ApproveRequest:
    name: str
    days: int = APPROVAL_DAYS


def parse_approve_args(tokens: list[str]) -> ApproveRequest:
    """Parse ``KEY=family.key`` and an optional ``DAYS=<n>`` (any order)."""
    name: str | None = None
    days = APPROVAL_DAYS
    for token in tokens:
        head, sep, rest = token.partition("=")
        if not sep:
            fail(f"ratchet: unexpected argument {token!r}")
        if head.upper() == "KEY":
            name = rest.strip()
        elif head.upper() == "DAYS":
            try:
                days = int(rest.strip())
            except ValueError:
                fail(f"ratchet: DAYS={rest.strip()!r} is not a whole number of days")
        elif "." in head and name is None:
            name = token.strip()
        else:
            fail(f"ratchet: unexpected argument {token!r}")
    if not name:
        fail("ratchet: approve needs KEY=<family>.<key>")
    if not 1 <= days <= MAX_APPROVAL_DAYS:
        fail(f"ratchet: DAYS must be between 1 and {MAX_APPROVAL_DAYS}, not {days}")
    return ApproveRequest(name, days)


def typed_at_a_terminal(prompt: str) -> str:
    """Read the confirmation from a person, and refuse when nobody is at the keyboard.

    The whole value of this step is that the agent doing the work cannot also grant the
    permission for it. Nothing here is a security boundary -- a determined process can open a
    pseudo-terminal -- but a pipe on stdin is what an agent's shell actually has, so the
    refusal puts the approval where Wes asked for it: with him (2026-09-18).
    """
    if not sys.stdin.isatty():
        fail(
            "ratchet: approve reads its confirmation from a terminal and stdin is not one. "
            "Run `make ratchet-approve KEY=<key>` yourself in a terminal; an agent cannot "
            "approve its own loosening."
        )
    return input(prompt)


def _pending_move(root: Path, spec: Spec, ref: str) -> tuple[Number, Number]:
    """The move awaiting approval for this key, or a refusal naming why there is none."""
    on_main = main_family_values(root, ref, spec.family)
    here = read_family_values(root, spec.family)
    if on_main is None or spec.key not in on_main:
        fail(f"ratchet: {spec.name} has no committed value on {ref}; nothing to approve against")
    if spec.key not in here:
        fail(f"ratchet: {spec.name} is missing from {RATCHET_DIR}/{spec.family}.txt")
    frm, to = on_main[spec.key], here[spec.key]
    if not spec.against(to, frm):
        fail(
            f"ratchet: {spec.name} is {spec.fmt(to)} here and {spec.fmt(frm)} on {ref}, which is "
            "not a loosening; there is nothing to approve"
        )
    return frm, to


def _approval_summary(
    spec: Spec, frm: Number, to: Number, ref: str, reason: str, expires: dt.date, phrase: str
) -> str:
    return "\n".join(
        [
            "",
            "A loosening on this tree is waiting for your approval.",
            "",
            f"  key       {spec.name} ({spec.bound}, direction {spec.direction})",
            f"  moves     {spec.fmt(frm)} on {ref}  ->  {spec.fmt(to)} here",
            f"  reason    {reason}",
            f"  approval  this move only, until {expires.isoformat()}",
            "",
            "Approving lets `make check` go green on this tree, which is what lets the tree be",
            "merged into main. It does not approve any later move of the same key.",
            "",
            "Type this line exactly to approve, or anything else to cancel:",
            "",
            f"    {phrase}",
            "",
        ]
    )


def approve(root: Path, request: ApproveRequest, confirm: Callable[[str], str]) -> int:
    spec = spec_by_name(request.name)
    if spec is None:
        known = ", ".join(s.name for s in SPECS)
        fail(f"ratchet: unknown key {request.name!r}; known keys: {known}")
    ref = resolve_main_ref(root, None)
    if ref is None:
        fail("ratchet: approve compares against the committed floors; 'none' cannot be approved")
    frm, to = _pending_move(root, spec, ref)
    reason = ledger_reason(root, spec, frm, to)
    if reason is None:
        fail(
            f"ratchet: {LEDGER_PATH.as_posix()} has no Loosenings row for {spec.name} "
            f"{spec.fmt(frm)} -> {spec.fmt(to)}; run make ratchet-loosen "
            f'KEY={spec.name} REASON="<why>" first, so the reason is on the record before '
            "anyone approves it"
        )
    granted = dt.date.today()
    expires = granted + dt.timedelta(days=request.days)
    phrase = f"approve {spec.name} {spec.fmt(frm)} -> {spec.fmt(to)}"
    print(_approval_summary(spec, frm, to, ref, reason, expires, phrase))
    if confirm("> ").strip() != phrase:
        fail("ratchet: approval cancelled; nothing was written")
    path = write_approval(root, spec, Approval(spec.name, frm, to, granted, expires))
    print(
        f"APPROVED  {spec.name:<34} {spec.fmt(frm)} -> {spec.fmt(to)} until "
        f"{expires.isoformat()}; wrote {path.relative_to(root).as_posix()}"
    )
    print("Stage it (git add) before make check, or no green stamp can name the tree.")
    return EXIT_OK


# --------------------------------------------------------------------------- cli


def _print_measurement(measurement: Measurement) -> None:
    for hit in measurement.hits:
        print(f"HIT       {hit}")
    for note in measurement.notes:
        print(f"NOTE      {note}")


def _default_root() -> Path:
    return Path(__file__).resolve().parent.parent


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ratchet.py", description=__doc__.split("\n\n")[0])
    parser.add_argument("--root", type=Path, default=_default_root(), help="repository root")
    parser.add_argument(
        "--coverage-json",
        type=Path,
        default=None,
        help=f"default <root>/{COVERAGE_JSON.as_posix()}",
    )
    parser.add_argument(
        "--code-health-json",
        type=Path,
        default=None,
        help=f"default <root>/{CODE_HEALTH_JSON.as_posix()}",
    )
    parser.add_argument(
        "--doc-policy-json",
        type=Path,
        default=None,
        help=f"default <root>/{DOC_POLICY_JSON.as_posix()}",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    measure_p = sub.add_parser("measure", help="print the measured values as JSON")
    measure_p.add_argument("--write", type=Path, default=None, help="also write the JSON here")
    compare_p = sub.add_parser("compare", help="three-way comparison; exit 0/1/3")
    compare_p.add_argument(
        "--main-ref", default=None, help="git ref with the committed floors, or 'none'"
    )
    sub.add_parser("bump", help="write measured values, never moving against direction")
    loosen_p = sub.add_parser(
        "loosen", help='KEY=<family>.<key>[=<value>] REASON="<why>" [HARD_AFTER=YYYY-MM-DD]'
    )
    loosen_p.add_argument("assignments", nargs="+")
    approve_p = sub.add_parser(
        "approve", help="KEY=<family>.<key> [DAYS=14]; a person types the confirmation"
    )
    approve_p.add_argument("assignments", nargs="+")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root: Path = args.root.resolve()
    # Approving reads the floors and the ledger, never the measurement, so it runs without
    # the analyser reports the other commands depend on: the operator's step is one command.
    if args.command == "approve":
        return approve(root, parse_approve_args(args.assignments), typed_at_a_terminal)
    coverage_json: Path = args.coverage_json or root / COVERAGE_JSON
    code_health_json: Path = args.code_health_json or root / CODE_HEALTH_JSON
    doc_policy_json: Path = args.doc_policy_json or root / DOC_POLICY_JSON
    measurement = measure(root, coverage_json, code_health_json, doc_policy_json)

    if args.command == "measure":
        payload = json.dumps(measurement.to_json(), indent=2, sort_keys=True) + "\n"
        if args.write is not None:
            target: Path = args.write
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(payload, encoding="utf-8")
        sys.stdout.write(payload)
        return EXIT_OK

    _print_measurement(measurement)
    if args.command == "compare":
        findings = compare(root, measurement, resolve_main_ref(root, args.main_ref))
        for finding in findings:
            print(finding.line())
        rc = exit_code(findings)
        counts = {
            s: sum(1 for f in findings if f.status == s)
            for s in ("OK", "RED", "STALE", "LOOSENING", "APPROVED", "RELAXED", "EXPIRED")
        }
        print(
            f"ratchet: {counts['OK']} ok, {counts['RED']} red, {counts['STALE']} stale, "
            f"{counts['LOOSENING']} loosening, {counts['APPROVED']} approved, "
            f"{counts['RELAXED']} relaxed, {counts['EXPIRED']} expired -> exit {rc}"
        )
        return rc
    if args.command == "bump":
        return bump(root, measurement)
    return loosen(root, measurement, parse_loosen_args(args.assignments))


if __name__ == "__main__":
    sys.exit(main())
