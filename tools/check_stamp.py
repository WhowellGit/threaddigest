#!/usr/bin/env python3
"""Leave a green stamp behind when ``make check`` passes, naming the tree it passed on.

Birth incident (2026-09-14, the packet panel's dry run): with no remote and the check wired
to the push hook, nothing mechanical stopped a red tree from being fast-forwarded into
``main``; the two-sessions incident that morning did exactly that. The fix has two halves.
This script is the first: it runs as the last step of ``make check`` (so it is reached only
when every step before it passed) and writes ``.build/check-green.json`` with the hash of the
tree the check ran on. The git hook is the second: it refuses ``git merge`` into ``main``
unless that stamp names the tree of the branch being merged (``tools/hooks/no_bypass_git.sh``).

Which tree did the check run on? The tracked content of the working tree, which is what
``git stash create`` records without touching anything (staged and unstaged changes alike),
or ``HEAD`` when the tree is clean. Untracked files are the one thing that cannot be named
(pytest collects them, but no commit can contain them unstaged), so with untracked files
present no stamp is written and the reason is printed; ``git add`` them first. A stale stamp
is removed whenever a new one cannot be written.

The flow this shapes: stage everything, run the check, commit, switch to ``main``, merge.
The stamp names the staged tree, the commit has the same tree, and the merge is allowed.

Usage: uv run python tools/check_stamp.py [--root DIR]
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

STAMP = Path(".build") / "check-green.json"


def git(root: Path, *args: str) -> str | None:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
        )
    except OSError:
        return None
    return proc.stdout.strip() if proc.returncode == 0 else None


def checked_tree(root: Path) -> tuple[str | None, str]:
    """The tree hash the check ran on, or None with the reason no stamp can be written."""
    status = git(root, "status", "--porcelain", "--untracked-files=normal")
    if status is None:
        return None, "not a git repository"
    untracked = [line[3:] for line in status.splitlines() if line.startswith("??")]
    if untracked:
        return (
            None,
            f"{len(untracked)} untracked file(s) are not in any tree (git add them): "
            + ", ".join(untracked[:5]),
        )
    if not status.strip():
        tree = git(root, "rev-parse", "HEAD^{tree}")
        return tree, "clean working tree"
    stash = git(root, "stash", "create")
    if not stash:
        tree = git(root, "rev-parse", "HEAD^{tree}")
        return tree, "clean working tree"
    return git(root, "rev-parse", f"{stash}^{{tree}}"), "working tree with tracked changes"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="check_stamp.py", description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent.parent, help="repository root"
    )
    args = parser.parse_args(argv)
    root: Path = args.root.resolve()
    stamp = root / STAMP
    tree, reason = checked_tree(root)
    if tree is None:
        if stamp.exists():
            stamp.unlink()
        print(f"check stamp: none written ({reason}); a merge into main will be refused")
        return 0
    stamp.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "tree": tree,
        "commit": git(root, "rev-parse", "HEAD"),
        "at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "basis": reason,
    }
    stamp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"check stamp: green for tree {tree[:12]} ({reason}); a merge into main is allowed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
