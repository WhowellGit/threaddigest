#!/usr/bin/env python3
"""Measure code health for the ``code_health`` ratchet family; ``make check`` runs it first.

Wes's rule (2026-09-14, ``docs/decisions/DECISIONS.md`` § 2026-09-14 (later)): at a milestone,
functional correctness, test correctness, and maintainability pass independently, the third
judged by deterministic analysis and never by asking a model whether the code is clean. This
script is that analysis. It runs the installed analyzers over the tree, counts the offenders
each one reports against a fixed threshold, and writes one JSON report that ``tools/ratchet.py``
reads the way it reads the coverage report; the ratchet then holds each count as a ceiling
that only goes down, and a relaxation at birth carries a ``hard_after`` date.

Counts (every one a ceiling; every offender printed with its location, so a count is never a
bare number):

    cognitive_over_15       functions whose cognitive complexity (complexipy) is above 15
    cyclomatic_over_15      functions whose cyclomatic complexity (radon cc) is above 15
    mi_below_a              modules whose maintainability index (radon mi) is below rank A
    size_rule_violations    ruff PLR0911/PLR0912/PLR0913/PLR1702 (returns, branches,
                            arguments, nesting), measured here rather than enforced as lint
                            because the existing offenders are held by this ceiling
    dead_code               vulture findings of kind function, method, class or property at
                            60% confidence or more, scanned over src, tests and tools so that
                            use from a test counts as use, with decorator-registered names
                            ignored and the rest matched against tools/vulture_whitelist.py
    dead_code_whitelisted   entries in that whitelist, so the list itself cannot grow unseen
    duplicate_blocks        pylint duplicate-code findings (eight similar lines or more), each
                            named by every module the block sits in rather than by the module
                            pylint happened to finish its run on

A missing analyzer or a failed run exits non-zero and writes no report, so the ratchet turns
red rather than reading zero: fail, never skip. Standard library only; the analyzers are
console scripts installed beside the interpreter (``uv sync --all-groups``).

Usage: uv run python tools/code_health.py [--root DIR] [--write PATH] [--bin-dir DIR]
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

COGNITIVE_LIMIT = 15
CYCLOMATIC_LIMIT = 15
MI_TOP_RANK = "A"
SIZE_RULES = ("PLR0911", "PLR0912", "PLR0913", "PLR1702")
DUPLICATE_MIN_LINES = 8
DEAD_CODE_MIN_CONFIDENCE = 60
DEAD_CODE_KINDS = frozenset({"function", "method", "class", "property"})
#: Names registered by a decorator are reached without a direct call, so vulture cannot see
#: their use: command handlers, validators, event listeners, fixtures.
DEAD_CODE_IGNORED_DECORATORS = (
    "@*.command",
    "@*.callback",
    "@field_validator",
    "@model_validator",
    "@event.listens_for",
    "@*.fixture",
    "@pytest.fixture",
)
SOURCE = Path("src") / "threaddigest"
DEAD_CODE_PATHS = ("src", "tests", "tools")
WHITELIST = Path("tools") / "vulture_whitelist.py"
REPORT = Path(".build") / "code_health.json"
TIMEOUT = 300

VULTURE_LINE = re.compile(r"^(?P<where>.+?:\d+): unused (?P<kind>\w+) '(?P<name>[^']+)'")
#: pylint emits duplicate-code from its closing pass, with no node to attach it to, so the row's
#: ``path`` is whichever module the run happened to finish on -- a different file on a different
#: filesystem, and often not one of the duplicated modules at all. The modules that actually hold
#: the block are in the message body, one ``==<dotted module>:[start:end]`` line each.
DUPLICATE_SITE = re.compile(r"^==(?P<module>[\w.]+):\[(?P<start>\d+):\d+\]$", re.MULTILINE)
#: One whitelist entry: a dotted name inside the WHITELISTED tuple, one per line, with a reason.
WHITELIST_ENTRY = re.compile(r"^\s*(?P<name>[\w.]+)\s*,\s*(#.*)?$")


def fail(message: str) -> NoReturn:
    msg = f"code_health: {message}"
    raise SystemExit(msg)


@dataclass
class Report:
    values: dict[str, int] = field(default_factory=dict)
    hits: list[str] = field(default_factory=list)

    def record(self, key: str, hits: list[str], count: int | None = None) -> None:
        self.values[key] = len(hits) if count is None else count
        self.hits.extend(f"{key} {hit}" for hit in hits)


class Analyzers:
    """The console scripts this measurement runs, resolved once, all required."""

    NAMES = ("complexipy", "radon", "ruff", "vulture", "pylint")

    def __init__(self, root: Path, bin_dir: Path) -> None:
        self.root = root
        self.paths: dict[str, Path] = {}
        for name in self.NAMES:
            candidate = bin_dir / name
            found = candidate if candidate.is_file() else shutil.which(name)
            if found is None:
                fail(f"analyzer {name!r} not found in {bin_dir} or on PATH; uv sync --all-groups")
            self.paths[name] = Path(found)

    def run(self, name: str, *args: str) -> subprocess.CompletedProcess[str]:
        try:
            return subprocess.run(
                [str(self.paths[name]), *args],
                cwd=self.root,
                capture_output=True,
                text=True,
                check=False,
                timeout=TIMEOUT,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            fail(f"{name} could not run: {exc}")

    def run_json(self, name: str, *args: str) -> object:
        proc = self.run(name, *args)
        try:
            return json.loads(proc.stdout)
        except ValueError:
            fail(f"{name} produced no JSON (exit {proc.returncode}): {proc.stderr.strip()[:300]}")


def rel(root: Path, raw: str) -> str:
    path = Path(raw)
    if path.is_absolute():
        try:
            path = path.relative_to(root)
        except ValueError:
            return raw
    return path.as_posix()


# --------------------------------------------------------------------------- measurements


def cognitive(tools: Analyzers, source: Path) -> list[str]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "complexipy.json"
        proc = tools.run(
            "complexipy",
            str(source),
            "--max-complexity-allowed",
            str(COGNITIVE_LIMIT),
            "--output-format",
            "json",
            "--output",
            str(out),
            "--quiet",
            "--ignore-complexity",
        )
        if not out.is_file():
            fail(
                f"complexipy wrote no report (exit {proc.returncode}): {proc.stderr.strip()[:300]}"
            )
        rows = json.loads(out.read_text(encoding="utf-8"))
    hits = []
    for row in rows:
        score = int(row.get("complexity", 0))
        if score > COGNITIVE_LIMIT:
            hits.append(f"{rel(tools.root, row['path'])} {row['function_name']} cognitive {score}")
    return sorted(hits)


def cyclomatic(tools: Analyzers, source: Path) -> list[str]:
    data = tools.run_json("radon", "cc", "-j", str(source))
    if not isinstance(data, dict):
        fail("radon cc returned an unexpected shape")
    hits = []
    for file, blocks in data.items():
        if not isinstance(blocks, list):
            fail(f"radon cc failed on {file}: {blocks}")
        for block in blocks:
            if block.get("type") == "class":
                continue  # its methods are listed as blocks of their own
            score = int(block["complexity"])
            if score > CYCLOMATIC_LIMIT:
                owner = f"{block['classname']}." if block.get("classname") else ""
                where = f"{rel(tools.root, file)}:{block['lineno']}"
                hits.append(f"{where} {owner}{block['name']} cyclomatic {score}")
    return sorted(hits)


def maintainability(tools: Analyzers, source: Path) -> list[str]:
    data = tools.run_json("radon", "mi", "-j", str(source))
    if not isinstance(data, dict):
        fail("radon mi returned an unexpected shape")
    hits = []
    for file, entry in data.items():
        if not isinstance(entry, dict) or "rank" not in entry:
            fail(f"radon mi failed on {file}: {entry}")
        if entry["rank"] != MI_TOP_RANK:
            hits.append(
                f"{rel(tools.root, file)} maintainability {entry['mi']:.1f} rank {entry['rank']}"
            )
    return sorted(hits)


def size_rules(tools: Analyzers, source: Path) -> list[str]:
    data = tools.run_json(
        "ruff",
        "check",
        "--select",
        ",".join(SIZE_RULES),
        "--preview",
        "--output-format",
        "json",
        "--exit-zero",
        str(source),
    )
    if not isinstance(data, list):
        fail("ruff returned an unexpected shape")
    return sorted(
        f"{rel(tools.root, row['filename'])}:{row['location']['row']} "
        f"{row['code']} {row['message']}"
        for row in data
    )


def whitelist_entries(root: Path) -> list[str]:
    path = root / WHITELIST
    if not path.is_file():
        return []
    entries = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        match = WHITELIST_ENTRY.match(line)
        if match:
            entries.append(f"{WHITELIST.as_posix()}:{number} {match.group('name')}")
    return entries


def dead_code(tools: Analyzers) -> list[str]:
    paths = [p for p in DEAD_CODE_PATHS if (tools.root / p).is_dir()]
    if (tools.root / WHITELIST).is_file():
        paths.append(WHITELIST.as_posix())
    proc = tools.run(
        "vulture",
        *paths,
        "--min-confidence",
        str(DEAD_CODE_MIN_CONFIDENCE),
        "--ignore-decorators",
        ",".join(DEAD_CODE_IGNORED_DECORATORS),
    )
    if proc.returncode not in (0, 3):  # 3 means findings; anything else is a failed run
        fail(f"vulture failed (exit {proc.returncode}): {proc.stderr.strip()[:300]}")
    hits = []
    for line in proc.stdout.splitlines():
        match = VULTURE_LINE.match(line.strip())
        if match and match.group("kind") in DEAD_CODE_KINDS:
            hits.append(
                f"{match.group('where')} unused {match.group('kind')} {match.group('name')}"
            )
    return sorted(hits)


def module_file(root: Path, source: Path, module: str) -> str:
    """``pkg.a.b`` → the file that defines it, relative to ``root``; the dotted name if unknown."""
    base = source.parent.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return rel(root, str(candidate))
    return module


def duplicate_sites(root: Path, source: Path, row: dict[str, object]) -> str:
    """Every module the duplicated block sits in, sorted, so the hit is the same on every host.

    pylint's own ``path`` for a duplicate-code row names the last module the run linted, which
    follows directory-read order and so differs between filesystems; it is kept only as the
    fallback for a message this parser does not recognise.
    """
    message = row.get("message")
    sites = sorted(
        f"{module_file(root, source, m.group('module'))}:{m.group('start')}"
        for m in DUPLICATE_SITE.finditer(message if isinstance(message, str) else "")
    )
    return " ".join(sites) or f"{rel(root, str(row['path']))}:{row['line']}"


def duplicates(tools: Analyzers, source: Path) -> list[str]:
    data = tools.run_json(
        "pylint",
        "--disable=all",
        "--enable=duplicate-code",
        f"--min-similarity-lines={DUPLICATE_MIN_LINES}",
        "--output-format=json",
        "--score=n",
        str(source),
    )
    if not isinstance(data, list):
        fail("pylint returned an unexpected shape")
    return sorted(
        f"{duplicate_sites(tools.root, source, row)} duplicate-code"
        for row in data
        if row.get("symbol") == "duplicate-code"
    )


def measure(root: Path, bin_dir: Path) -> Report:
    tools = Analyzers(root, bin_dir)
    source = root / SOURCE
    if not source.is_dir():
        fail(f"source tree {SOURCE} not found under {root}")
    report = Report()
    report.record("cognitive_over_15", cognitive(tools, source))
    report.record("cyclomatic_over_15", cyclomatic(tools, source))
    report.record("mi_below_a", maintainability(tools, source))
    report.record("size_rule_violations", size_rules(tools, source))
    report.record("dead_code", dead_code(tools))
    report.record("dead_code_whitelisted", whitelist_entries(root))
    report.record("duplicate_blocks", duplicates(tools, source))
    return report


# --------------------------------------------------------------------------- cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="code_health.py", description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent.parent, help="repository root"
    )
    parser.add_argument(
        "--write", type=Path, default=None, help=f"report path; default <root>/{REPORT.as_posix()}"
    )
    parser.add_argument(
        "--bin-dir",
        type=Path,
        default=Path(sys.executable).parent,
        help="where the analyzer console scripts live (default: beside the interpreter)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root: Path = args.root.resolve()
    report = measure(root, args.bin_dir.resolve())
    target: Path = args.write or root / REPORT
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {"values": report.values, "hits": report.hits}
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    for hit in report.hits:
        print(f"HIT       {hit}")
    for key, value in report.values.items():
        print(f"code_health.{key:<24} {value}")
    print(f"code_health: report written to {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
