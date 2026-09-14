#!/usr/bin/env python3
"""Snapshot, verify and audit Claude Code's auto-memory for this repo.

The memory directory (``~/.claude/projects/<slug>/memory``) is keyed to the repo's absolute
path and lives outside git: a repo move strands it, a machine wipe loses it, and nothing in
the tree can regenerate it. It is the only asset here that is not derivable from code or data,
so it gets a committed snapshot and a mechanical audit rather than a habit.

Three rules come from the earlier project's incidents and are the reason this file exists.

1. **Add-or-update only.** An export there mirrored deletions, so a memory file deleted
   upstream was deleted from the backup too ("the memory system ate the memory"). Here a file
   that is present in the snapshot and absent from live memory is *never* removed: it is
   reported as ``live-missing`` and kept. There is no delete path in this tool.
2. **Copying is not restoring.** Its restore printed a copy count and never checked the
   result, so a partial restore looked identical to a complete one. Here both ``export`` and
   ``restore`` re-read every file from disk afterwards and assert completeness --
   every source file present at the destination with identical bytes -- and exit non-zero
   otherwise. :func:`copy_file` is the seam a positive control replaces to prove the
   verification can go red (``tests/gates/test_memory_snapshot.py``).
3. **The index is the recall mechanism.** There, 28 index links pointed at files that no
   longer existed and 127 of 166 files were reachable only through a second-tier index, so
   most of the memory was effectively unreadable. Here ``check`` reports topic files no
   ``MEMORY.md`` line links (unreachable), index links whose target is gone (dangling), the
   index against a size budget, and the frontmatter contract every topic file must satisfy.

Everything is reported as pasted output: one line per finding plus a summary line, so a
``make check`` block shows the memory's state instead of a claim about it.

Subcommands: ``check`` (audit live memory, exit 1 on any finding), ``export``
(live -> ``memory-snapshot/``, then verify), ``diff`` (what ``export`` would change, exit 1
if anything would), ``restore --to <dir>`` (snapshot -> a target dir, then verify; refuses
the live directory without ``--yes-live``).

Stdlib only, and no writes anywhere except the snapshot directory or an explicit
``restore --to`` target.
"""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

#: Budget for the index. It is the recall surface: past roughly this size an agent skims it,
#: and entries that are only skimmed are not recalled. Both are deliberately small and are
#: meant to be argued with -- raise them by editing these two constants, in a commit that
#: says why, rather than by letting the index grow unwatched.
INDEX_MAX_LINES = 60
INDEX_MAX_BYTES = 12 * 1024

#: The index file, and the topic-file frontmatter contract (``metadata.type`` values).
INDEX_NAME = "MEMORY.md"
TOPIC_TYPES = frozenset({"user", "feedback", "project", "reference"})

#: Committed snapshot, relative to the repo root. Not under ``docs/``: the doc router gate
#: requires every markdown file under ``docs/`` to be listed in ``docs/INDEX.md``, and these
#: files are a mirror of something outside the repo, not part of the corpus.
SNAPSHOT_DIRNAME = "memory-snapshot"

#: Printed verbatim when there is no live memory directory (CI, a fresh clone, a moved repo).
#: A real state, not a skip: it is visible in the output and ``check``/``diff`` still exit 0.
NO_LIVE_DIR = "memory: no live memory directory at {path}"

#: One index entry: ``- [Title](file.md) — hook``.
INDEX_LINK = re.compile(r"^\s*[-*]\s*\[[^\]]*\]\(([^)]+)\)")


# --------------------------------------------------------------------------------------
# locating things
# --------------------------------------------------------------------------------------
def main_checkout(start: Path) -> Path:
    """The checkout the memory belongs to, given any tree.

    A git worktree is a second working copy of the same repo at a different path, and the
    memory is keyed to a path. Keying a worktree's memory to the worktree would report "no
    live memory directory" for every agent working in one, which is worse than wrong: it
    looks like a real state. A worktree's ``.git`` is a file pointing at
    ``<main checkout>/.git/worktrees/<name>``, so the main checkout is recoverable from it.
    """
    root = start.resolve()
    pointer = root / ".git"
    if not pointer.is_file():
        return root
    text = pointer.read_text(encoding="utf-8").strip()
    if not text.startswith("gitdir:"):
        return root
    gitdir = Path(text.split(":", 1)[1].strip())
    if not gitdir.is_absolute():
        gitdir = (root / gitdir).resolve()
    if gitdir.parent.name == "worktrees" and gitdir.parent.parent.name == ".git":
        return gitdir.parent.parent.parent
    return root


def slug_for(path: Path) -> str:
    """Claude Code's project slug: the absolute path with ``/`` replaced by ``-``."""
    return str(path).replace("/", "-")


def memory_dir_for(repo_root: Path) -> Path:
    return Path.home() / ".claude" / "projects" / slug_for(repo_root) / "memory"


def default_paths(tree: Path) -> tuple[Path, Path]:
    """``(live memory, snapshot)`` for the tree this tool is running in.

    The two are keyed differently on purpose. Live memory belongs to the *main checkout*
    (that is the path Claude Code keyed it to, and a worktree shares it). The snapshot is a
    committed file in *this* tree: resolving it to the main checkout as well would have an
    agent working in a worktree write its snapshot outside the branch under review, where
    nothing is reviewing it and the next `git status` there finds a stray directory.
    """
    return memory_dir_for(main_checkout(tree)), tree / SNAPSHOT_DIRNAME


def relative_files(root: Path) -> list[str]:
    """Every file under ``root`` as a sorted relative posix path; dotfiles excluded."""
    if not root.is_dir():
        return []
    found: list[str] = []
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(root)
        if any(part.startswith(".") for part in relative.parts):
            continue
        found.append(relative.as_posix())
    return found


def same_dir(left: Path, right: Path) -> bool:
    return left.expanduser().resolve() == right.expanduser().resolve()


# --------------------------------------------------------------------------------------
# check: integrity of the live memory directory
# --------------------------------------------------------------------------------------
def index_links(index_text: str) -> list[tuple[int, str]]:
    """``(line number, target)`` for every local link in the index."""
    links: list[tuple[int, str]] = []
    for lineno, line in enumerate(index_text.splitlines(), start=1):
        match = INDEX_LINK.match(line)
        if match is None:
            continue
        target = match.group(1).strip()
        if "://" in target or target.startswith("#"):
            continue
        links.append((lineno, target))
    return links


def parse_frontmatter(text: str) -> dict[str, str] | None:
    """Flatten a topic file's frontmatter to ``{"name": …, "metadata.type": …}``.

    Deliberately not a YAML parser (stdlib only, and the contract is four scalar keys):
    top-level ``key: value`` lines, plus one level of indented keys under a parent whose
    value is empty. ``None`` means there is no closed ``---`` block to read.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return None
    fields: dict[str, str] = {}
    parent = ""
    for line in lines[1:]:
        if line.strip() == "---":
            return fields
        if not line.strip() or line.lstrip().startswith("#") or ":" not in line:
            continue
        indented = line[:1].isspace()
        key, _, value = line.strip().partition(":")
        key = key.strip()
        value = value.strip().strip("\"'")
        if indented and parent:
            fields[f"{parent}.{key}"] = value
        else:
            fields[key] = value
            parent = key if not value else ""
    return None


def frontmatter_problems(path: Path) -> list[str]:
    fields = parse_frontmatter(path.read_text(encoding="utf-8"))
    if fields is None:
        return ["no closed --- frontmatter block"]
    problems = [f"missing {key}" for key in ("name", "description") if not fields.get(key)]
    kind = fields.get("metadata.type", "")
    if not kind:
        problems.append("missing metadata.type")
    elif kind not in TOPIC_TYPES:
        allowed = ", ".join(sorted(TOPIC_TYPES))
        problems.append(f'metadata.type "{kind}" not in {{{allowed}}}')
    return problems


#: A sibling memory home belongs to this project when any file in it names the project.
PROJECT_WORD = "insightminer"


def projects_root_for(memory_dir: Path) -> Path | None:
    """``~/.claude/projects`` when ``memory_dir`` follows the ``projects/<key>/memory`` layout."""
    root = memory_dir.parent.parent
    return root if root.name == "projects" else None


def second_home_findings(memory_dir: Path, projects_root: Path) -> list[str]:
    """One finding per other memory home under ``projects_root`` holding this project's topics.

    Two homes diverge silently: on 2026-09-14 the Desktop-keyed home and the repo-keyed one
    differed by 589 bytes in one topic file, and nothing looked at the second. A second home may
    hold a pointer index and nothing else; a home that never mentions the project is another
    project's and is left alone.
    """
    findings: list[str] = []
    live = memory_dir.resolve()
    if not projects_root.is_dir():
        return findings
    for candidate in sorted(projects_root.iterdir()):
        home = candidate / "memory"
        if not home.is_dir() or home.resolve() == live:
            continue
        files = [p for p in home.rglob("*.md") if p.is_file()]
        topics = [p for p in files if p.name != INDEX_NAME]
        ours = any(
            PROJECT_WORD in p.read_text(encoding="utf-8", errors="replace").lower() for p in files
        )
        if topics and ours:
            findings.append(
                f"memory: second home {home} holds {len(topics)} topic files; one memory home "
                "(move them to the archive, keep the pointer index)"
            )
    return findings


def check_memory(memory_dir: Path, projects_root: Path | None = None) -> tuple[list[str], str]:
    """Audit the live memory directory: one line per finding, plus a summary line."""
    findings: list[str] = []
    topics = [
        rel for rel in relative_files(memory_dir) if rel.endswith(".md") and rel != INDEX_NAME
    ]
    index = memory_dir / INDEX_NAME
    links: list[tuple[int, str]] = []
    lines = size = 0
    if not index.is_file():
        findings.append(f"memory: index missing: no {INDEX_NAME} in {memory_dir}")
    else:
        text = index.read_text(encoding="utf-8")
        lines, size = len(text.splitlines()), len(index.read_bytes())
        links = index_links(text)
        if lines > INDEX_MAX_LINES:
            findings.append(f"memory: index over budget: {lines} lines (max {INDEX_MAX_LINES})")
        if size > INDEX_MAX_BYTES:
            findings.append(f"memory: index over budget: {size} bytes (max {INDEX_MAX_BYTES})")
        findings += [
            f"memory: dangling {INDEX_NAME}:{lineno} -> {target} (no such file)"
            for lineno, target in links
            if not (memory_dir / target).is_file()
        ]
    linked = {target for _, target in links}
    findings += [
        f"memory: unreachable {rel} (no {INDEX_NAME} line links it)"
        for rel in topics
        if rel not in linked
    ]
    findings += [
        f"memory: frontmatter {rel}: " + "; ".join(problems)
        for rel in topics
        if (problems := frontmatter_problems(memory_dir / rel))
    ]
    if projects_root is not None:
        findings += second_home_findings(memory_dir, projects_root)
    verdict = f"FAILED - {len(findings)} findings" if findings else "OK"
    summary = (
        f"memory: check {verdict}; {len(topics)} topic files, {len(links)} index links, "
        f"index {lines} lines / {size} bytes (budget {INDEX_MAX_LINES} / {INDEX_MAX_BYTES})"
    )
    return findings, summary


# --------------------------------------------------------------------------------------
# copy, add-or-update only, then verify
# --------------------------------------------------------------------------------------
@dataclass(frozen=True)
class Sync:
    """What a copy from source to destination would do, or did."""

    added: list[str]
    updated: list[str]
    unchanged: list[str]
    live_missing: list[str]

    @property
    def changes(self) -> int:
        return len(self.added) + len(self.updated)


def copy_file(source: Path, destination: Path) -> None:
    """Copy one file. The seam a positive control replaces to simulate a silent bad copy."""
    shutil.copy2(source, destination)


def plan_sync(source: Path, destination: Path) -> Sync:
    """Classify every source file, and list destination files the source no longer has.

    ``live_missing`` is reported and never acted on: deletion upstream is not a reason to
    destroy the only surviving copy of a memory file.
    """
    added: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    source_files = relative_files(source)
    for relative in source_files:
        target = destination / relative
        if not target.is_file():
            added.append(relative)
        elif target.read_bytes() != (source / relative).read_bytes():
            updated.append(relative)
        else:
            unchanged.append(relative)
    known = set(source_files)
    live_missing = [rel for rel in relative_files(destination) if rel not in known]
    return Sync(added, updated, unchanged, live_missing)


def apply_sync(source: Path, destination: Path, plan: Sync) -> None:
    for relative in [*plan.added, *plan.updated]:
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        copy_file(source / relative, target)


def verify_complete(source: Path, destination: Path) -> list[str]:
    """Re-read from disk: every source file present at the destination with identical bytes."""
    failures: list[str] = []
    for relative in relative_files(source):
        target = destination / relative
        if not target.is_file():
            failures.append(f"missing at destination: {relative}")
        elif target.read_bytes() != (source / relative).read_bytes():
            failures.append(f"bytes differ at destination: {relative}")
    return failures


def copy_and_verify(source: Path, destination: Path, label: str) -> int:
    """Add-or-update copy, print what happened, then assert completeness byte-for-byte."""
    destination.mkdir(parents=True, exist_ok=True)
    plan = plan_sync(source, destination)
    apply_sync(source, destination, plan)
    print_plan(plan, label)
    print(
        f"memory: {label} added {len(plan.added)}, updated {len(plan.updated)}, "
        f"unchanged {len(plan.unchanged)}, live-missing {len(plan.live_missing)} "
        f"-> {destination}"
    )
    failures = verify_complete(source, destination)
    for failure in failures:
        print(f"memory: verify {failure}")
    total = len(relative_files(source))
    if failures:
        print(f"memory: {label} FAILED verification: {len(failures)} of {total} files")
        return 1
    print(f"memory: {label} verified {total} files byte-for-byte at {destination}")
    return 0


def print_plan(plan: Sync, label: str, add: str = "added", update: str = "updated") -> None:
    for relative in plan.added:
        print(f"memory: {label} {add} {relative}")
    for relative in plan.updated:
        print(f"memory: {label} {update} {relative}")
    for relative in plan.live_missing:
        print(f"memory: live-missing {relative} (kept in the snapshot, never deleted)")


# --------------------------------------------------------------------------------------
# subcommands
# --------------------------------------------------------------------------------------
def cmd_check(memory_dir: Path) -> int:
    if not memory_dir.is_dir():
        print(NO_LIVE_DIR.format(path=memory_dir))
        return 0
    findings, summary = check_memory(memory_dir, projects_root_for(memory_dir))
    for finding in findings:
        print(finding)
    print(summary)
    return 1 if findings else 0


def cmd_export(memory_dir: Path, snapshot_dir: Path) -> int:
    if not memory_dir.is_dir():
        print(NO_LIVE_DIR.format(path=memory_dir))
        print("memory: export FAILED: nothing to snapshot")
        return 1
    return copy_and_verify(memory_dir, snapshot_dir, "export")


def cmd_diff(memory_dir: Path, snapshot_dir: Path) -> int:
    if not memory_dir.is_dir():
        print(NO_LIVE_DIR.format(path=memory_dir))
        return 0
    plan = plan_sync(memory_dir, snapshot_dir)
    print_plan(plan, "diff would", add="add", update="update")
    print(
        f"memory: diff add {len(plan.added)}, update {len(plan.updated)}, "
        f"unchanged {len(plan.unchanged)}, live-missing {len(plan.live_missing)} "
        f"-> {snapshot_dir}"
    )
    return 1 if plan.changes else 0


def cmd_restore(snapshot_dir: Path, target: Path, memory_dir: Path, yes_live: bool) -> int:
    if not snapshot_dir.is_dir():
        print(f"memory: no snapshot directory at {snapshot_dir}")
        return 1
    if same_dir(target, memory_dir) and not yes_live:
        print(
            f"memory: refusing to restore into the live memory directory {target} "
            "without --yes-live"
        )
        return 2
    return copy_and_verify(snapshot_dir, target, "restore")


def build_parser(default_memory: Path, default_snapshot: Path) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="memory_snapshot",
        description="Audit and snapshot Claude Code's auto-memory for this repo.",
    )
    parser.add_argument(
        "--memory-dir",
        default=str(default_memory),
        help=f"live memory directory (default: {default_memory})",
    )
    parser.add_argument(
        "--snapshot-dir",
        default=str(default_snapshot),
        help=f"committed snapshot directory (default: {default_snapshot})",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check", help="audit live memory; exit 1 on any finding")
    sub.add_parser("export", help="copy live memory into the snapshot, then verify")
    sub.add_parser("diff", help="what export would change; exit 1 if anything would")
    restore = sub.add_parser("restore", help="copy the snapshot into a directory, then verify")
    restore.add_argument("--to", required=True, help="destination directory")
    restore.add_argument(
        "--yes-live",
        action="store_true",
        help="allow restoring into the live memory directory",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    memory_default, snapshot_default = default_paths(Path(__file__).resolve().parents[1])
    parser = build_parser(memory_default, snapshot_default)
    args = parser.parse_args(argv)
    memory_dir = Path(str(args.memory_dir)).expanduser()
    snapshot_dir = Path(str(args.snapshot_dir)).expanduser()
    command = str(args.command)
    if command == "check":
        return cmd_check(memory_dir)
    if command == "export":
        return cmd_export(memory_dir, snapshot_dir)
    if command == "diff":
        return cmd_diff(memory_dir, snapshot_dir)
    target = Path(str(args.to)).expanduser()
    yes_live = bool(args.yes_live)
    return cmd_restore(snapshot_dir, target, memory_dir, yes_live)


if __name__ == "__main__":
    sys.exit(main())
