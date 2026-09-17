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

What is scanned: every tracked file whose extension is in
:data:`tools.private_terms.TEXT_SUFFIXES`. The one exclusion is
``docs/reference/earlier-project-retrospectives/``: those three files plus their index are the
earlier project's own documents, kept deliberately and redacted under their own
``REDACTION_NOTE.md``. The file set moved into ``tools/private_terms.py`` on 2026-09-17, where
the private-term check can read it too; a tool cannot import a test module, so the shared half
lives in the tool and this file imports it.

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

import json
import re
import subprocess
from collections.abc import Iterable
from pathlib import Path

import pytest
from tools.memory_snapshot import private_home
from tools.private_terms import (
    EXCLUDED_PREFIXES,
    NO_LIST,
    accept,
    accepted_path,
    check,
    line_hash,
    list_path,
    scannable,
    tracked_files,
)

ROOT = Path(__file__).resolve().parents[2]

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


def violations(root: Path, rel_paths: Iterable[str]) -> list[str]:
    """``file:line: rule: matched text`` for every hit under ``root``."""
    found: list[str] = []
    for rel in scannable(rel_paths):
        text = (root / rel).read_text(encoding="utf-8")
        for number, line in enumerate(text.splitlines(), start=1):
            found += [f"{rel}:{number}: {rule}: {hit}" for rule, hit in _line_hits(line)]
    return found


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
            "THREADDIGEST_DATA_DIR=/Users/[user]/repos/insightminer/data",
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


# ---------------------------------------------------------------------------- fixtures (2026-09-16)
# Widened on 2026-09-16 (the plan-version-two deep review, readiness seat F2): a fixture committed
# under tests/fixtures/ is permanent history, and a Reddit username or account id in it is another
# person's identifier, the class this gate exists for. Every capture is scrubbed on save by
# core.fixture_scrub; the hand-written synthetic set is invented by construction and exempt.

FIXTURE_ROOTS = ("tests/fixtures/", "tests/adapters/cassettes/")
HAND_WRITTEN = ("tests/fixtures/json/synthetic/",)
CASSETTE_AUTHOR = re.compile(r'"author":\s*"([^"]*)"')
CASSETTE_ID = re.compile(r"\bt2_[0-9a-z]+\b")


def fixture_violations(root: Path, rel_paths: Iterable[str]) -> list[str]:
    """Every author name or account id under the fixture roots that is neither kept nor
    synthetic, as ``path: value``; JSON is walked, a cassette is scanned as text."""
    from threaddigest.core import fixture_scrub as fs

    found: list[str] = []
    for rel in sorted(rel_paths):
        if not rel.startswith(FIXTURE_ROOTS) or rel.startswith(HAND_WRITTEN):
            continue
        path = root / rel
        if rel.endswith(".json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            found += [f"{rel}: {v}" for v in fs.offending_values(payload)]
        elif rel.endswith((".yaml", ".yml")):
            text = path.read_text(encoding="utf-8")
            names = [m for m in CASSETTE_AUTHOR.findall(text) if fs._needs_name(m)]
            ids = [m for m in CASSETTE_ID.findall(text) if not fs.SYNTHETIC_ID.match(m)]
            found += [f"{rel}: {v}" for v in names + ids]
    return found


def test_fixtures_carry_synthetic_authors_only() -> None:
    found = fixture_violations(ROOT, tracked_files(ROOT))
    assert not found, "real author names or ids in fixtures:\n" + "\n".join(found)


@pytest.mark.gate("G35")
def test_positive_control_a_real_author_in_a_fixture_is_red(tmp_path: Path) -> None:
    from threaddigest.core import fixture_scrub as fs

    raw = {"posts": [{"id": "x", "author": "a_real_person", "author_fullname": "t2_9zq8x"}]}
    capture = tmp_path / "tests" / "fixtures" / "json" / "captures" / "post.json"
    capture.parent.mkdir(parents=True)
    capture.write_text(json.dumps(raw), encoding="utf-8")
    cassette = tmp_path / "tests" / "adapters" / "cassettes" / "auth.yaml"
    cassette.parent.mkdir(parents=True)
    cassette.write_text(
        'body: \'{"author": "a_real_person", "author_fullname": "t2_9zq8x"}\'\n',
        encoding="utf-8",
    )
    synthetic = tmp_path / "tests" / "fixtures" / "json" / "synthetic" / "post.json"
    synthetic.parent.mkdir(parents=True)
    synthetic.write_text(json.dumps(raw), encoding="utf-8")
    rels = [
        "tests/fixtures/json/captures/post.json",
        "tests/adapters/cassettes/auth.yaml",
        "tests/fixtures/json/synthetic/post.json",
    ]
    assert fixture_violations(tmp_path, rels) == [
        "tests/adapters/cassettes/auth.yaml: a_real_person",
        "tests/adapters/cassettes/auth.yaml: t2_9zq8x",
        "tests/fixtures/json/captures/post.json: a_real_person",
        "tests/fixtures/json/captures/post.json: t2_9zq8x",
    ]
    # The scrubbed capture is green; the hand-written synthetic set is exempt by construction.
    capture.write_text(json.dumps(fs.scrub(raw)), encoding="utf-8")
    assert fixture_violations(tmp_path, rels[:1]) == []


# ------------------------------------------------------- the private term list (2026-09-17)
# Widened 2026-09-17: a term on the operator's private list was found in tracked text; nothing
# mechanical had been checking for it. That half of the rule cannot be written down here: the
# terms are the operator's and this repository is public, so the list lives in the private
# folder beside the memory snapshot, the scan is ``tools/private_terms.py``, and a finding
# names the pattern that matched by its ordinal in that list and never by its text. Every term
# planted below is invented for the test.
#
# Two readers, deliberately. Under pytest every ``THREADDIGEST_*`` variable is stripped by the
# data-directory fixture (``tests/conftest.py``), so this gate reads the tracked default home;
# the ``make check`` line runs the same check outside pytest, where a folder moved with
# ``THREADDIGEST_PRIVATE_DIR`` is honoured. With no folder at all -- CI, a fresh clone -- the
# check prints its note and passes, which is a visible state rather than a silent skip.

PLACEHOLDER_TERMS = "# invented for this test\n\nquokka-lantern\nnarwhal[- ]compass\n"


def _private(tmp_path: Path, name: str = "private", terms: str = PLACEHOLDER_TERMS) -> Path:
    """A private folder holding one term list."""
    home = tmp_path / name
    home.mkdir()
    list_path(home).write_text(terms, encoding="utf-8")
    return home


@pytest.mark.gate("G35")
def test_no_tracked_text_carries_a_private_term() -> None:
    found = check(ROOT, tracked_files(ROOT), private_home())
    assert not found, "private terms in tracked text:\n" + "\n".join(found)


@pytest.mark.gate("G35")
def test_positive_control_a_planted_private_term_is_red(tmp_path: Path) -> None:
    home = _private(tmp_path)
    body = "# s\n\nthe quokka-lantern note\nand the narwhal compass beside it\n"
    root, paths = _tree(tmp_path / "dirty", body)
    assert check(root, paths, home) == [
        "docs/SUSPECT.md:3: private term (pattern 1)",
        "docs/SUSPECT.md:4: private term (pattern 2)",
    ]


@pytest.mark.gate("G35")
def test_positive_control_the_same_tree_without_a_private_term_is_green(tmp_path: Path) -> None:
    home = _private(tmp_path)
    root, paths = _tree(tmp_path / "clean", "# s\n\nthe main session decides.\n")
    assert check(root, paths, home) == []


@pytest.mark.gate("G35")
def test_positive_control_an_accepted_line_is_green_until_it_is_edited(tmp_path: Path) -> None:
    """An acceptance is of the line's content under one path: it travels, it does not survive
    an edit, and it says nothing about the same line anywhere else."""
    home = _private(tmp_path)
    offending = "the quokka-lantern note"
    root, paths = _tree(tmp_path / "accepted", f"# s\n\n{offending}\n")
    suspect = root / "docs" / "SUSPECT.md"
    accepted_path(home).write_text(f"docs/SUSPECT.md\t{line_hash(offending)}\n", encoding="utf-8")
    assert check(root, paths, home) == []

    suspect.write_text(f"# s\n\nprose added above it\n\n{offending}\n", encoding="utf-8")
    assert check(root, paths, home) == [], "a line that moved lost its acceptance"

    suspect.write_text(f"# s\n\n{offending}, revised\n", encoding="utf-8")
    assert check(root, paths, home) == ["docs/SUSPECT.md:3: private term (pattern 1)"]

    (root / "docs" / "CLEAN.md").write_text(f"# c\n\n{offending}\n", encoding="utf-8")
    assert check(root, paths, home) == [
        "docs/CLEAN.md:3: private term (pattern 1)",
        "docs/SUSPECT.md:3: private term (pattern 1)",
    ]


@pytest.mark.gate("G35")
def test_positive_control_accept_writes_the_hash_and_refuses_a_clean_line(tmp_path: Path) -> None:
    home = _private(tmp_path)
    offending = "the quokka-lantern note"
    root, paths = _tree(tmp_path / "accepting", f"# s\n\n{offending}\n")
    with pytest.raises(SystemExit, match="matches no pattern"):
        accept(root, home, "docs/CLEAN.md:3")
    entry = accept(root, home, "docs/SUSPECT.md:3")
    assert entry == f"docs/SUSPECT.md\t{line_hash(offending)}"
    assert check(root, paths, home) == []


@pytest.mark.gate("G35")
def test_positive_control_no_list_checks_nothing_and_says_so(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The CI and fresh-clone case: no private folder, so nothing is checked and it is said."""
    root, paths = _tree(tmp_path / "unchecked", "# s\n\nthe quokka-lantern note\n")
    absent = tmp_path / "no-private-folder"
    assert check(root, paths, absent) == []
    assert capsys.readouterr().out.strip() == NO_LIST.format(path=list_path(absent))


@pytest.mark.gate("G35")
def test_positive_control_a_list_that_cannot_be_used_is_red(tmp_path: Path) -> None:
    """A list that is present and unusable fails; only an absent list is green."""
    root, paths = _tree(tmp_path / "broken", "# s\n\nthe quokka-lantern note\n")
    uncompilable = _private(tmp_path, "uncompilable", "quokka-[lantern\n")
    with pytest.raises(SystemExit, match="not a valid regular expression"):
        check(root, paths, uncompilable)
    empty = _private(tmp_path, "empty", "# every line a comment\n")
    with pytest.raises(SystemExit, match="holds no pattern"):
        check(root, paths, empty)
    malformed = _private(tmp_path, "malformed")
    accepted_path(malformed).write_text("docs/SUSPECT.md no-tab-no-hash\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="path<TAB>sha1hex"):
        check(root, paths, malformed)
