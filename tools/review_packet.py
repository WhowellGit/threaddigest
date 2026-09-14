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
REDACTIONS = Path("docs") / "reference" / "reviews" / "templates" / "redactions.txt"
#: Placeholders for the owner's identity, which is read from git and the machine at build
#: time (Wes, 2026-09-14): the name, the email, the email's domain, the machine username.
NAME_PLACEHOLDER = "the owner"
EMAIL_PLACEHOLDER = "owner@example.invalid"
DOMAIN_PLACEHOLDER = "example.invalid"
USER_PLACEHOLDER = "[user]"
EXTRA_PLACEHOLDER = "the-owner"
MIN_REDACTION_LENGTH = 4
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
        "docs/recent/STATUS.md",
        "docs/TEST_STRATEGY.md",
        "docs/INDEX.md",
        "docs/runbook/RUNBOOK.md",
        "docs/runbook/KNOWN_ISSUES.md",
        "docs/runbook/GUARDS.md",
        "docs/reference/reviews/REGISTER.md",
        "docs/reference/AGENT_BRIEF.md",
        "docs/learnings",
        "docs/insights",
        # inputs to the design, not verdicts on it: the research report the collector's
        # Reddit facts come from, and the design review the deletion predicates cite
        "docs/reference/2026-09-11-compass-research-report.md",
        "docs/reference/reviews/2026-09-12-collector-design-review.md",
        "config",
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
#: Never included unless the allowlist names the exact file. Prefix match on the tracked path.
EXCLUDED_PREFIXES = (
    ".env",
    "data/",
    "docs/reference/earlier-project",
    "docs/reference/reviews/2026-",
    "memory-snapshot/",
    "tests/fixtures/",
    "docs/PLAN.html",
    # The identifier gate's own test spells out the banned identifiers as its positive controls
    # (split strings that defeat the scan, not a reader); the ledger row G35 describes it.
    "tests/gates/test_no_imported_identifiers.py",
    # the owner-identity list is an input to the redaction, never content
    "docs/reference/reviews/templates/redactions.txt",
)
UPLOAD_SET = ("00-README.md", "01-QUERY.md", "02-CLAIMS.md", "MANIFEST.json")
#: A bundle larger than this is written in numbered parts, so no single upload is beyond what
#: a retrieval-based research tool handles in one pass (about 110k tokens at four bytes each).
PART_BYTES = 450_000
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


def owner_identity(root: Path) -> list[tuple[str, str]]:
    """Strings to replace and their placeholders, longest first: the git identity, the
    email's domain, the machine username, and the entries of the redactions file at HEAD."""
    pairs: list[tuple[str, str]] = []
    name = git_optional(root, "config", "user.name")
    email = git_optional(root, "config", "user.email")
    if name:
        pairs.append((name, NAME_PLACEHOLDER))
    if email:
        pairs.append((email, EMAIL_PLACEHOLDER))
        if "@" in email:
            pairs.append((email.split("@", 1)[1], DOMAIN_PLACEHOLDER))
    pairs.append((Path.home().name, USER_PLACEHOLDER))
    if tracked_under(root, REDACTIONS.as_posix()):
        for line in (
            git_bytes(root, "show", f"HEAD:{REDACTIONS.as_posix()}").decode("utf-8").splitlines()
        ):
            entry = line.split("#", 1)[0].strip()
            if not entry:
                continue
            original, sep, placeholder = entry.partition("=>")
            pairs.append((original.strip(), placeholder.strip() if sep else EXTRA_PLACEHOLDER))
    seen: set[str] = set()
    unique = []
    for original, placeholder in pairs:
        if len(original) >= MIN_REDACTION_LENGTH and original not in seen:
            seen.add(original)
            unique.append((original, placeholder))
    return sorted(unique, key=lambda pair: -len(pair[0]))


def git_optional(root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def tracked_under(root: Path, spec: str) -> list[str]:
    """Files under ``spec`` (a file or a directory) in the tree at HEAD, in git's order. The
    tree, not the index: a staged file that is not committed is not part of any commit."""
    out = git(root, "ls-tree", "-r", "--name-only", "-z", "HEAD", "--", spec)
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
    redactions: dict[str, int] = field(default_factory=dict)

    def collect(self) -> None:
        identity = owner_identity(self.root)
        seen: set[str] = set()
        for bundle, specs in BUNDLES.items():
            members: list[str] = []
            for spec in specs:
                for rel in tracked_under(self.root, spec):
                    if rel in seen or (excluded(rel) and rel != spec):
                        continue
                    seen.add(rel)
                    content = git_bytes(self.root, "show", f"HEAD:{rel}")
                    try:
                        text = content.decode("utf-8")
                    except UnicodeDecodeError:
                        self.skipped_binary.append(rel)
                        continue
                    for original, placeholder in identity:
                        hits = text.count(original)
                        if hits:
                            text = text.replace(original, placeholder)
                            self.redactions[placeholder] = (
                                self.redactions.get(placeholder, 0) + hits
                            )
                    self.files[rel] = text.encode("utf-8")
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


def split_parts(packet: Packet, members: list[str], part_bytes: int) -> list[list[str]]:
    """Greedy split of a bundle's files into parts of at most ``part_bytes`` of content; a
    single file larger than the budget gets a part of its own."""
    parts: list[list[str]] = []
    current: list[str] = []
    size = 0
    for rel in members:
        length = len(packet.files[rel])
        if current and size + length > part_bytes:
            parts.append(current)
            current, size = [], 0
        current.append(rel)
        size += length
    if current:
        parts.append(current)
    return parts


def part_names(name: str, count: int) -> list[str]:
    return [f"{name}.md"] if count == 1 else [f"{name}-{i}.md" for i in range(1, count + 1)]


def render_bundle(name: str, packet: Packet, members: list[str], label: str) -> str:
    parts = [
        f"# {PROJECT} review packet, {label}\n",
        f"Commit `{packet.commit}`, built {packet.date}. Every file below is the committed "
        f"text at that commit, one section per file, every line prefixed with its line number; "
        f"fences use five backticks so the files' own fences stay intact.\n",
        "## Files in this part\n",
        *(f"- `{rel}`" for rel in members),
        "",
    ]
    for rel in members:
        lang = LANG.get(Path(rel).suffix, "text")
        text = packet.files[rel].decode("utf-8")
        numbered = "\n".join(
            f"{number:>5}  {line}" for number, line in enumerate(text.rstrip().splitlines(), 1)
        )
        parts.append(f"\n---\n\n## `{rel}`\n\n{FENCE}{lang}\n{numbered}\n{FENCE}\n")
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


def render_index(packet: Packet, placement: dict[str, str]) -> str:
    """Every packed path with the part that holds it: the retrieval index the README points at."""
    rows = [
        f"| `{rel}` | `{placement[rel]}` | {len(packet.files[rel]):,} |" for rel in packet.files
    ]
    return (
        "## File index\n\n"
        "Every file in the packet, the upload part that holds it, and its size in bytes. Inside a\n"
        "part, each file is one section headed by its path in backticks. The gate tests\n"
        "(`tests/gates/`) sit in the harness part, not the tests part.\n\n"
        "| Path | Part | Bytes |\n|---|---|---|\n" + "\n".join(rows) + "\n"
    )


def render_readme(
    packet: Packet, part_sizes: dict[str, int], part_files: dict[str, list[str]]
) -> str:
    dirty = (
        "\n> **Built from a dirty working tree** with `--allow-dirty`: the contents are the "
        "commit above, not the uncommitted edits.\n"
        if packet.dirty
        else ""
    )
    rows = "\n".join(
        f"| `{name}` | {size:,} | {size // 4:,} | {len(part_files[name])} |"
        for name, size in part_sizes.items()
    )
    skipped = "\n".join(f"- `{rel}`" for rel in packet.skipped_binary) or "- (none)"
    excluded_rules = "\n".join(f"- `{prefix}`" for prefix in EXCLUDED_PREFIXES)
    redacted = sum(packet.redactions.values())
    return f"""# {PROJECT} review packet: commit `{packet.commit[:12]}`, {packet.date}

This packet is the committed tree of a small personal system at one commit, assembled by
`tools/review_packet.py`. `MANIFEST.json` carries a sha256 for every file and one packet hash,
`{packet.packet_hash[:16]}…`, which the project's review register cites. The file index at
the end of this README maps every path to the upload part that holds it; use it before
searching, because the parts are large and a retrieval tool will not read them in order.
{dirty}
## What is and is not here, stated plainly

- The earlier project's own material (an unrelated system this project took lessons from) is
  excluded. Where these documents describe those lessons they do so in abstract terms, and
  they refer to a folder of redacted retrospectives and an archive under `~/` that are not in
  the packet; treat every such pointer as a dead link, not as missing context you must recover.
- One gate test, `tests/gates/test_no_imported_identifiers.py`, is withheld because its
  positive controls spell out the very identifiers it bans. The guards ledger row G35
  describes what it scans; `tests/gates/test_review_packet.py` imports it, which is why that
  import has no target here.
- Earlier reviews are recorded, not withheld: the dated reports are excluded, but the plan and
  the decisions log restate what was adopted from them and the authors' rulings, the register
  carries a verdict column, and about sixty test docstrings cite `round5-findings.json`, a
  panel file that is not tracked and not here. Treat every recorded conclusion as a claim
  under review.
- The owner's name, email address and its domain, account handle, and machine username are
  replaced by placeholders (`the owner`, `owner@example.invalid`, `example.invalid`,
  `the-owner`, `[user]`) everywhere, including inside code and paths; the manifest counts the
  substitutions per placeholder ({redacted:,} in total). The owner's first name remains, as
  the operator the documents address. Nothing else personal is here, and there are no
  secrets: the packet is built from tracked files only, and the tree's own gates refuse a
  committed secret.

## What the system is

{intent_paragraph(packet)}

## What you are asked to do

Read `01-QUERY.md` first; it is the brief. In one line: find what is wrong, what it would
cost, and how sure you are, citing files and lines, and say "cannot judge" where you lack the
context rather than guessing. `02-CLAIMS.md` lists the load-bearing claims with the test that
backs each; try to falsify them.

## Reading order

1. `01-QUERY.md`, then `02-CLAIMS.md`, then the file index at the end of this README.
2. The documents part(s): the working agreement (`CLAUDE.md`), the plan (its intent block
   first), the decisions log (settled negatives before proposing a lever), the status page,
   the test strategy, the runbook, the guards ledger, known issues, the review register, the
   sub-agent brief template, the learnings and insights, and the database schema.
3. The harness part(s): what enforces the working agreement: the hooks, the ratchet and
   code-health tools, the configs, and the gate tests under `tests/gates/`, which live here and
   not in the tests part.
4. The source part(s), then the tests part(s) (unit, database, services, end-to-end).

Two things a reader should know. Every line inside a file section carries its line number
in the left margin, the same number the file has in the repository: cite a finding by part,
path, that number, and the quoted line, so the owner can check it in seconds. And the dated
review reports are excluded, but the plan and the decisions log record what was adopted from
earlier reviews and the authors' rulings on them: treat every such recorded conclusion as a
claim under review, not as settled.

## Contents

| Part | Bytes | Tokens (about) | Files |
|---|---|---|---|
{rows}

The upload set is this README, the brief, the claims list, the parts, and `MANIFEST.json`. If
your tool caps an upload at ten files, leave out `MANIFEST.json`: it is the hash record for the
project's register, not review material.

Skipped because binary:

{skipped}

Excluded by rule (never part of a packet): secrets, data, fixtures, the earlier project's
material, the memory snapshot, and the dated review reports (the plan and the decisions log
still record what was adopted from them; see above). Two dated documents are included on
purpose because they are inputs to the design rather than verdicts on it: the research report
the collector's Reddit facts come from, and the collector design review that the deletion
predicates cite. The live configuration under `config/` is included; the secrets file is not.

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


def write_packet(
    packet: Packet, out: Path, with_tree: bool = True, part_bytes: int = PART_BYTES
) -> dict[str, object]:
    out.mkdir(parents=True, exist_ok=True)
    part_sizes: dict[str, int] = {}
    part_hashes: dict[str, str] = {}
    part_files: dict[str, list[str]] = {}
    placement: dict[str, str] = {}
    for name in BUNDLES:
        parts = split_parts(packet, packet.bundle_files[name], part_bytes)
        names = part_names(name, len(parts))
        for part_name, members in zip(names, parts, strict=True):
            label = f"bundle {name}" + (f", part {part_name}" if len(parts) > 1 else "")
            text = render_bundle(name, packet, members, label).encode("utf-8")
            (out / part_name).write_bytes(text)
            part_sizes[part_name] = len(text)
            part_hashes[part_name] = sha256(text)
            part_files[part_name] = members
            for rel in members:
                placement[rel] = part_name
    query = render_query(packet, head_text(packet.root, TEMPLATE, "query template"))
    (out / "01-QUERY.md").write_text(query, encoding="utf-8")
    (out / "02-CLAIMS.md").write_text(
        head_text(packet.root, CLAIMS, "claims list"), encoding="utf-8"
    )
    (out / "00-README.md").write_text(
        render_readme(packet, part_sizes, part_files) + "\n" + render_index(packet, placement),
        encoding="utf-8",
    )
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
                "name": part_name,
                "bytes": part_sizes[part_name],
                "sha256": part_hashes[part_name],
                "files": part_files[part_name],
            }
            for part_name in part_sizes
        ],
        "skipped_binary": packet.skipped_binary,
        "redactions": dict(sorted(packet.redactions.items())),
        "excluded_prefixes": list(EXCLUDED_PREFIXES),
    }
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def copy_upload_set(out: Path, dest: Path, manifest: dict[str, object]) -> list[str]:
    dest.mkdir(parents=True, exist_ok=True)
    bundles = manifest["bundles"]
    assert isinstance(bundles, list)
    names = [*UPLOAD_SET, *(str(bundle["name"]) for bundle in bundles)]
    for name in names:
        shutil.copy2(out / name, dest / name)
    return names


def build(
    root: Path, out: Path, *, allow_dirty: bool, with_tree: bool, part_bytes: int = PART_BYTES
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
    manifest = write_packet(packet, out, with_tree=with_tree, part_bytes=part_bytes)
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
        "--part-bytes",
        type=int,
        default=PART_BYTES,
        help="split a bundle into numbered parts above this many bytes of content",
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
    packet, manifest = build(
        root, out, allow_dirty=args.allow_dirty, with_tree=True, part_bytes=args.part_bytes
    )
    print(f"packet: {out}")
    print(f"commit: {packet.commit} ({'dirty tree' if packet.dirty else 'clean tree'})")
    print(f"packet sha256: {packet.packet_hash}")
    for bundle in manifest["bundles"]:  # type: ignore[union-attr]
        print(
            f"bundle {bundle['name']:<16} {bundle['bytes']:>9,} bytes  {len(bundle['files'])} files"
        )
    if packet.skipped_binary:
        print(f"skipped binary: {', '.join(packet.skipped_binary)}")
    total = sum(packet.redactions.values())
    print(f"redactions: {total} substitutions across {len(packet.redactions)} placeholders")
    dest: Path | None = args.copy_to
    if args.desktop:
        dest = Path.home() / "Desktop" / f"insightminer-review-packet-{stamp}"
    if dest is not None:
        names = copy_upload_set(out, dest, manifest)
        if args.with_tree:
            shutil.copytree(out / "tree", dest / "tree", dirs_exist_ok=True)
            names.append("tree/")
        print(f"copied to {dest}: {', '.join(names)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
