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
from collections.abc import Mapping
from pathlib import Path

import pytest
from tools.hash_remap import load_remap, successors
from tools.ratchet import is_separator_row, split_row

ROOT = Path(__file__).resolve().parents[2]
REGISTER = Path("docs") / "reference" / "reviews" / "REGISTER.md"
BASELINE = "2026-09-15"
#: The ratchet files left this list on 2026-09-14 (Wes's ruling on the principal-engineer seat's
#: finding): they are already gated by their writer tool, the hook, and the three-way compare,
#: and keeping them here would have put a register row on most routine commits.
SURFACES: tuple[str, ...] = (
    "src/threaddigest/db/migrations",
    "src/threaddigest/services/scrub.py",
    "src/threaddigest/core/deletion.py",
    "src/threaddigest/db/repo.py",
    "tests/gates",
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
    """``(full hash, subject)`` for every ancestor of HEAD dated on or after ``baseline``.

    The date is read off each commit and compared here rather than handed to ``git log --since``.
    Git's approximate date parser fills the fields a bare date leaves out from the current clock,
    so ``--since=2026-09-15`` means *that date at the hour the suite happens to run*, in whatever
    timezone the host is set to. The cutoff slid through the day and moved with the machine, and
    six commits on review-required surfaces were invisible on the owner's Mac while the Linux
    runner demanded rows for them (KI-035). ``%cs`` is the committer date in the commit's own
    recorded zone -- the date a reader of ``git log`` sees -- and comparing two ``YYYY-MM-DD``
    strings has no clock in it at all.
    """
    out = git(root, "log", "--format=%H%x00%cs%x00%s", "--", *SURFACES)
    commits: list[tuple[str, str]] = []
    for line in out.splitlines():
        if line:
            full, dated, subject = line.split("\x00", 2)
            if dated >= baseline:
                commits.append((full, subject))
    return commits


def _through_remap(remap: Mapping[str, str], sha: str) -> list[str]:
    """``sha`` and every hash a recorded history rewrite turned it into."""
    return [sha, *successors(remap, sha)]


def covered(root: Path, scope: str, full: str, remap: Mapping[str, str] | None = None) -> bool:
    """True when ``scope`` names ``full`` directly or through a range it lies in.

    A scope is written once and never edited (the register is append-only), so after a history
    rewrite its hashes name commits that no longer exist. The rewrite records what each commit
    became (``docs/reference/hash-remap-*.tsv``) and both a bare hash and each end of a range
    are followed through that map. A scope that names no commit, before or after the map, still
    covers nothing.

    The two ends are followed independently, so the pairs tried include the start as it was
    written with the end as the rewrite left it. Those two sit on histories with no commit in
    common, and ``git rev-list old..new`` answers such a pair with the whole new history -- a row
    covering every commit before its own start. A pair is therefore a range only when the start
    is an ancestor of the end, which is what ``first..last`` means (KI-035).
    """
    remap = load_remap(root) if remap is None else remap
    for first, last in RANGE.findall(scope):
        for start in _through_remap(remap, first):
            for end in _through_remap(remap, last):
                try:  # ``a..b`` excludes ``a``; it is added back (a root has no parent)
                    git(root, "merge-base", "--is-ancestor", start, end)
                    listed = git(root, "rev-list", f"{start}..{end}").split()
                    listed.append(git(root, "rev-parse", f"{start}^{{commit}}").strip())
                except subprocess.CalledProcessError:
                    continue
                if full in listed:
                    return True
    bare = [h for h in HASH.findall(RANGE.sub(" ", scope)) if re.search(r"[a-f]", h)]
    return any(full.startswith(h) or full in successors(remap, h) for h in bare)


def uncovered_commits(root: Path, register_rows: list[dict[str, str]]) -> list[str]:
    scopes = [row.get(SCOPE_COLUMN, "") for row in register_rows]
    remap = load_remap(root)
    return [
        f"{full[:7]} {subject}"
        for full, subject in required_commits(root)
        if not any(covered(root, scope, full, remap) for scope in scopes)
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


def _git_env(root: Path) -> dict[str, str]:
    """A git environment with no global configuration and a fixed identity."""
    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(root),
        "GIT_AUTHOR_NAME": "register-test",
        "GIT_AUTHOR_EMAIL": "register-test@example.invalid",
        "GIT_COMMITTER_NAME": "register-test",
        "GIT_COMMITTER_EMAIL": "register-test@example.invalid",
    }


def _commit(root: Path, rel: str, date: str, subject: str) -> str:
    """Write ``rel``, commit it at ``date`` (any git date, its zone included), return the hash."""
    env = _git_env(root)
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


def _repo_with_dated_commits(root: Path) -> list[str]:
    """Three commits: one before the baseline on a surface, two after (surface, not surface)."""
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=_git_env(root), timeout=60)
    old = _commit(root, "tests/gates/test_old.py", "2026-09-10T10:00:00", "before the baseline")
    new = _commit(root, "tests/gates/test_new.py", "2026-09-16T10:00:00", "gate after the baseline")
    other = _commit(root, "docs/x.md", "2026-09-17T10:00:00", "a document, not a surface")
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
    assert uncovered_commits(tmp_path, [{SCOPE_COLUMN: f"{old[:7]}..HEAD"}]) != [], (
        "a moving reference is not a range end; such a scope covers the hash it names and no "
        "more, and the gate stays red over the commits the writer meant to cover (KI-035)"
    )


@pytest.mark.gate("G50")
def test_positive_control_a_scope_written_before_a_history_rewrite_still_covers(
    tmp_path: Path,
) -> None:
    """A register row is append-only: after the 2026-09-16 history rewrite its scope names
    commits that no longer exist, and the row may not be edited to follow. The map the rewrite
    records is what keeps the row honest -- and it rescues only what it names."""
    old, new, other = _repo_with_dated_commits(tmp_path)
    gone = "0badc0d" + "0" * 33
    vanished = "d0omed01" + "0" * 32
    maps = tmp_path / "docs" / "reference"
    maps.mkdir(parents=True, exist_ok=True)

    assert uncovered_commits(tmp_path, [{SCOPE_COLUMN: gone[:7]}]) != [], "no map, no rescue"

    (maps / "hash-remap-2026-09-16.tsv").write_text(
        f"# a rewrite\n{gone}\t{new}\tthe commit it became\n"
        f"{vanished}\t{'f' * 40}\tsomething nobody has\n",
        encoding="utf-8",
    )

    assert uncovered_commits(tmp_path, [{SCOPE_COLUMN: gone[:7]}]) == []
    assert uncovered_commits(tmp_path, [{SCOPE_COLUMN: f"{gone[:7]}..{other[:7]}"}]) == [], (
        "a range is followed through the map at its start"
    )
    assert uncovered_commits(tmp_path, [{SCOPE_COLUMN: f"{old[:7]}..{gone[:7]}"}]) == [], (
        "and at its end"
    )
    assert uncovered_commits(tmp_path, [{SCOPE_COLUMN: f"{vanished[:7]}..{other[:7]}"}]) != [], (
        "a range whose end the map sends nowhere covers nothing"
    )
    assert uncovered_commits(tmp_path, [{SCOPE_COLUMN: vanished[:7]}]) != [], (
        "a map entry pointing at a commit this repository does not have covers nothing"
    )
    assert uncovered_commits(tmp_path, [{SCOPE_COLUMN: "0ther123"}]) != [], "unmapped, uncovered"


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


@pytest.mark.gate("G50")
def test_positive_control_the_baseline_is_a_date_not_the_hour_the_suite_runs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Which commits need a row is a property of the commits, never of the clock or the host.

    Birth incident (2026-09-16, KI-035): the baseline was handed to ``git log --since=``, whose
    approximate date parser fills the hour a bare date leaves out from the current time. The
    cutoff therefore slid through the day and moved with the host's timezone: six commits on
    review-required surfaces were invisible on the owner's Mac and demanded rows on the Linux
    runner, which is where the second CI run went red while ``make check`` was green here. The
    zones are written as POSIX strings so the assertion holds on a container with no zone
    database (``XXX12`` is twelve hours behind UTC, ``YYY-14`` fourteen ahead).
    """
    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, env=_git_env(tmp_path), timeout=60
    )
    eve = _commit(tmp_path, "tests/gates/test_eve.py", "2026-09-14T23:59:00-06:00", "the eve")
    dawn = _commit(tmp_path, "tests/gates/test_dawn.py", "2026-09-15T00:04:26-06:00", "four past")
    dusk = _commit(tmp_path, "tests/gates/test_dusk.py", "2026-09-15T23:50:00-06:00", "ten to")

    for zone in ("UTC0", "XXX12", "YYY-14", "America/Denver"):
        monkeypatch.setenv("TZ", zone)
        assert [full for full, _ in required_commits(tmp_path)] == [dusk, dawn], (
            f"the set of commits needing a row moved with the host timezone {zone}"
        )
        assert eve not in [full for full, _ in required_commits(tmp_path)], (
            f"a commit dated the day before the baseline was demanded under {zone}"
        )


@pytest.mark.gate("G50")
def test_positive_control_a_range_covers_only_a_real_ancestry(tmp_path: Path) -> None:
    """A range covers what lies between its ends; a pair that is not an ancestry is not a range.

    Birth incident (2026-09-16, KI-035): each end of a range is followed through the rewrite map
    on its own, so the pairs tried include the old start with the new end. Those two sit on
    histories with no commit in common, and ``git rev-list old..new`` then answers with the whole
    new history -- a row silently covering every commit before its own start. Only a machine
    without the pre-rewrite objects could tell, which is why a fresh clone is the reviewer.
    """
    subprocess.run(
        ["git", "init", "-q"], cwd=tmp_path, check=True, env=_git_env(tmp_path), timeout=60
    )
    before = _commit(tmp_path, "tests/gates/test_before.py", "2026-09-16T09:00:00", "before")
    first = _commit(tmp_path, "tests/gates/test_first.py", "2026-09-16T10:00:00", "the first")
    last = _commit(tmp_path, "tests/gates/test_last.py", "2026-09-16T11:00:00", "the last")
    subprocess.run(
        ["git", "checkout", "-q", "--orphan", "as-it-was"],
        cwd=tmp_path,
        check=True,
        env=_git_env(tmp_path),
        timeout=60,
    )
    was_first = _commit(tmp_path, "tests/gates/test_wf.py", "2026-09-16T10:00:00", "the first was")
    was_last = _commit(tmp_path, "tests/gates/test_wl.py", "2026-09-16T11:00:00", "the last was")

    maps = tmp_path / "docs" / "reference"
    maps.mkdir(parents=True, exist_ok=True)
    (maps / "hash-remap-2026-09-16.tsv").write_text(
        f"# the rewrite\n{was_first}\t{first}\tthe first\n{was_last}\t{last}\tthe last\n",
        encoding="utf-8",
    )

    scope = f"{was_first[:7]}..{was_last[:7]}"
    assert covered(tmp_path, scope, first), "the range's own start is covered"
    assert covered(tmp_path, scope, last), "and its end"
    assert not covered(tmp_path, scope, before), (
        "a row covered a commit that precedes its own start, through an old start paired with a "
        "new end"
    )
