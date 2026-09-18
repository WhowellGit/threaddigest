#!/usr/bin/env python3
"""Renumber a known-issue id across every citation in the tracked tree, in one pass.

Birth incident (2026-09-17, ``docs/reference/reviews/2026-09-17-renumber-sweep-incident.md``):
two agents working in separate git worktrees each appended a ``docs/runbook/KNOWN_ISSUES.md``
row and each claimed the same next-free id, because neither could see the other's uncommitted
tree. The main session renumbered one by hand, moved the two citations a gate had named, and
left three others pointing a reader at the wrong incident. The remedy the incident record names
is this tool: a renumber is a mirrors sweep over the whole tracked tree, never a hand edit that
stops where a gate stopped.

What it does. ``OLD`` and ``NEW`` are ids in the sheet's own form (``KI-041``). The id is matched
as a whole token -- ``KI-04`` never matches inside ``KI-041``, and a longer id such as ``KI-0410``
is never truncated into a match -- wherever it appears: prose, a table cell, a docstring, a
comment, a string a test's own name is built from. A real run rewrites every match in every
tracked text file the shared file set yields (``tools.private_terms.scannable`` and
``tracked_files``, the same file set the identifier gate reads, reused rather than redefined),
with one exception: a reference record under ``docs/reference/reviews/`` is never rewritten,
because a reference record is never edited after it lands. ``--dry-run`` prints what would change
and writes nothing.

Refusals (exit 1, a reason printed): ``OLD`` has no row in ``KNOWN_ISSUES.md``; ``NEW`` already
has a row; either id is malformed; or -- on a real run only, since a dry run writes nothing --
a file the rename would touch already has uncommitted changes, so a half-finished edit is never
swept into the rename.

Usage, as a module so ``tools.private_terms`` and ``tools.ratchet`` resolve (a tool cannot run as
a bare script the way ``tools/private_terms.py`` explains for the same reason)::

    uv run python -m tools.renumber_known_issue KI-041 KI-099 [--root PATH] [--dry-run]

Not run by ``make check``: this is a command an operator runs, not a gate. Stdlib only.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

from tools.private_terms import scannable, tracked_files
from tools.ratchet import is_separator_row, split_row

ROOT = Path(__file__).resolve().parents[1]

#: The sheet's own id form: ``KI-`` followed by one or more digits.
ID_RE = re.compile(r"^KI-\d+$")

#: A reference record is never rewritten; this is its home.
REFERENCE_PREFIX = "docs/reference/reviews/"

KNOWN_ISSUES_REL = "docs/runbook/KNOWN_ISSUES.md"

_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)


class RefusalError(Exception):
    """A validated refusal (exit 1) -- distinct from an argparse usage error (exit 2)."""


# --------------------------------------------------------------------------- matching


def token_pattern(id_: str) -> re.Pattern[str]:
    """``id_`` matched only as a whole token: neither a shorter id already in the tree (a
    prefix) nor a longer one (a suffix of extra digits or letters) may be swept in."""
    return re.compile(rf"(?<![A-Za-z0-9]){re.escape(id_)}(?![A-Za-z0-9])")


def line_matches(text: str, pattern: re.Pattern[str]) -> list[tuple[int, str]]:
    """``(1-based line number, that line's text)`` once per match on that line."""
    out: list[tuple[int, str]] = []
    for number, line in enumerate(text.splitlines(), start=1):
        out += [(number, line) for _ in pattern.finditer(line)]
    return out


# --------------------------------------------------------------------------- the row sheet


def _strip_html_comments(text: str) -> str:
    """Drop HTML comments (the format example in ``KNOWN_ISSUES.md`` lives in one), keeping
    their newlines so nothing downstream misreads a comment as a row."""
    return _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def known_issue_row_ids(root: Path) -> set[str]:
    """Every id that heads a real row of ``KNOWN_ISSUES.md`` (not the header, a separator, or
    the commented-out format example)."""
    text = (root / KNOWN_ISSUES_REL).read_text(encoding="utf-8")
    ids: set[str] = set()
    for line in _strip_html_comments(text).splitlines():
        cells = split_row(line)
        if not cells or is_separator_row(cells):
            continue
        if ID_RE.fullmatch(cells[0]):
            ids.add(cells[0])
    return ids


# --------------------------------------------------------------------------- the file set


def collect_files(root: Path) -> tuple[list[str], list[str]]:
    """``(rewritable paths, reference-record paths)`` from the shared scannable file set."""
    candidates = scannable(tracked_files(root))
    rewrite = [p for p in candidates if not p.startswith(REFERENCE_PREFIX)]
    reference = [p for p in candidates if p.startswith(REFERENCE_PREFIX)]
    return rewrite, reference


def build_touched(root: Path, paths: list[str], pattern: re.Pattern[str]) -> dict[str, str]:
    """``{path: original text}`` for every path in ``paths`` that carries at least one match."""
    touched: dict[str, str] = {}
    for rel in paths:
        text = (root / rel).read_text(encoding="utf-8")
        if pattern.search(text):
            touched[rel] = text
    return touched


def reference_report(
    root: Path, paths: list[str], pattern: re.Pattern[str]
) -> tuple[int, list[str]]:
    """Total remaining citation count and the sorted files that carry one, under the
    reference-record prefix -- reported, never rewritten."""
    count = 0
    files: list[str] = []
    for rel in paths:
        text = (root / rel).read_text(encoding="utf-8")
        hits = len(pattern.findall(text))
        if hits:
            count += hits
            files.append(rel)
    return count, sorted(files)


# --------------------------------------------------------------------------- git state


def dirty_files(root: Path) -> set[str]:
    """Repo-relative paths with a staged, unstaged, or untracked change."""
    out = subprocess.run(
        ["git", "-C", str(root), "status", "--porcelain", "--untracked-files=all"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout
    paths: set[str] = set()
    for line in out.splitlines():
        if len(line) < 4:
            continue
        rest = line[3:]
        if " -> " in rest:
            _, _, rest = rest.partition(" -> ")
        paths.add(rest.strip().strip('"'))
    return paths


# --------------------------------------------------------------------------- validation


def validate_ids(old: str, new: str) -> None:
    for label, value in (("OLD", old), ("NEW", new)):
        if not ID_RE.fullmatch(value):
            msg = f"{label} {value!r} is not a well-formed id (expected KI-<digits>)"
            raise RefusalError(msg)


def check_rows(root: Path, old: str, new: str) -> None:
    ids = known_issue_row_ids(root)
    if old not in ids:
        msg = f"{old} has no row in {KNOWN_ISSUES_REL}"
        raise RefusalError(msg)
    if new in ids:
        msg = f"{new} already has a row in {KNOWN_ISSUES_REL}"
        raise RefusalError(msg)


def refuse_if_dirty(root: Path, touched: dict[str, str]) -> None:
    blocked = sorted(dirty_files(root) & touched.keys())
    if blocked:
        msg = (
            "uncommitted changes would be swept into the rename: "
            + ", ".join(blocked)
            + " (commit or stash first, or pass --dry-run)"
        )
        raise RefusalError(msg)


# --------------------------------------------------------------------------- reporting and writing


def print_dry_run(old: str, new: str, touched: dict[str, str], pattern: re.Pattern[str]) -> None:
    total = 0
    for rel in sorted(touched):
        for number, line in line_matches(touched[rel], pattern):
            print(f"renumber: {rel}:{number}: {line.strip()}")
            total += 1
    print(
        f"renumber: dry run; {len(touched)} file(s), {total} citation(s) of {old} would "
        f"become {new}; nothing written"
    )


def apply_changes(root: Path, touched: dict[str, str], pattern: re.Pattern[str], new: str) -> None:
    for rel, text in touched.items():
        (root / rel).write_text(pattern.sub(new, text), encoding="utf-8")


def print_summary(
    old: str,
    new: str,
    touched: dict[str, str],
    pattern: re.Pattern[str],
    reference_count: int,
    reference_files: list[str],
) -> None:
    total = sum(len(line_matches(text, pattern)) for text in touched.values())
    print(f"renumber: {old} -> {new}")
    print(f"renumber: {len(touched)} file(s) changed, {total} citation(s) rewritten")
    print(
        f"renumber: {reference_count} citation(s) of {old} left in {REFERENCE_PREFIX} "
        "(reference records are never rewritten)"
    )
    for rel in reference_files:
        print(f"renumber: left: {rel}")
    print(
        f"renumber: the row's own id in {KNOWN_ISSUES_REL} moved with the rest of the sweep "
        "(it is part of the tracked set this tool rewrites)"
    )


# --------------------------------------------------------------------------- orchestration


def run(root: Path, old: str, new: str, *, dry_run: bool) -> None:
    validate_ids(old, new)
    check_rows(root, old, new)
    pattern = token_pattern(old)
    rewrite_paths, reference_paths = collect_files(root)
    touched = build_touched(root, rewrite_paths, pattern)
    if dry_run:
        print_dry_run(old, new, touched, pattern)
        return
    refuse_if_dirty(root, touched)
    apply_changes(root, touched, pattern, new)
    reference_count, reference_files = reference_report(root, reference_paths, pattern)
    print_summary(old, new, touched, pattern, reference_count, reference_files)


# --------------------------------------------------------------------------- cli


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="renumber_known_issue",
        description="Renumber a known-issue id across every citation in the tracked tree.",
    )
    parser.add_argument("old", metavar="OLD", help="the existing id, e.g. KI-041")
    parser.add_argument("new", metavar="NEW", help="the id to rename it to, e.g. KI-099")
    parser.add_argument(
        "--root", default=str(ROOT), help="repository root (default: this checkout)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="print what would change; write nothing"
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(str(args.root)).resolve()
    try:
        run(root, str(args.old), str(args.new), dry_run=bool(args.dry_run))
    except RefusalError as exc:
        print(f"renumber: refused: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
