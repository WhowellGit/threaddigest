"""G35: no imported identifiers, attribution trailers, or model names in tracked text.

Birth incident (2026-09-13): Wes's two standing rules were being kept by memory alone. The
first is that nothing project-specific may be carried in from his earlier data project -- the
worry is conflation as much as confidentiality, so that project's codenames, register ids,
script names, machine names, channels, tickets and people must not appear here at all. The
second is that a commit or document must not carry an attribution trailer or name the model
that wrote it. A sweep on 2026-09-13 rewrote the documents (its measured count is in
``docs/runbook/GUARDS.md`` G35); a rule kept by a sweep alone comes back, so it is kept by this
test instead. Widened 2026-09-14: a lowercase codename had survived inside a quoted transcript
line, and the company's name had survived inside an imported lint name, so the codename rule is
case-insensitive and the company name is allowed only in its public-product sense.

What is scanned: every tracked file whose extension is in :data:`TEXT_SUFFIXES`. The one
exclusion is ``docs/reference/earlier-project-retrospectives/``: those three files plus their
index are the earlier project's own documents, kept deliberately and redacted under their own
``REDACTION_NOTE.md``.

Carve-outs, each narrow and reasoned:

* **Loopback addresses.** The web UI binds ``127.0.0.1``; the rule is aimed at other people's
  machines, so the loopback block and the unspecified address are allowed and every other
  literal IPv4 address fails.
* **Reserved and own-identity e-mail.** Documentation addresses in the RFC 2606 / RFC 6761
  reserved domains are allowed, as is the project's own recorded git identity (``D-23``).
  Any other address fails.

Every banned literal in this file -- in the patterns and in the planted fixtures alike -- is
broken up, either by a redundant character class in a regex (``X[Y]Z`` for ``XYZ``) or by
string concatenation in a fixture, so that this file does not match its own rules. A regex
engine treats the two spellings identically. Excluding this file from its own scan would be
simpler and would leave a hole exactly where someone would hide something.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

TEXT_SUFFIXES = frozenset(
    {".md", ".py", ".toml", ".yaml", ".yml", ".txt", ".json", ".cfg", ".ini", ".sh", ".mako"}
)
EXCLUDED_PREFIXES = ("docs/reference/earlier-project-retrospectives/",)

# --------------------------------------------------------------------------- carve-outs

#: Loopback (127.0.0.0/8) and the unspecified address; everything else is a real host.
ALLOWED_IPV4 = re.compile(r"\A(?:127\.\d{1,3}\.\d{1,3}\.\d{1,3}|0\.0\.0\.0)\Z")

#: RFC 2606 / RFC 6761 reserved names, safe in documentation and fixtures forever.
RESERVED_EMAIL_DOMAINS = (".invalid", ".test", ".example", ".localhost", "example.com")

#: The project's own git identity, recorded as D-23 in docs/decisions/DECISIONS.md.
ALLOWED_EMAILS = frozenset({"wes@weshowell.com"})

#: The operator's own home, and the placeholder used in templates.
ALLOWED_HOME_USERS = frozenset({"wesmax", "[user]"})

# --------------------------------------------------------------------------- rules

EMAIL = re.compile(
    r"(?<![\w.\\])[A-Za-z0-9._%+-]{2,}@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,24}\b"
)
IPV4 = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
HOME_PATH = re.compile(r"/Users/(\[user\]|[A-Za-z0-9._-]+)")

Rule = tuple[str, re.Pattern[str]]

RULES: tuple[Rule, ...] = (
    (
        "attribution trailer",
        re.compile(r"Co-Authored[-]By|Generated with \[Claude Code\]", re.IGNORECASE),
    ),
    ("model name (write “the main session”)", re.compile(r"\b[Ff]abl[e]\b")),
    (
        "earlier project's codename",
        # The org codename is matched in any case and with any suffix, because it also prefixes
        # that project's service-account names; the other three stay whole-word and upper-case
        # (their lower-case forms are ordinary technical words).
        re.compile(r"\b(?:D[P]I|N[F]S|D[Q]S)\b|\b[Dd][Vv][Aa]\w*"),
    ),
    (
        "company name outside its public-product sense",
        # The product this project monitors is made by a company whose name is also the earlier
        # project's employer. The name is allowed only when it names a public product, a subreddit
        # (``r/…``), or a quoted fixture string; "its internal workflow" and imported identifiers
        # that embed the name are red.
        re.compile(
            r"(?<![A-Za-z])(?<!r/)(?<![\"'])ad[o]be"
            r"(?!(?:'s)?[\s-]*(?:premiere|after\s+effects|media\s+encoder|creative\s+cloud|"
            r"photoshop|audition|lightroom|firefly|acrobat|fonts|stock))",
            re.IGNORECASE,
        ),
    ),
    ("earlier project's register id", re.compile(r"\bK[I] #\d+|\bS[F] #\d+|\bAD[R]-\d{3}")),
    ("ticket key", re.compile(r"\b[A-Z]{3,8}-\d{4,8}\b")),
    ("Slack channel id", re.compile(r"\bC0[A-Z0-9]{8,}\b")),
)


def _allowed(rule: str, hit: str) -> bool:
    """Carve-outs are applied per rule; every other hit fails."""
    if rule == "e-mail address":
        return hit in ALLOWED_EMAILS or hit.lower().endswith(RESERVED_EMAIL_DOMAINS)
    if rule == "IPv4 address":
        return bool(ALLOWED_IPV4.match(hit))
    return False


def _line_hits(line: str) -> list[tuple[str, str]]:
    """Every ``(rule, matched text)`` on one line, carve-outs already applied."""
    hits = [(rule, m.group(0)) for rule, pattern in RULES for m in pattern.finditer(line)]
    hits += [("e-mail address", m.group(0)) for m in EMAIL.finditer(line)]
    hits += [("IPv4 address", m.group(0)) for m in IPV4.finditer(line)]
    hits += [
        ("another user's home path", m.group(0))
        for m in HOME_PATH.finditer(line)
        if m.group(1) not in ALLOWED_HOME_USERS
    ]
    return [(rule, hit) for rule, hit in hits if not _allowed(rule, hit)]


def scannable(rel_paths: Iterable[str]) -> list[str]:
    """The subset of ``rel_paths`` this gate reads: text suffixes, retrospectives excluded."""
    return sorted(
        rel
        for rel in rel_paths
        if Path(rel).suffix in TEXT_SUFFIXES and not rel.startswith(EXCLUDED_PREFIXES)
    )


def violations(root: Path, rel_paths: Iterable[str]) -> list[str]:
    """``file:line: rule: matched text`` for every hit under ``root``."""
    found: list[str] = []
    for rel in scannable(rel_paths):
        text = (root / rel).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            found += [f"{rel}:{number}: {rule}: {hit}" for rule, hit in _line_hits(line)]
    return found


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


@pytest.mark.gate
def test_positive_control_an_untracked_file_is_scanned(tmp_path: Path) -> None:
    """An untracked, non-ignored file must be in the scan set before it is ever added."""
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, timeout=60)
    (tmp_path / "note.md").write_text("draft\n", encoding="utf-8")
    (tmp_path / ".gitignore").write_text("ignored.md\n", encoding="utf-8")
    (tmp_path / "ignored.md").write_text("draft\n", encoding="utf-8")
    listed = tracked_files(tmp_path)
    assert "note.md" in listed and ".gitignore" in listed
    assert "ignored.md" not in listed


# --------------------------------------------------------------------------- the gate


def test_the_gate_scans_a_plausible_share_of_the_repo() -> None:
    """A scan that silently matched nothing would pass forever; pin that it reads the repo."""
    scanned = scannable(tracked_files(ROOT))
    assert len(scanned) > 100, f"only {len(scanned)} files scanned; the file filter is wrong"
    assert "CLAUDE.md" in scanned and "docs/PLAN.md" in scanned
    assert not any(p.startswith(EXCLUDED_PREFIXES) for p in scanned)


def test_no_tracked_text_carries_an_imported_identifier() -> None:
    found = violations(ROOT, tracked_files(ROOT))
    assert not found, "imported identifiers in tracked text:\n" + "\n".join(found)


# --------------------------------------------------------------------------- positive controls

#: One line per rule, so every rule is proven able to go red. Assembled at runtime for the
#: same reason the patterns carry a redundant character class: this file must not trip its
#: own gate.
PLANTED: tuple[str, ...] = (
    "Co-Authored" + "-By: Someone <someone@" + "elsewhere.example.org>",
    "Generated with [" + "Claude Code]",
    "the main session runs on " + "Fab" + "le",
    "the collector was called " + "NF" + "S and the store " + "DQ" + "S",
    "the org was " + "dv" + "a and its bot was " + "dv" + "axbot",
    "the company's internal workflow at " + "Ado" + "be",
    "the earlier lint scalar_" + "ado" + "be_lint",
    "see " + "KI" + " #226 and " + "AD" + "R-064",
    "tracked as " + "PROJ" + "-12345",
    "posted in " + "C01" + "ABCDEF23",
    "mail " + "someone@" + "other-company.com",
    "the box at " + "192.168." + "1.50",
    "/Users/" + "someone-else/repos/thing",
)


def _tree(root: Path, body: str) -> tuple[Path, list[str]]:
    """A miniature repo: one clean file, one file holding ``body``."""
    root.mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "docs" / "CLEAN.md").write_text("# clean\n\nthe main session decides.\n", "utf-8")
    (root / "docs" / "SUSPECT.md").write_text(body, encoding="utf-8")
    (root / "notes.bin").write_text("\n".join(PLANTED), encoding="utf-8")  # wrong suffix
    return root, ["docs/CLEAN.md", "docs/SUSPECT.md", "notes.bin"]


@pytest.mark.gate("G35")
def test_positive_control_a_planted_identifier_is_red(tmp_path: Path) -> None:
    root, paths = _tree(tmp_path / "dirty", "# s\n\n" + "\n".join(PLANTED) + "\n")
    found = violations(root, paths)
    assert len(found) >= len(PLANTED), "some planted line went unseen:\n" + "\n".join(found)
    assert all(f.startswith("docs/SUSPECT.md:") for f in found), found
    rules = {f.split(": ", 1)[1].split(":")[0] for f in found}
    assert rules == {rule for rule, _ in RULES} | {
        "e-mail address",
        "IPv4 address",
        "another user's home path",
    }, rules


@pytest.mark.gate("G35")
def test_positive_control_the_same_tree_without_the_violation_is_green(tmp_path: Path) -> None:
    root, paths = _tree(tmp_path / "clean", "# s\n\nthe earlier project's fix log.\n")
    assert violations(root, paths) == []


@pytest.mark.gate("G35")
def test_positive_control_the_carve_outs_are_narrow(tmp_path: Path) -> None:
    """The allowed forms stay green and their near neighbours go red."""
    allowed = "\n".join(
        [
            "bind 127.0.0.1:8765 and 0.0.0.0",
            "git identity Wes Howell <wes@weshowell.com>",
            "GIT_AUTHOR_EMAIL=ratchet-test@example.invalid",
            "INSIGHTMINER_DATA_DIR=/Users/[user]/repos/insightminer/data",
            "/Users/wesmax/repos/insightminer",
            "the primary Adobe Premiere Pro community; Adobe's After Effects; Adobe Media Encoder",
            "r/adobe is a public subreddit",
            'names=["premiere", "adobe"]',
            "an advance, advanced, and advantage (no codename inside ordinary words)",
        ]
    )
    root, paths = _tree(tmp_path / "edge", f"# s\n\n{allowed}\n")
    assert violations(root, paths) == []

    near = "\n".join(
        [
            "bind " + "10.0." + "0.5",  # a real host, not loopback
            "mail " + "someone@" + "weshowell.com",  # right domain, not the recorded identity
            "/Users/" + "other/repos",  # neither the operator nor the placeholder
            "the " + "Ado" + "be data sources of the earlier project",  # the company, not a product
            "the org codename in lower case: " + "dv" + "a",
        ]
    )
    other, other_paths = _tree(tmp_path / "near", f"# s\n\n{near}\n")
    assert len(violations(other, other_paths)) == 5
