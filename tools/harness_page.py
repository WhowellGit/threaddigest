#!/usr/bin/env python3
"""Derive the harness inventory block of ``docs/THREADDIGEST_HARNESS.md`` from the tree.

The earlier project kept a hand-written "how this codebase uses its harness" document. Its
content was among the most valuable in that corpus and it was never opened again after it was
written: it drifted to naming a mechanism deleted weeks earlier, and nobody could tell without
reading the code. The lesson carried here (documentation-practices assessment, 2026-09-13) is
that an inventory of mechanisms is a derived artifact, so this tool renders it from the files
that *are* the mechanisms and a gate (``tests/gates/test_harness_page.py``, G54) goes red when
the committed block and the tree disagree.

What the block lists, and where each line comes from:

- hook scripts under ``tools/hooks/`` with the matcher that registers each one in the Claude
  Code settings and the mode file beside it (a script that exists but is not registered has
  never run; installed-ness of the *git* hooks is machine-local and is printed by ``make check``
  and by ``doctor``, never here);
- pre-commit stages from ``.pre-commit-config.yaml``;
- gate files under ``tests/gates/`` and the ledger's row counts in ``docs/runbook/GUARDS.md``;
- ratchet files under ``.ratchets/`` with their keys (values stay in the files: one number home);
- import-linter contracts, path-scoped rule files with their globs, skills, tools, ``make``
  targets;
- the machine-read registers and which gate files read each one.

Usage: ``uv run python tools/harness_page.py --check`` (exit 1 with a diff when the block is
stale) or ``--write`` (replace the block in place). Stdlib only; reads the tree, writes only
the page.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PAGE = Path("docs") / "THREADDIGEST_HARNESS.md"
BEGIN = "<!-- harness-inventory:begin -->"
END = "<!-- harness-inventory:end -->"

REGISTERS: tuple[str, ...] = (
    "docs/runbook/KNOWN_ISSUES.md",
    "docs/runbook/GUARDS.md",
    "docs/reference/reviews/REGISTER.md",
    "docs/reference/reviews/templates/claims.md",
    "docs/TEST_STRATEGY.md",
    "docs/decisions/DECISIONS.md",
    "docs/recent/STATUS.md",
    "docs/INDEX.md",
)

_PRECOMMIT_ID = re.compile(r"^\s*-\s*id:\s*(\S+)")
_PRECOMMIT_STAGE = re.compile(r"^\s*stages:\s*\[([^\]]*)\]")
_CONTRACT_NAME = re.compile(r"^name\s*=\s*(.+?)\s*$")
_MAKE_TARGET = re.compile(r"^([a-z][a-z0-9_-]*):")
_RULE_GLOB = re.compile(r'^\s*-\s*"([^"]+)"')
_TABLE_SEPARATOR = re.compile(r"^\|\s*:?-")


def _read(root: Path, rel: str) -> str:
    path = root / rel
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def hook_lines(root: Path) -> list[str]:
    """One line per hook script: the matcher registering it and its mode file, if any."""
    matchers: dict[str, list[str]] = {}
    try:
        settings = json.loads(_read(root, ".claude/settings.json") or "{}")
        for event, entries in settings.get("hooks", {}).items():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    name = str(hook.get("command", "")).rsplit("/", 1)[-1]
                    matchers.setdefault(name, []).append(f"{event} `{entry.get('matcher', '*')}`")
    except (ValueError, AttributeError, TypeError):
        matchers = {}
    lines = []
    for script in sorted((root / "tools" / "hooks").glob("*.sh")):
        where = "; ".join(matchers.get(script.name, [])) or "NOT REGISTERED (a human adds it)"
        mode_file = script.with_suffix(".mode")
        mode = (
            f"; mode `{mode_file.read_text(encoding='utf-8').strip()}`"
            if mode_file.is_file()
            else ""
        )
        lines.append(f"- `tools/hooks/{script.name}`: {where}{mode}")
    return lines


def precommit_lines(root: Path) -> list[str]:
    """Hook ids from the pre-commit configuration, with a non-default stage when declared."""
    lines = []
    current: str | None = None
    for raw in _read(root, ".pre-commit-config.yaml").splitlines():
        if m := _PRECOMMIT_ID.match(raw):
            current = m.group(1)
            lines.append(f"`{current}`")
        elif current and (m := _PRECOMMIT_STAGE.match(raw)):
            lines[-1] = f"`{current}` (stage {m.group(1).strip()})"
    return lines


def ledger_counts(root: Path) -> dict[str, int]:
    """Body-row counts per table-bearing section of the guards ledger, by section heading.

    A table's header row is the line before its separator, so the count is every ``|`` line
    minus two per separator; a placeholder row whose cells are all blank is not a row."""
    counts: dict[str, int] = {}
    section = ""
    for raw in _read(root, "docs/runbook/GUARDS.md").splitlines():
        if raw.startswith("## "):
            section = raw[3:].split("(", 1)[0].strip()
        elif section and _TABLE_SEPARATOR.match(raw):
            counts[section] = counts.get(section, 0) - 1  # the header row counted just before
        elif section and raw.startswith("|") and raw.strip("| \t"):
            counts[section] = counts.get(section, 0) + 1
    return counts


def ratchet_lines(root: Path) -> list[str]:
    lines = []
    for path in sorted((root / ".ratchets").glob("*.txt")):
        keys = []
        for raw in path.read_text(encoding="utf-8").splitlines():
            key = raw.split("=", 1)[0].strip()
            if key and not key.startswith("#") and not key.endswith(".hard_after"):
                keys.append(f"`{key}`")
        lines.append(f"- `.ratchets/{path.name}`: {', '.join(keys) or '(empty)'}")
    return lines


def rule_lines(root: Path) -> list[str]:
    lines = []
    for path in sorted((root / ".claude" / "rules").glob("*.md")):
        globs = []
        in_paths = False
        for raw in path.read_text(encoding="utf-8").splitlines():
            if raw.startswith("paths:"):
                in_paths = True
            elif in_paths and (m := _RULE_GLOB.match(raw)):
                globs.append(f"`{m.group(1)}`")
            elif in_paths and not raw.startswith((" ", "-")):
                break
        lines.append(f"- `.claude/rules/{path.name}`: {', '.join(globs) or '(no paths)'}")
    return lines


def register_lines(root: Path) -> list[str]:
    """For each machine-read register, the gate files whose text names it."""
    gates = {
        p.name: p.read_text(encoding="utf-8")
        for p in sorted((root / "tests" / "gates").glob("test_*.py"))
    }
    lines = []
    for rel in REGISTERS:
        if not (root / rel).is_file():
            continue
        base = rel.rsplit("/", 1)[-1]
        readers = [f"`{name}`" for name, text in gates.items() if base in text]
        lines.append(
            f"- `{rel}`: read by {', '.join(readers) if readers else 'no gate (review only)'}"
        )
    return lines


def _names(root: Path, pattern: str, strip: str = "") -> list[str]:
    return [
        f"`{p.name.removesuffix(strip)}`"
        for p in sorted(root.glob(pattern))
        if p.name != "__pycache__"
    ]


def render(root: Path = ROOT) -> str:
    """The generated block, markers included, ending with a newline."""
    counts = ledger_counts(root)
    contracts = [
        f"`{m.group(1)}`"
        for raw in _read(root, ".importlinter").splitlines()
        if (m := _CONTRACT_NAME.match(raw))
    ]
    targets = [
        f"`{m.group(1)}`"
        for raw in _read(root, "Makefile").splitlines()
        if (m := _MAKE_TARGET.match(raw))
    ]
    gate_files = _names(root, "tests/gates/test_*.py", ".py")
    skills = [
        f"`{p.parent.name}`" for p in sorted((root / ".claude" / "skills").glob("*/SKILL.md"))
    ]
    ledger = ", ".join(f"{name} {n}" for name, n in counts.items()) or "no ledger"
    parts = [
        BEGIN,
        "",
        "_Generated by `tools/harness_page.py` from the tree; gate G54 fails when this block "
        "and the tree disagree. Regenerate with `uv run python tools/harness_page.py --write`. "
        "Installed-ness of the git hooks is machine-local and is printed by `make check` and "
        "`doctor`, never here._",
        "",
        "**Hook scripts and their registration** (`.claude/settings.json`):",
        *hook_lines(root),
        "",
        "**Pre-commit stages** (`.pre-commit-config.yaml`): " + ", ".join(precommit_lines(root)),
        "",
        f"**Gate files** (`tests/gates/`, {len(gate_files)}): " + ", ".join(gate_files),
        "",
        f"**Guards ledger rows** (`docs/runbook/GUARDS.md`): {ledger}",
        "",
        "**Ratchet files and keys** (`.ratchets/`; values live in the files):",
        *ratchet_lines(root),
        "",
        "**Import-linter contracts** (`.importlinter`): " + ", ".join(contracts),
        "",
        "**Path-scoped rule files** (`.claude/rules/`):",
        *rule_lines(root),
        "",
        "**Skills** (`.claude/skills/`): " + (", ".join(skills) or "none"),
        "",
        "**Tools** (`tools/*.py`): " + ", ".join(_names(root, "tools/*.py")),
        "",
        "**`make` targets**: " + ", ".join(targets),
        "",
        "**Machine-read registers and their readers**:",
        *register_lines(root),
        "",
        END,
    ]
    return "\n".join(parts) + "\n"


def split_page(text: str) -> tuple[str, str, str] | None:
    """``(before, block, after)`` around the markers, or ``None`` when a marker is missing."""
    start = text.find(BEGIN)
    stop = text.find(END)
    if start < 0 or stop < 0 or stop < start:
        return None
    stop += len(END)
    return text[:start], text[start:stop] + "\n", text[stop:].lstrip("\n")


def problems(root: Path = ROOT) -> list[str]:
    """Why the committed page disagrees with the tree; empty when it is current."""
    page = root / PAGE
    if not page.is_file():
        return [f"{PAGE} is missing"]
    parts = split_page(page.read_text(encoding="utf-8"))
    if parts is None:
        return [f"{PAGE} has no {BEGIN} … {END} markers"]
    expected = render(root)
    if parts[1] == expected:
        return []
    diff = difflib.unified_diff(
        parts[1].splitlines(), expected.splitlines(), "committed", "tree", lineterm="", n=1
    )
    return [f"{PAGE} inventory block is stale:", *diff]


def write(root: Path = ROOT) -> None:
    page = root / PAGE
    parts = split_page(page.read_text(encoding="utf-8"))
    if parts is None:
        msg = f"{PAGE} has no markers to replace"
        raise SystemExit(msg)
    page.write_text(
        parts[0] + render(root) + ("\n" + parts[2] if parts[2] else ""), encoding="utf-8"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true", help="exit 1 if the block is stale")
    mode.add_argument("--write", action="store_true", help="regenerate the block in place")
    mode.add_argument("--print", action="store_true", help="print the block")
    args = parser.parse_args(argv)
    if args.print:
        sys.stdout.write(render(args.root))
        return 0
    if args.write:
        write(args.root)
        print(f"{PAGE}: inventory block regenerated")
        return 0
    found = problems(args.root)
    print("\n".join(found) if found else f"{PAGE}: inventory block matches the tree")
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
