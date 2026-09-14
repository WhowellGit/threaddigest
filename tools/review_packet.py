#!/usr/bin/env python3
"""Build an external review packet from the committed tree, never from the working copy.

The review harness (``docs/PLAN.md`` § Review harness; ``docs/reference/reviews/REGISTER.md``)
sends a packet to an outside reviewer at key moments, and the rule is that nothing but the
clean current tree or a diff ever leaves this machine. This script is that rule made
mechanical (Wes, 2026-09-14):

* every file comes from ``git show HEAD:<path>``, so the packet equals one commit; a dirty
  working tree is refused unless ``--allow-dirty`` is passed, and then the manifest says so;
* only an allowlist of paths is included, so the archive, the earlier project's material,
  secrets, data, fixtures, and prior review verdicts can never ride along (a reviewer handed
  the previous verdict inherits its blind spots);
* the output is a dated folder holding the originals under ``tree/``, four bundled Markdown
  files a research tool can take in one upload, a generated README with the reading order, the
  refute-framed query rendered from its template, the claims list, and ``MANIFEST.json`` with
  a sha256 per file and one packet hash for the register row;
* ``--copy-to DIR`` or ``--desktop`` places the upload set (bundles, README, query, claims,
  manifest) where the human runs the research jobs from.

Standard library only. Usage:

    uv run python tools/review_packet.py [--root DIR] [--out DIR] [--copy-to DIR | --desktop]
                                         [--allow-dirty] [--with-tree]
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import NoReturn

PROJECT = "Insight Miner"
TEMPLATE = Path("docs") / "reference" / "reviews" / "templates" / "external-deep-research.md"
CLAIMS = Path("docs") / "reference" / "reviews" / "templates" / "claims.md"
PLAN = Path("docs") / "PLAN.md"
INTENT_HEADING = "## Intent (read this first)"
DEFAULT_OUT = Path(".build") / "review-packets"
FENCE = "`" * 5  # longer than any fence a Markdown source uses, so nesting cannot break out

#: What goes into each bundle, as tracked paths (a directory means every tracked file under
#: it). Order is the reading order inside the bundle.
BUNDLES: dict[str, tuple[str, ...]] = {
    "1-documents": (
        "CLAUDE.md",
        "docs/PLAN.md",
        "docs/decisions/DECISIONS.md",
        "docs/TEST_STRATEGY.md",
        "docs/INDEX.md",
        "docs/runbook/RUNBOOK.md",
        "docs/runbook/KNOWN_ISSUES.md",
        "docs/runbook/GUARDS.md",
        "docs/reference/reviews/REGISTER.md",
        "docs/reference/AGENT_BRIEF.md",
        "docs/learnings",
        "docs/insights",
        "src/insightminer/db/schema.sql",
    ),
    "2-harness": (
        "Makefile",
        "pyproject.toml",
        ".importlinter",
        ".pre-commit-config.yaml",
        ".gitleaks.toml",
        ".github/workflows",
        ".claude/settings.json",
        ".claude/rules",
        ".claude/skills",
        ".ratchets",
        "tools",
        "tests/conftest.py",
        "tests/gates",
    ),
    "3-source": ("src",),
    "4-tests": ("tests",),
}
#: Never included, whatever the allowlist says. Prefix match on the tracked path.
EXCLUDED_PREFIXES = (
    ".env",
    "data/",
    "docs/reference/earlier-project",
    "docs/reference/reviews/2026-",
    "memory-snapshot/",
    "tests/fixtures/",
    "docs/PLAN.html",
)
UPLOAD_SET = ("00-README.md", "01-QUERY.md", "02-CLAIMS.md", "MANIFEST.json")
LANG = {
    ".py": "python",
    ".md": "markdown",
    ".sql": "sql",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".json": "json",
    ".sh": "bash",
    ".txt": "text",
    "": "text",
}


def fail(message: str) -> NoReturn:
    msg = f"review_packet: {message}"
    raise SystemExit(msg)


def git(root: Path, *args: str) -> str:
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
        )
    except OSError as exc:
        fail(f"git could not run: {exc}")
    if proc.returncode != 0:
        fail(f"git {' '.join(args)} failed: {proc.stderr.strip()[:300]}")
    return proc.stdout


def git_bytes(root: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, check=False)
    if proc.returncode != 0:
        fail(f"git {' '.join(args)} failed: {proc.stderr.decode(errors='replace').strip()[:300]}")
    return proc.stdout


def excluded(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return rel.startswith(EXCLUDED_PREFIXES) or name.startswith(".env")


def tracked_under(root: Path, spec: str) -> list[str]:
    """Tracked files under ``spec`` (a file or a directory), in git's sorted order."""
    out = git(root, "ls-files", "-z", "--", spec)
    return [p for p in out.split("\0") if p]


@dataclass
class Packet:
    root: Path
    commit: str
    date: str
    dirty: bool
    files: dict[str, bytes] = field(default_factory=dict)  # rel path -> content, in order
    bundle_files: dict[str, list[str]] = field(default_factory=dict)
    skipped_binary: list[str] = field(default_factory=list)

    def collect(self) -> None:
        seen: set[str] = set()
        for bundle, specs in BUNDLES.items():
            members: list[str] = []
            for spec in specs:
                for rel in tracked_under(self.root, spec):
                    if rel in seen or excluded(rel):
                        continue
                    seen.add(rel)
                    content = git_bytes(self.root, "show", f"HEAD:{rel}")
                    try:
                        content.decode("utf-8")
                    except UnicodeDecodeError:
                        self.skipped_binary.append(rel)
                        continue
                    self.files[rel] = content
                    members.append(rel)
            self.bundle_files[bundle] = members

    @property
    def packet_hash(self) -> str:
        digest = hashlib.sha256()
        for rel, content in sorted(self.files.items()):
            digest.update(f"{rel} {sha256(content)}\n".encode())
        return digest.hexdigest()


def sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def render_bundle(name: str, packet: Packet) -> str:
    members = packet.bundle_files[name]
    parts = [
        f"# {PROJECT} review packet, bundle {name}\n",
        f"Commit `{packet.commit}`, built {packet.date}. Every file below is the committed "
        f"text at that commit, verbatim, one section per file; fences use five backticks so "
        f"the files' own fences stay intact.\n",
        "## Files in this bundle\n",
        *(f"- `{rel}`" for rel in members),
        "",
    ]
    for rel in members:
        lang = LANG.get(Path(rel).suffix, "text")
        text = packet.files[rel].decode("utf-8")
        parts.append(f"\n---\n\n## `{rel}`\n\n{FENCE}{lang}\n{text.rstrip()}\n{FENCE}\n")
    return "\n".join(parts)


def intent_paragraph(packet: Packet) -> str:
    text = packet.files.get(PLAN.as_posix(), b"").decode("utf-8")
    lines = text.splitlines()
    try:
        start = lines.index(INTENT_HEADING) + 1
    except ValueError:
        return "(the plan's intent block was not found)"
    body: list[str] = []
    for line in lines[start:]:
        if line.startswith("## "):
            break
        if line.strip():
            body.append(line.strip())
    return " ".join(body)


def render_readme(packet: Packet, bundle_sizes: dict[str, int]) -> str:
    dirty = (
        "\n> **Built from a dirty working tree** with `--allow-dirty`: the contents are the "
        "commit above, not the uncommitted edits.\n"
        if packet.dirty
        else ""
    )
    rows = "\n".join(
        f"| `{name}.md` | {size:,} | {len(packet.bundle_files[name])} |"
        for name, size in bundle_sizes.items()
    )
    skipped = "\n".join(f"- `{rel}`" for rel in packet.skipped_binary) or "- (none)"
    excluded_rules = "\n".join(f"- `{prefix}`" for prefix in EXCLUDED_PREFIXES)
    return f"""# {PROJECT} review packet: commit `{packet.commit[:12]}`, {packet.date}

This packet is the committed tree of a small personal system at one commit, assembled by
`tools/review_packet.py`. `MANIFEST.json` carries a sha256 for every file and one packet hash,
`{packet.packet_hash[:16]}…`, which the project's review register cites. Nothing here comes
from any other system.
{dirty}
## What the system is

{intent_paragraph(packet)}

## What you are asked to do

Read `01-QUERY.md` first; it is the brief. In one line: find what is wrong, what it would
cost, and how sure you are, citing files and lines, and say "cannot judge" where you lack the
context rather than guessing. `02-CLAIMS.md` lists the load-bearing claims with the test that
backs each; try to falsify them.

## Reading order

1. `01-QUERY.md`, then `02-CLAIMS.md`.
2. `1-documents.md`: the working agreement (`CLAUDE.md`), the plan (its intent block first),
   the decisions log (settled negatives before proposing a lever), the runbook, the guards
   ledger, known issues, learnings, and the database schema.
3. `2-harness.md`: what enforces the working agreement (hooks, ratchets, gate tests, configs).
4. `3-source.md`, then `4-tests.md`.

## Contents

| Bundle | Bytes | Files |
|---|---|---|
{rows}

Skipped because binary:

{skipped}

Excluded by rule (never part of a packet): secrets, data, fixtures, the earlier project's
material, the memory snapshot, and the dated review reports, which hold prior verdicts and are
withheld so that this review is independent of them:

{excluded_rules}
"""


def render_query(packet: Packet, template: str) -> str:
    return (
        template.replace("{project}", PROJECT)
        .replace("{commit}", packet.commit)
        .replace("{date}", packet.date)
        .replace("{packet_hash}", packet.packet_hash)
    )


def head_text(root: Path, rel: Path, what: str) -> str:
    """A committed file the packet is rendered from (the brief, the claims), read at HEAD."""
    if not tracked_under(root, rel.as_posix()):
        fail(f"{what} {rel.as_posix()} is not a tracked file at HEAD")
    return git_bytes(root, "show", f"HEAD:{rel.as_posix()}").decode("utf-8")


def write_packet(packet: Packet, out: Path, with_tree: bool = True) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    bundle_sizes: dict[str, int] = {}
    bundle_hashes: dict[str, str] = {}
    for name in BUNDLES:
        text = render_bundle(name, packet).encode("utf-8")
        (out / f"{name}.md").write_bytes(text)
        bundle_sizes[name] = len(text)
        bundle_hashes[name] = sha256(text)
    query = render_query(packet, head_text(packet.root, TEMPLATE, "query template"))
    (out / "01-QUERY.md").write_text(query, encoding="utf-8")
    (out / "02-CLAIMS.md").write_text(
        head_text(packet.root, CLAIMS, "claims list"), encoding="utf-8"
    )
    (out / "00-README.md").write_text(render_readme(packet, bundle_sizes), encoding="utf-8")
    if with_tree:
        for rel, content in packet.files.items():
            target = out / "tree" / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
    manifest: dict[str, object] = {
        "project": PROJECT,
        "commit": packet.commit,
        "built": packet.date,
        "working_tree": "dirty" if packet.dirty else "clean",
        "packet_sha256": packet.packet_hash,
        "files": [
            {"path": rel, "bytes": len(content), "sha256": sha256(content)}
            for rel, content in packet.files.items()
        ],
        "bundles": [
            {
                "name": f"{name}.md",
                "bytes": bundle_sizes[name],
                "sha256": bundle_hashes[name],
                "files": packet.bundle_files[name],
            }
            for name in BUNDLES
        ],
        "skipped_binary": packet.skipped_binary,
        "excluded_prefixes": list(EXCLUDED_PREFIXES),
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def copy_upload_set(out: Path, dest: Path) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    names = [*UPLOAD_SET, *(f"{name}.md" for name in BUNDLES)]
    for name in names:
        shutil.copy2(out / name, dest / name)
    return names


def build(
    root: Path, out: Path, *, allow_dirty: bool, with_tree: bool
) -> tuple[Packet, dict[str, object]]:
    status = git(root, "status", "--porcelain")
    dirty = bool(status.strip())
    if dirty and not allow_dirty:
        fail(
            "the working tree is not clean; commit first so the packet equals one commit "
            "(or pass --allow-dirty, which stamps the manifest and README as dirty)"
        )
    commit = git(root, "rev-parse", "HEAD").strip()
    packet = Packet(root=root, commit=commit, date=dt.date.today().isoformat(), dirty=dirty)
    packet.collect()
    if not packet.files:
        fail("nothing to pack: no tracked files matched the allowlist")
    manifest = write_packet(packet, out, with_tree=with_tree)
    return packet, manifest


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="review_packet.py", description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--root", type=Path, default=Path(__file__).resolve().parent.parent, help="repository root"
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help=f"packet folder; default <root>/{DEFAULT_OUT}/<date>-<commit>",
    )
    parser.add_argument("--copy-to", type=Path, default=None, help="also copy the upload set here")
    parser.add_argument(
        "--desktop",
        action="store_true",
        help="copy the upload set to ~/Desktop/insightminer-review-packet-<date>-<commit>",
    )
    parser.add_argument(
        "--allow-dirty", action="store_true", help="build from HEAD despite a dirty tree"
    )
    parser.add_argument(
        "--with-tree",
        action="store_true",
        help="also copy the tree/ folder of originals into the copy destination",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root: Path = args.root.resolve()
    commit_short = git(root, "rev-parse", "--short", "HEAD").strip()
    stamp = f"{dt.date.today().isoformat()}-{commit_short}"
    out: Path = args.out or root / DEFAULT_OUT / stamp
    packet, manifest = build(root, out, allow_dirty=args.allow_dirty, with_tree=True)
    print(f"packet: {out}")
    print(f"commit: {packet.commit} ({'dirty tree' if packet.dirty else 'clean tree'})")
    print(f"packet sha256: {packet.packet_hash}")
    for bundle in manifest["bundles"]:  # type: ignore[union-attr]
        print(
            f"bundle {bundle['name']:<16} {bundle['bytes']:>9,} bytes  {len(bundle['files'])} files"
        )
    if packet.skipped_binary:
        print(f"skipped binary: {', '.join(packet.skipped_binary)}")
    dest: Path | None = args.copy_to
    if args.desktop:
        dest = Path.home() / "Desktop" / f"insightminer-review-packet-{stamp}"
    if dest is not None:
        names = copy_upload_set(out, dest)
        if args.with_tree:
            shutil.copytree(out / "tree", dest / "tree", dirs_exist_ok=True)
            names.append("tree/")
        print(f"copied to {dest}: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
