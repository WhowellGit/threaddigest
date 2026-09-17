#!/usr/bin/env python3
"""Check tracked text against the operator's private term list (the G35 widening).

Birth incident (2026-09-17): a term on the operator's private list was found in tracked text;
nothing mechanical had been checking for it.

The rule behind it is the operator's standing one: sensitive material must never reach the
repository, and where a repository can check that mechanically it builds the check. The fixed
classes -- addresses, home paths, ticket keys, attribution strings -- are the identifier gate's
own rules in ``tests/gates/test_no_imported_identifiers.py``. This file is the half that cannot
be written down here: the terms are the operator's, the repository is public, and a public
repository listing what it must not say would be the leak it exists to prevent. So the list
lives in the private folder beside the memory snapshot (``$THREADDIGEST_PRIVATE_DIR``, resolved
by ``tools.memory_snapshot.private_home`` so there is one home and one default), nothing here
and nothing this tool prints ever carries a term, and a finding names the pattern that matched
by its ordinal in the list.

Two files, both in that folder:

``tracked-text-terms.txt``
    One case-sensitive Python regular expression per line. Blank lines and lines beginning with
    ``#`` are ignored. Case-sensitive because the operator writes the pattern, and a pattern
    that should be case-insensitive says so in its own syntax (``(?i)``).
``tracked-text-terms-accepted.txt``
    One accepted existing occurrence per line, ``path<TAB>sha1hex``, where the hash is of the
    offending line stripped of surrounding whitespace and the path is the repository-relative
    one ``git ls-files`` prints. Content-hashed rather than ``path:line``: a line that moves
    within its file keeps its acceptance, and a line that is edited is flagged again, which is
    the behaviour an acceptance list needs to stay honest as the document around it changes.

A missing list is not a failure: CI and a fresh clone have no private folder, so ``check``
prints one verbatim note saying nothing was checked and exits 0 -- a visible state rather than
a silent skip. A list that exists and cannot be read, or that holds a pattern that does not
compile, is red: a check that cannot run is never quietly green.

The file set is defined here rather than in the gate because two readers need it -- this tool
under ``make check`` and the gate under pytest -- and a tool cannot import a test module. The
gate imports :func:`scannable` and :func:`tracked_files` from here.

Usage, as a module so that the repository root is on the path (this tool imports
``tools.memory_snapshot`` for the one definition of the private folder, which a script run
from ``tools/`` cannot see)::

    uv run python -m tools.private_terms check            # exit 1 on any unaccepted hit
    uv run python -m tools.private_terms accept path:line  # accept one existing occurrence

``make check`` runs the first of those. Stdlib only. Writes nothing anywhere except the
accepted file in the private folder, and never creates that folder
(``tools/memory_snapshot.py`` explains why a missing home is reported rather than made).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import NoReturn

from tools.memory_snapshot import private_home

ROOT = Path(__file__).resolve().parents[1]

#: The tracked files this scan and the identifier gate read: text by extension, with the
#: earlier project's own redacted documents excluded (they are kept deliberately, under their
#: own redaction note).
TEXT_SUFFIXES = frozenset(
    {".md", ".py", ".toml", ".yaml", ".yml", ".txt", ".json", ".cfg", ".ini", ".sh", ".mako"}
)
EXCLUDED_PREFIXES = ("docs/reference/earlier-project-retrospectives/",)

LIST_NAME = "tracked-text-terms.txt"
ACCEPTED_NAME = "tracked-text-terms-accepted.txt"

#: Printed verbatim when the private folder holds no list (CI, a fresh clone, another machine).
#: A real state, not a skip: it is visible in the ``make check`` output and the run exits 0.
NO_LIST = "private terms: no list at {path}; nothing checked"


def fail(message: str) -> NoReturn:
    msg = f"private terms: {message}"
    raise SystemExit(msg)


# --------------------------------------------------------------------------- the file set


def scannable(rel_paths: Iterable[str]) -> list[str]:
    """The subset of ``rel_paths`` that is scanned: text suffixes, retrospectives excluded."""
    return sorted(
        rel
        for rel in rel_paths
        if Path(rel).suffix in TEXT_SUFFIXES and not rel.startswith(EXCLUDED_PREFIXES)
    )


def tracked_files(root: Path) -> list[str]:
    """Tracked files plus untracked files git would not ignore.

    A new file is invisible to ``git ls-files`` until it is added, so a scan of tracked files
    alone lets a violation ride into the first commit that adds it (this happened on
    2026-09-14: a review record carrying a foreign register id passed the gate untracked and
    failed it once committed). Untracked-but-not-ignored files are therefore scanned too.
    """
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--cached", "--others", "--exclude-standard"],
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    ).stdout
    return out.split()


# --------------------------------------------------------------------------- the private files


def list_path(home: Path) -> Path:
    return home / LIST_NAME


def accepted_path(home: Path) -> Path:
    return home / ACCEPTED_NAME


def line_hash(line: str) -> str:
    """The identity of one offending line: its stripped text, hashed.

    Not a secret-keeping device -- it is a short, stable name for a line the accepted file must
    not spell out, in a file that sits beside the list itself.
    """
    return hashlib.sha1(line.strip().encode("utf-8")).hexdigest()


def load_patterns(home: Path) -> list[re.Pattern[str]] | None:
    """The compiled list, or ``None`` when there is no list file. Unreadable is red."""
    path = list_path(home)
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"list at {path} could not be read: {exc.strerror}")
    except UnicodeDecodeError:
        fail(f"list at {path} is not UTF-8 text")
    patterns: list[re.Pattern[str]] = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        try:
            patterns.append(re.compile(line))
        except re.error as exc:
            fail(f"list at {path} line {number} is not a valid regular expression: {exc.msg}")
    if not patterns:
        fail(f"list at {path} holds no pattern; an empty list checks nothing")
    return patterns


def load_accepted(home: Path) -> set[tuple[str, str]]:
    """``(path, hash)`` for every accepted occurrence; a missing file accepts nothing."""
    path = accepted_path(home)
    if not path.is_file():
        return set()
    accepted: set[tuple[str, str]] = set()
    for number, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        rel, tab, digest = line.partition("\t")
        if not tab or not re.fullmatch(r"[0-9a-f]{40}", digest.strip()):
            fail(f"accepted file at {path} line {number} is not 'path<TAB>sha1hex'")
        accepted.add((rel.strip(), digest.strip()))
    return accepted


# --------------------------------------------------------------------------- the scan


def hits_on(line: str, patterns: Sequence[re.Pattern[str]]) -> list[int]:
    """The ordinals (1-based, the list's own order) of every pattern matching ``line``."""
    return [number for number, pattern in enumerate(patterns, start=1) if pattern.search(line)]


def check(root: Path, rel_paths: Iterable[str], home: Path) -> list[str]:
    """``path:line: private term (pattern N)`` for every unaccepted hit under ``root``.

    The pattern's text is never part of a finding: its ordinal in the list is enough to look it
    up in the private folder, and the output of this check is read in a terminal, pasted into a
    pull request, and kept in CI logs.
    """
    patterns = load_patterns(home)
    if patterns is None:
        print(NO_LIST.format(path=list_path(home)))
        return []
    accepted = load_accepted(home)
    found: list[str] = []
    for rel in scannable(rel_paths):
        text = (root / rel).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            ordinals = hits_on(line, patterns)
            if ordinals and (rel, line_hash(line)) in accepted:
                continue
            found += [f"{rel}:{number}: private term (pattern {n})" for n in ordinals]
    return found


def accept(root: Path, home: Path, spec: str) -> str:
    """Accept one existing occurrence named ``path:line``; return the line appended."""
    rel, _, number = spec.rpartition(":")
    if not rel or not number.isdigit():
        fail(f"{spec!r} is not path:line")
    patterns = load_patterns(home)
    if patterns is None:
        fail(f"no list at {list_path(home)}; there is nothing to accept against")
    path = root / rel
    if not path.is_file():
        fail(f"{rel} is not a file under {root}")
    lines = path.read_text(encoding="utf-8").splitlines()
    index = int(number)
    if not 1 <= index <= len(lines):
        fail(f"{rel} has no line {index}")
    line = lines[index - 1]
    if not hits_on(line, patterns):
        fail(f"{rel}:{index} matches no pattern; there is nothing to accept")
    entry = f"{rel}\t{line_hash(line)}"
    if (rel, line_hash(line)) in load_accepted(home):
        print(f"private terms: already accepted {entry}")
        return entry
    target = accepted_path(home)
    if not home.is_dir():
        fail(f"no private folder at {home}; it is never created here")
    with target.open("a", encoding="utf-8") as handle:
        handle.write(entry + "\n")
    print(f"private terms: accepted {rel}:{index} -> {entry}")
    return entry


# --------------------------------------------------------------------------- cli


def cmd_check(root: Path, home: Path) -> int:
    found = check(root, tracked_files(root), home)
    for finding in found:
        print(f"private terms: {finding}")
    if found:
        print(f"private terms: check FAILED - {len(found)} findings")
        return 1
    if list_path(home).is_file():
        scanned = len(scannable(tracked_files(root)))
        print(f"private terms: check OK; {scanned} files scanned against {list_path(home)}")
    return 0


def build_parser(default_home: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="private_terms",
        description="Check tracked text against the operator's private term list.",
    )
    parser.add_argument(
        "--home", default=str(default_home), help=f"private folder (default: {default_home})"
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="scan tracked text; exit 1 on any unaccepted hit")
    accepted = sub.add_parser("accept", help="accept one existing occurrence")
    accepted.add_argument("spec", help="path:line of the occurrence to accept")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser(private_home())
    args = parser.parse_args(argv)
    home = Path(str(args.home)).expanduser()
    if str(args.command) == "check":
        return cmd_check(ROOT, home)
    accept(ROOT, home, str(args.spec))
    return 0


if __name__ == "__main__":
    sys.exit(main())
