"""G50: every commit on a review-required surface since the baseline has a review register row.

Birth incident (2026-09-14): the review-harness protocol says every review run is recorded in
``docs/reference/reviews/``. The planning-day panels were; the code panel that closed 24
findings on the collector build was not (its findings sat in the git-ignored build folder), and
33 of 62 commits on ``main`` touched a review-required surface with no way to tell which had
been reviewed. Written protocols drift where nothing checks them, so the register is
machine-read: a commit on ``main`` dated on or after the baseline that touches one of the
surfaces must be covered by a row's scope (a hash or a ``first..last`` range), and every record
a row cites must exist. Commits before the baseline are grandfathered on purpose; the first
external review takes them as a deliberate job, not as debt hidden by a rule.

What stays review: whether the review was adversarial enough, and whether a row written by the
same session that made the change is worth anything. The record's provider column and the
packet it saves beside it are what make that judgement possible.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest
from tools.ratchet import is_separator_row, split_row

ROOT = Path(__file__).resolve().parents[2]
REGISTER = Path("docs") / "reference" / "reviews" / "REGISTER.md"
BASELINE = "2026-09-15"
SURFACES: tuple[str, ...] = (
    "src/insightminer/db/migrations",
    "src/insightminer/services/scrub.py",
    "src/insightminer/core/deletion.py",
    "src/insightminer/db/repo.py",
    "tests/gates",
    ".ratchets",
    "tools/hooks",
    "CLAUDE.md",
    ".claude/settings.json",
)
SCOPE_COLUMN = "Scope"
RECORD_COLUMN = "Record"
HASH = re.compile(r"\b[0-9a-f]{7,40}\b")
RANGE = re.compile(r"\b([0-9a-f]{7,40})\.\.([0-9a-f]{7,40})\b")


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, check=True, timeout=60
    ).stdout


def rows(text: str) -> list[dict[str, str]]:
    """Every data row of the first table declaring the Scope and Record columns."""
    out: list[dict[str, str]] = []
    header: list[str] | None = None
    for line in text.splitlines():
        cells = split_row(line)
        if not cells:
            header = None
            continue
        if header is None:
            if SCOPE_COLUMN in cells and RECORD_COLUMN in cells:
                header = cells
            continue
        if is_separator_row(cells):
            continue
        out.append(dict(zip(header, cells, strict=False)))
    return out


def missing_records(root: Path, register_rows: list[dict[str, str]]) -> list[str]:
    folder = root / REGISTER.parent
    found: list[str] = []
    for row in register_rows:
        for name in re.findall(r"`([^`]+)`", row.get(RECORD_COLUMN, "")):
            if not (folder / name).is_file():
                found.append(name)
    return found


def required_commits(root: Path, baseline: str = BASELINE) -> list[tuple[str, str]]:
    """``(full hash, subject)`` for every ancestor of HEAD since ``baseline`` touching a surface."""
    out = git(root, "log", f"--since={baseline}", "--format=%H%x00%s", "--", *SURFACES)
    commits: list[tuple[str, str]] = []
    for line in out.splitlines():
        if line:
            full, subject = line.split("\x00", 1)
            commits.append((full, subject))
    return commits


def covered(root: Path, scope: str, full: str) -> bool:
    """True when ``scope`` names ``full`` directly or through a range it lies in."""
    for first, last in RANGE.findall(scope):
        try:  # ``first..last`` excludes ``first``; it is added back (a root has no parent)
            listed = git(root, "rev-list", f"{first}..{last}").split()
            listed.append(git(root, "rev-parse", f"{first}^{{commit}}").strip())
        except subprocess.CalledProcessError:
            continue
        if full in listed:
            return True
    bare = [h for h in HASH.findall(RANGE.sub(" ", scope)) if re.search(r"[a-f]", h)]
    return any(full.startswith(h) for h in bare)


def uncovered_commits(root: Path, register_rows: list[dict[str, str]]) -> list[str]:
    scopes = [row.get(SCOPE_COLUMN, "") for row in register_rows]
    return [
        f"{full[:7]} {subject}"
        for full, subject in required_commits(root)
        if not any(covered(root, scope, full) for scope in scopes)
    ]


# --------------------------------------------------------------------------- the gate


def test_every_record_the_register_cites_exists() -> None:
    register_rows = rows((ROOT / REGISTER).read_text(encoding="utf-8"))
    assert register_rows, "the register has no rows; its table is unreadable"
    found = missing_records(ROOT, register_rows)
    assert not found, "register rows cite records that do not exist:\n" + "\n".join(found)


def test_every_required_commit_since_the_baseline_has_a_review_row() -> None:
    register_rows = rows((ROOT / REGISTER).read_text(encoding="utf-8"))
    found = uncovered_commits(ROOT, register_rows)
    assert not found, (
        "commits on a review-required surface with no review register row:\n" + "\n".join(found)
    )


# --------------------------------------------------------------------------- positive controls


def _repo_with_dated_commits(root: Path) -> list[str]:
    """Three commits: one before the baseline on a surface, two after (surface, not surface)."""
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(root),
        "GIT_AUTHOR_NAME": "register-test",
        "GIT_AUTHOR_EMAIL": "register-test@example.invalid",
        "GIT_COMMITTER_NAME": "register-test",
        "GIT_COMMITTER_EMAIL": "register-test@example.invalid",
    }

    def commit(rel: str, date: str, subject: str) -> str:
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(subject + "\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=root, check=True, env=env, timeout=60)
        subprocess.run(
            ["git", "commit", "-q", "-m", subject],
            cwd=root,
            check=True,
            env={**env, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date},
            timeout=60,
        )
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
        ).stdout.strip()

    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env, timeout=60)
    old = commit("tests/gates/test_old.py", "2026-09-10T10:00:00", "before the baseline")
    new = commit("tests/gates/test_new.py", "2026-09-16T10:00:00", "gate after the baseline")
    other = commit("docs/x.md", "2026-09-17T10:00:00", "a document, not a surface")
    return [old, new, other]


@pytest.mark.gate("G50")
def test_positive_control_an_uncovered_surface_commit_is_red(tmp_path: Path) -> None:
    old, new, other = _repo_with_dated_commits(tmp_path)
    assert [h for h, _ in required_commits(tmp_path)] == [new], "only the dated surface commit"
    assert uncovered_commits(tmp_path, []) == [f"{new[:7]} gate after the baseline"]
    assert uncovered_commits(tmp_path, [{SCOPE_COLUMN: new[:7], RECORD_COLUMN: "`r.md`"}]) == []
    assert uncovered_commits(tmp_path, [{SCOPE_COLUMN: f"{old[:7]}..{other[:7]}"}]) == []
    assert uncovered_commits(tmp_path, [{SCOPE_COLUMN: "pre-baseline"}]) != []
    assert uncovered_commits(tmp_path, [{SCOPE_COLUMN: other[:7]}]) != [], (
        "a wrong hash covers nothing"
    )


@pytest.mark.gate("G50")
def test_positive_control_a_missing_record_is_red(tmp_path: Path) -> None:
    folder = tmp_path / REGISTER.parent
    folder.mkdir(parents=True)
    (folder / "real.md").write_text("# real\n", encoding="utf-8")
    register = "| Date | Trigger | Scope | Provider / tier | Verdict | Record |\n"
    register += "|---|---|---|---|---|---|\n"
    register += (
        "| d | t | abc1234 | p | v | `real.md` |\n| d | t | abc1234 | p | v | `ghost.md` |\n"
    )
    parsed = rows(register)
    assert len(parsed) == 2
    assert missing_records(tmp_path, parsed) == ["ghost.md"]
