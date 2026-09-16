#!/usr/bin/env python3
"""Old-to-new commit hashes, recorded once per history rewrite, so a citation survives one.

Birth incident (2026-09-16, D-35): purging the memory snapshot from history rewrote most of
the commits on ``main``, and the documents cite commit hashes in three places the rules forbid
rewriting -- the append-only decisions log, the append-only review register, and the reference
records, which are added and never edited. Two gates resolve those citations against git
(``tests/gates/test_known_issues_cite_collected_tests.py`` requires every cited hash to be an
ancestor of ``HEAD``; ``tests/gates/test_review_register.py`` matches a review row's scope
against the commits it must cover). Without a map both would have to stop looking, which is the
weakening the working agreement forbids; with one they still look, and a rewritten commit is
followed to what it became before the same ancestry check is applied.

A map file is a reference record: added by the rewrite, never edited, one file per rewrite, so
a hash rewritten twice is followed through both in turn. Nothing here rescues a hash the map
does not name, and a mapped hash whose successor is not an ancestor of ``HEAD`` still fails --
the map changes what a citation points at, never whether it has to resolve.

Format, one line per rewritten commit, tab separated: ``<old full hash>\t<new full hash>``,
with an optional third field (the subject) for the reader. ``#`` comments and blank lines are
ignored. Stdlib only.
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path

#: Every map, oldest first by name; each rewrite adds one dated file.
REMAP_GLOB = "docs/reference/hash-remap-*.tsv"
FULL_HASH = 40


def parse_remap(text: str) -> dict[str, str]:
    """``{old full hash: new full hash}`` for every data line; a malformed line is skipped."""
    found: dict[str, str] = {}
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        fields = [part.strip() for part in stripped.split("\t") if part.strip()]
        if len(fields) < 2:
            continue
        old, new = fields[0], fields[1]
        if len(old) == FULL_HASH and len(new) == FULL_HASH:
            found[old] = new
    return found


def load_remap(root: Path) -> dict[str, str]:
    """Every map under ``root``, merged; a later file may remap a hash an earlier one produced."""
    found: dict[str, str] = {}
    for path in sorted(root.glob(REMAP_GLOB)):
        found.update(parse_remap(path.read_text(encoding="utf-8")))
    return found


def successors(remap: Mapping[str, str], sha: str) -> list[str]:
    """Every hash ``sha`` (a prefix of a rewritten commit) became, following the chain.

    A hash rewritten twice has two entries in two files; both are returned, so a citation
    resolves whichever rewrite the reader's clone stops at. Cycles cannot loop: a hash already
    seen is never followed again.
    """
    seen: set[str] = set()
    out: list[str] = []
    frontier = [sha]
    while frontier:
        current = frontier.pop()
        for old, new in remap.items():
            if old.startswith(current) and new not in seen:
                seen.add(new)
                out.append(new)
                frontier.append(new)
    return out
