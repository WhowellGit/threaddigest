#!/usr/bin/env python3
"""The document contract: purpose, update policy, mirrors, and the checks that keep them honest.

Wes's ask (2026-09-15): the earlier project's reference corpus grew by ad-hoc requests, agents
appended rather than rewrote, dated annotations piled up, and nothing tied a changed fact to the
documents that repeated it. This tool makes the writing side mechanical, the way the routing
gates made the reading side mechanical. What it checks, and honestly what it does not:

- **Contract.** Every living document under ``docs/`` (everything except ``reference/``) opens with
  YAML front matter naming its ``purpose``, its ``update-policy`` from a fixed vocabulary, the
  documents it ``mirrors`` (paths that must exist; mirroring between living documents must be
  declared from both sides), and, for the policies that are rewritten, the milestone it was
  ``verified-at``. The mirror list is a declaration the sweep reads; the tool does not compare a
  document's text with its mirrors, the live-facts table does that for the facts it lists.
- **Append-only by the diff, against the branch base.** A document declared ``append-only`` may
  gain lines anywhere and may carry a dated parenthetical inserted into an existing line, but no
  line committed at the merge base with ``main`` may disappear, move, or change otherwise. The
  baseline is the merge base, not ``HEAD``, so committing a deletion does not launder it. The
  policy that governs the diff is the one declared at the base, so a document cannot exempt
  itself by changing its own declaration. Sections named in ``exempt-sections`` are outside the
  diff (a table column filled at milestones).
- **Records are added, never edited.** Under ``docs/reference/`` a file that existed at the base
  must be byte-identical, except the review register (append-only) and the templates (reviewed
  like code).
- **Accretion.** Dated annotations in the prose of a prune-stale, versioned, or rewritten document
  (parentheticals, brackets, dash-delimited asides; table rows excluded, because the registers
  date their rows by design) are counted into a ratchet ceiling (``.ratchets/docs.txt``). This is a
  pressure, not a proof: a reshaped annotation escapes it, and the milestone pass reads the count.
- **Milestone lag.** The status page's front matter names the current milestone; a prune-stale or
  versioned document may lag it by at most one and may not be stamped ahead of it.
- **Dangling references.** Every backticked or linked ``*.md`` path carrying a directory, in a
  rewritten document or the working agreement, resolves to a file. A bare file name is not judged.
- **Live facts.** The machine-read table in the decisions log must exist, parse, and hold at least
  one row; every mirror must contain the literal (outside code fences and comments); a
  configuration, code, or file home must agree with the literal.

Usage: ``--check`` (exit 1 with every problem), ``--write PATH`` (the JSON report the ratchet
reads), ``--report`` (print the report); ``--write --check`` is what ``make check`` runs. The gate
is ``tests/gates/test_doc_policy.py``.
"""

from __future__ import annotations

import argparse
import importlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
DOCS = Path("docs")
DECISIONS = DOCS / "decisions" / "DECISIONS.md"
STATUS = DOCS / "recent" / "STATUS.md"
WORKING_AGREEMENT = Path("CLAUDE.md")
REPORT = Path(".build") / "doc_policy.json"
REFERENCE = "reference/"
REFERENCE_APPEND_ONLY = ("reference/reviews/REGISTER.md",)
REFERENCE_EDITABLE = ("reference/reviews/templates/",)

POLICIES = ("append-only", "prune-stale", "rewritten", "versioned")
LAG_POLICIES = ("prune-stale", "versioned")
ACCRETION_POLICIES = ("prune-stale", "versioned", "rewritten")
MILESTONES = ("D0", "M0", "M1a-A", "M1a-B", "M1b", "M1c", "M1d", "M2", "M3", "M4", "MB", "M5")
MAX_MILESTONE_LAG = 1
FACTS_SECTION = "## Live facts (machine-read)"

FRONT = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
DATE = r"(?<![-/_\w])20\d\d-\d\d-\d\d(?![-\w])"
#: A prose aside: a parenthetical (one nested level allowed), a bracket, or a dash-delimited
#: clause. An aside is an annotation when it carries a date that is not part of a path or name.
ASIDE = re.compile(r"\((?:[^()]|\([^()]*\))*\)|\[[^\[\]]*\]|[—–][^—–]*[—–]")
PARENTHETICAL = re.compile(r"\s*\*?\((?:[^()]|\([^()]*\))*\)\*?")
DATE_RE = re.compile(DATE)


def dated_asides(line: str) -> list[str]:
    return [m.group(0) for m in ASIDE.finditer(line) if DATE_RE.search(m.group(0))]


def _without_dated_parentheticals(line: str) -> str:
    return PARENTHETICAL.sub(lambda m: "" if DATE_RE.search(m.group(0)) else m.group(0), line)


DOC_TOKEN = re.compile(r"`([A-Za-z0-9_./-]+\.md)`|\]\(([A-Za-z0-9_./-]+\.md)\)")
FACT_ROW = re.compile(r"^\|\s*(F-\d+)\s*\|([^|]*)\|([^|]*)\|\s*`([^`]*)`\s*\|([^|]*)\|\s*$")
FACT_LIKE = re.compile(r"^\|\s*F-\d+\s*\|")
BACKTICKED = re.compile(r"`([^`]+)`")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
FENCE = re.compile(r"^(```|~~~)")


# ------------------------------------------------------------------------- front matter


def front_matter(text: str) -> dict[str, object] | None:
    """The parsed front matter, ``{}`` when the block is empty, ``None`` when there is none."""
    m = FRONT.match(text)
    if m is None:
        return None
    try:
        data = yaml.safe_load(m.group(1)) or {}
    except yaml.YAMLError:
        return None
    return data if isinstance(data, dict) else None


def strip_front_matter(text: str) -> str:
    return FRONT.sub("", text, count=1)


def prose_only(text: str) -> str:
    """The text with HTML comments and fenced code removed, for searches that mean prose."""
    lines: list[str] = []
    in_code = False
    for line in HTML_COMMENT.sub("", text).splitlines():
        if FENCE.match(line):
            in_code = not in_code
            continue
        if not in_code:
            lines.append(line)
    return "\n".join(lines)


def living_documents(root: Path) -> list[Path]:
    docs = root / DOCS
    return sorted(
        p for p in docs.rglob("*.md") if not p.relative_to(docs).as_posix().startswith(REFERENCE)
    )


def _rel(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


def _policy(data: dict[str, object] | None) -> str | None:
    value = (data or {}).get("update-policy")
    return value if isinstance(value, str) else None


def contract_problems(root: Path, path: Path, declared: dict[str, dict[str, object]]) -> list[str]:
    """Why one document's front matter fails the contract; empty when it holds."""
    rel = _rel(root, path)
    data = front_matter(path.read_text(encoding="utf-8"))
    if data is None:
        return [f"{rel}: no front matter (purpose, update-policy, mirrors, verified-at)"]
    found: list[str] = []
    purpose = data.get("purpose")
    if not isinstance(purpose, str) or not purpose.strip():
        found.append(f"{rel}: purpose missing")
    policy = _policy(data)
    if policy not in POLICIES:
        found.append(f"{rel}: update-policy {policy!r} not one of {', '.join(POLICIES)}")
    mirrors = data.get("mirrors", [])
    if not isinstance(mirrors, list):
        found.append(f"{rel}: mirrors must be a list of paths")
    else:
        for m in mirrors:
            if not isinstance(m, str) or not (root / m).is_file():
                found.append(f"{rel}: mirror {m!r} does not exist")
            elif m in declared and rel not in (declared[m].get("mirrors") or []):
                found.append(f"{rel}: declares {m} as a mirror, which does not declare it back")
    verified = data.get("verified-at")
    if policy in LAG_POLICIES and verified not in MILESTONES:
        found.append(f"{rel}: verified-at {verified!r} not one of {', '.join(MILESTONES)}")
    elif verified is not None and verified not in MILESTONES:
        found.append(f"{rel}: verified-at {verified!r} not one of {', '.join(MILESTONES)}")
    if policy == "rewritten" and data.get("milestone") not in MILESTONES:
        found.append(f"{rel}: a rewritten document names the current milestone")
    return found


# --------------------------------------------------------------------------- append-only


def _git(root: Path, *args: str) -> str | None:
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=False, timeout=60
    )
    return proc.stdout if proc.returncode == 0 else None


def baseline_ref(root: Path) -> str | None:
    """The merge base with ``main`` when it exists, else ``HEAD``; ``None`` outside a repository."""
    if _git(root, "rev-parse", "--verify", "HEAD") is None:
        return None
    base = _git(root, "merge-base", "HEAD", "main")
    return base.strip() if base else "HEAD"


def base_text(root: Path, ref: str, rel: str) -> str | None:
    """The file at the baseline, or ``None`` when it did not exist there."""
    return _git(root, "show", f"{ref}:{rel}")


def _norm(line: str) -> str:
    """A line with its dated parentheticals removed and its spacing collapsed."""
    return " ".join(_without_dated_parentheticals(line).split())


def _exempt_ranges(text: str, headings: list[str]) -> set[int]:
    """Line numbers (1-based) inside sections whose heading line starts with an exempt prefix."""
    exempt: set[int] = set()
    level = 0
    for number, line in enumerate(text.splitlines(), start=1):
        m = re.match(r"^(#{1,6})\s+", line)
        if m:
            depth = len(m.group(1))
            if level and depth <= level:
                level = 0
            if not level and any(line.startswith(h) for h in headings):
                level = depth
        if level:
            exempt.add(number)
    return exempt


def append_only_violations(
    old: str, new: str, rel: str, exempt_sections: list[str] | None = None
) -> list[str]:
    """Every baseline line that the new text does not keep, in order, with at most a dated
    parenthetical inserted or a suffix appended; a moved, hidden, or rewritten line is a loss."""
    exempt = _exempt_ranges(old, exempt_sections or [])
    new_lines = [line.rstrip() for line in HTML_COMMENT.sub("", new).splitlines()]
    found: list[str] = []
    cursor = 0
    for number, raw in enumerate(old.splitlines(), start=1):
        line = raw.rstrip()
        if not line.strip() or number in exempt:
            continue
        target = _norm(line)
        hit = next(
            (
                i
                for i in range(cursor, len(new_lines))
                if new_lines[i] == line
                or new_lines[i].startswith(line)
                or _norm(new_lines[i]) == target
                or _norm(new_lines[i]).startswith(target)
            ),
            None,
        )
        if hit is None:
            found.append(f"{rel}:{number}: append-only document lost a line: {line[:80]!r}")
        else:
            cursor = hit + 1
    return found


def append_only_problems(root: Path, ref: str | None) -> list[str]:
    """The diff check for every append-only document and every reference record."""
    if ref is None:
        return ["append-only baseline unavailable: not a git repository"]
    found: list[str] = []
    for path in living_documents(root):
        rel = _rel(root, path)
        new = path.read_text(encoding="utf-8")
        old = base_text(root, ref, rel)
        if old is None:
            continue  # new on this branch
        old_data = front_matter(old)
        old_policy = _policy(old_data) or _policy(front_matter(new))
        if old_policy != "append-only":
            continue
        if _policy(front_matter(new)) != "append-only":
            found.append(f"{rel}: append-only at the base; the policy may not be changed in place")
        exempt = (old_data or {}).get("exempt-sections") or []
        found += append_only_violations(old, new, rel, [str(h) for h in exempt])
    reference = root / DOCS / "reference"
    for path in sorted(reference.rglob("*")) if reference.is_dir() else []:
        if not path.is_file():
            continue
        rel = _rel(root, path)
        short = path.relative_to(root / DOCS).as_posix()
        if short.startswith(REFERENCE_EDITABLE):
            continue
        old = base_text(root, ref, rel)
        if old is None:
            continue
        new = path.read_text(encoding="utf-8") if path.suffix == ".md" else path.read_bytes().hex()
        if short in REFERENCE_APPEND_ONLY:
            found += append_only_violations(old, new, rel)
        elif old != new:
            found.append(f"{rel}: a reference record was edited; records are added, never edited")
    return found


# ------------------------------------------------------------------------------ accretion


def dated_annotations(text: str) -> list[tuple[int, str]]:
    """``(line, snippet)`` for every dated annotation in prose: outside front matter, fences,
    and table rows (the registers date their rows by design)."""
    found: list[tuple[int, str]] = []
    in_code = False
    body = strip_front_matter(text)
    skipped = text[: len(text) - len(body)].count("\n")
    for number, line in enumerate(body.splitlines(), start=skipped + 1):
        if FENCE.match(line):
            in_code = not in_code
            continue
        if in_code or line.lstrip().startswith("|"):
            continue
        found += [(number, aside[:60]) for aside in dated_asides(line)]
    return found


# ------------------------------------------------------------------------- milestone lag


def current_milestone(root: Path) -> str | None:
    if not (root / STATUS).is_file():
        return None
    value = (front_matter((root / STATUS).read_text(encoding="utf-8")) or {}).get("milestone")
    return value if isinstance(value, str) and value in MILESTONES else None


def milestone_lag_problems(root: Path) -> list[str]:
    current = current_milestone(root)
    if current is None:
        return [f"{STATUS.as_posix()}: front matter names no current milestone"]
    found: list[str] = []
    for path in living_documents(root):
        data = front_matter(path.read_text(encoding="utf-8")) or {}
        if _policy(data) not in LAG_POLICIES:
            continue
        verified = data.get("verified-at")
        if verified not in MILESTONES:
            continue  # the contract check reports it
        lag = MILESTONES.index(current) - MILESTONES.index(str(verified))
        if lag > MAX_MILESTONE_LAG:
            found.append(
                f"{_rel(root, path)}: verified at {verified}, the status page is at {current}: "
                f"re-read and rewrite or re-verify it (lag {lag}, allowed {MAX_MILESTONE_LAG})"
            )
        elif lag < 0:
            found.append(
                f"{_rel(root, path)}: verified at {verified}, ahead of the status page ({current})"
            )
    return found


# ---------------------------------------------------------------------- dangling references


def _resolves(root: Path, source: Path, token: str, corpus: list[str]) -> bool:
    """A path resolves at the root, under ``docs/``, beside the source, or as a suffix of any
    corpus file. A bare file name is not judged; a path with a directory must resolve."""
    if "<" in token or "*" in token:
        return True  # a template, not a path
    candidates = [root / token, root / DOCS / token, source.parent / token]
    if any(c.is_file() for c in candidates):
        return True
    if any(rel.endswith("/" + token) or rel == token for rel in corpus):
        return True
    return "/" not in token


def dangling_document_references(root: Path) -> list[str]:
    """Rewritten documents and the working agreement may not point at a document that is gone;
    append-only logs describe the past and may name files that no longer exist."""
    corpus = [p.relative_to(root / DOCS).as_posix() for p in (root / DOCS).rglob("*.md")]
    sources = [
        p
        for p in living_documents(root)
        if _policy(front_matter(p.read_text(encoding="utf-8"))) in ACCRETION_POLICIES
    ]
    sources.append(root / WORKING_AGREEMENT)
    found: list[str] = []
    for path in sources:
        if not path.is_file():
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            for a, b in DOC_TOKEN.findall(line):
                token = a or b
                if not _resolves(root, path, token, corpus):
                    found.append(f"{_rel(root, path)}:{number}: `{token}` does not exist")
    return found


# ------------------------------------------------------------------------------ live facts


@dataclass(frozen=True)
class Fact:
    fact_id: str
    fact: str
    home: str
    literal: str
    mirrors: tuple[str, ...] = field(default_factory=tuple)


def live_facts(decisions_text: str) -> tuple[list[Fact], list[str]]:
    """The parsed rows and the problems: a missing section, an empty table, an unparsed row."""
    if FACTS_SECTION not in decisions_text:
        return [], [f"{DECISIONS.as_posix()}: no {FACTS_SECTION!r} section"]
    section = decisions_text.split(FACTS_SECTION, 1)[1].split("\n## ", 1)[0]
    facts: list[Fact] = []
    problems: list[str] = []
    for line in section.splitlines():
        m = FACT_ROW.match(line)
        if m:
            mirrors = tuple(BACKTICKED.findall(m.group(5)))
            facts.append(
                Fact(m.group(1), m.group(2).strip(), m.group(3).strip(), m.group(4), mirrors)
            )
        elif FACT_LIKE.match(line):
            problems.append(f"{DECISIONS.as_posix()}: unparsed live-facts row: {line[:60]!r}")
    if not facts:
        problems.append(f"{DECISIONS.as_posix()}: the live-facts table has no rows")
    return facts, problems


def _home_value(root: Path, home: str) -> str | None:
    """The value the canonical home holds, or ``None`` when the home form needs no lookup."""
    kind, _, rest = home.partition(":")
    if kind == "text":
        return None
    if kind == "file":
        return (
            prose_only((root / rest).read_text(encoding="utf-8")) if (root / rest).is_file() else ""
        )
    if kind == "yaml":
        path, _, dotted = rest.partition(":")
        data = yaml.safe_load((root / path).read_text(encoding="utf-8"))
        for part in dotted.split("."):
            data = data[part] if isinstance(data, dict) and part in data else None
        return "" if data is None else str(data)
    if kind == "python":
        module, _, name = rest.partition(":")
        return str(getattr(importlib.import_module(module), name))
    msg = f"unknown fact home {home!r}"
    raise ValueError(msg)


def fact_problems(root: Path) -> list[str]:
    if not (root / DECISIONS).is_file():
        return [f"{DECISIONS.as_posix()}: missing"]
    facts, found = live_facts((root / DECISIONS).read_text(encoding="utf-8"))
    for f in facts:
        try:
            value = _home_value(root, f.home)
        except (ValueError, ImportError, AttributeError, OSError) as exc:
            found.append(f"{f.fact_id}: home {f.home!r} unreadable: {exc}")
            continue
        if value is not None and (
            (f.home.startswith("file:") and f.literal not in value)
            or (not f.home.startswith("file:") and value != f.literal)
        ):
            found.append(
                f"{f.fact_id}: home {f.home} holds {value!r}, the table says `{f.literal}`"
            )
        for mirror in f.mirrors:
            path = root / mirror
            if not path.is_file():
                found.append(f"{f.fact_id}: mirror {mirror} does not exist")
            elif (
                f.literal.casefold() not in prose_only(path.read_text(encoding="utf-8")).casefold()
            ):
                found.append(f"{f.fact_id}: mirror {mirror} does not state `{f.literal}`")
    return found


# ------------------------------------------------------------------------------- the report


def report(root: Path = ROOT) -> dict[str, object]:
    """Counts for the ratchet, hits for the summary, problems for the gate."""
    declared = {
        _rel(root, p): front_matter(p.read_text(encoding="utf-8")) or {}
        for p in living_documents(root)
    }
    problems: dict[str, list[str]] = {
        "contract": [],
        "append_only": append_only_problems(root, baseline_ref(root)),
        "milestone_lag": milestone_lag_problems(root),
        "dangling": dangling_document_references(root),
        "facts": fact_problems(root),
    }
    hits: list[str] = []
    total = 0
    for path in living_documents(root):
        rel = _rel(root, path)
        text = path.read_text(encoding="utf-8")
        problems["contract"] += contract_problems(root, path, declared)
        if _policy(front_matter(text)) in ACCRETION_POLICIES:
            annotations = dated_annotations(text)
            total += len(annotations)
            hits += [f"dated_annotation {rel}:{n} {snippet}" for n, snippet in annotations]
    return {"values": {"dated_annotations": total}, "hits": hits, "problems": problems}


def flat_problems(rep: dict[str, object]) -> list[str]:
    problems = rep["problems"]
    assert isinstance(problems, dict)
    return [line for group in problems.values() for line in group]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--write", type=Path, default=None, help="write the JSON report here")
    parser.add_argument("--report", action="store_true", help="print the JSON report")
    parser.add_argument("--check", action="store_true", help="exit 1 on any problem")
    args = parser.parse_args(argv)
    rep = report(args.root)
    if args.write is not None:
        args.write.parent.mkdir(parents=True, exist_ok=True)
        args.write.write_text(json.dumps(rep, indent=2) + "\n", encoding="utf-8")
    if args.report:
        print(json.dumps(rep, indent=2))
    found = flat_problems(rep)
    print("\n".join(found) if found else "doc policy: contracts, records, and facts hold")
    return 1 if (found and args.check) else 0


if __name__ == "__main__":
    sys.exit(main())
