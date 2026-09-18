"""``tools/renumber_known_issue.py``: a known-issue id renumber is one pass over every
citation in the tracked tree, never a hand sweep.

Birth incident (``docs/reference/reviews/2026-09-17-renumber-sweep-incident.md``): two agents in
separate worktrees each claimed the same next-free ``KI-`` id on 2026-09-17, and the hand fix that
followed moved only the two citations a gate had named, leaving three pointing a reader at the
wrong incident. This tool replaces the hand sweep: every listed test below builds a throwaway git
repository under ``tmp_path`` (the house pattern for a tool that touches the tracked-file set),
commits a baseline, and drives the tool's ``main()`` directly rather than through a subprocess,
since the module runs in-process exactly the way ``pytest`` imports it.

A real invocation of this tool always runs as ``uv run python -m tools.renumber_known_issue``
(it imports sibling ``tools`` modules, so it cannot run as a bare script -- the same constraint
``tools/private_terms.py`` documents); ``--root`` is what lets these tests point a real checkout's
copy of the tool at a disposable tree instead.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
from tools.renumber_known_issue import main, token_pattern

# --------------------------------------------------------------------------- fixture plumbing


def _write(root: Path, rel: str, content: str) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _git(root: Path, *args: str) -> str:
    """Run git in ``root`` with an isolated identity, so the test never depends on the
    operator's own global git config (the pattern ``tests/gates/test_review_packet.py`` uses)."""
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(root),
        "GIT_AUTHOR_NAME": "renumber-test",
        "GIT_AUTHOR_EMAIL": "renumber-test@example.invalid",
        "GIT_COMMITTER_NAME": "renumber-test",
        "GIT_COMMITTER_EMAIL": "renumber-test@example.invalid",
    }
    proc = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, env=env, text=True, timeout=60
    )
    return proc.stdout


def _init_repo(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "symbolic-ref", "HEAD", "refs/heads/main")


def _commit_all(root: Path, message: str = "baseline") -> None:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)


KNOWN_ISSUES_HEADER = (
    "# Known issues\n\n"
    "| ID | Date | Symptom | Root cause | Regression test (node id) | Status |\n"
    "|---|---|---|---|---|---|\n"
)

ROW_040 = "| KI-040 | 2026-09-10 | unrelated | unrelated | tests/x.py::test_x | fixed |\n"
ROW_041 = (
    "| KI-041 | 2026-09-17 | queue drains oldest first | ordering bug | "
    "tests/db/test_repo.py::test_newest_first | fixed |\n"
)
ROW_099 = (
    "| KI-099 | 2026-09-16 | unrelated rate limit | http-date parsing | "
    "tests/unit/test_retry.py::test_http_date | fixed |\n"
)


def _known_issues(*rows: str) -> str:
    return KNOWN_ISSUES_HEADER + "".join(rows)


# --------------------------------------------------------------------------- the tests


def test_it_rewrites_the_row_and_every_citation_in_one_pass(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    _write(root, "docs/runbook/KNOWN_ISSUES.md", _known_issues(ROW_040, ROW_041))
    _write(
        root,
        "docs/runbook/GUARDS.md",
        "# Guards\n\nSee KI-041 for why the due queue sorts as it does.\n",
    )
    _write(
        root,
        "src/pkg/repo.py",
        '"""Ordering fixed by KI-041."""\n\n# KI-041\nORDER = "newest_first"\n',
    )
    _write(
        root,
        "tests/db/test_repo.py",
        'def test_newest_first() -> None:\n    """Regression for KI-041."""\n    assert True\n',
    )
    _commit_all(root)

    code = main(["KI-041", "KI-099", "--root", str(root)])

    assert code == 0
    issues = (root / "docs/runbook/KNOWN_ISSUES.md").read_text(encoding="utf-8")
    assert "KI-099" in issues and "KI-041" not in issues
    guards = (root / "docs/runbook/GUARDS.md").read_text(encoding="utf-8")
    assert "KI-099" in guards and "KI-041" not in guards
    src = (root / "src/pkg/repo.py").read_text(encoding="utf-8")
    assert src.count("KI-099") == 2 and "KI-041" not in src
    test = (root / "tests/db/test_repo.py").read_text(encoding="utf-8")
    assert "KI-099" in test and "KI-041" not in test


def test_it_refuses_when_the_new_id_already_has_a_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    _write(root, "docs/runbook/KNOWN_ISSUES.md", _known_issues(ROW_041, ROW_099))
    _commit_all(root)

    code = main(["KI-041", "KI-099", "--root", str(root)])

    assert code == 1
    out = capsys.readouterr().out
    assert "KI-099" in out and "already has a row" in out
    issues = (root / "docs/runbook/KNOWN_ISSUES.md").read_text(encoding="utf-8")
    assert "KI-041" in issues  # untouched


def test_it_refuses_when_the_old_id_has_no_row(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    _write(root, "docs/runbook/KNOWN_ISSUES.md", _known_issues(ROW_040))
    _commit_all(root)

    code = main(["KI-041", "KI-099", "--root", str(root)])

    assert code == 1
    out = capsys.readouterr().out
    assert "KI-041" in out and "no row" in out


def test_it_refuses_a_malformed_id(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    _write(root, "docs/runbook/KNOWN_ISSUES.md", _known_issues(ROW_041))
    _commit_all(root)

    code = main(["KI-41x", "KI-099", "--root", str(root)])

    assert code == 1
    out = capsys.readouterr().out
    assert "KI-41x" in out and "well-formed" in out
    issues = (root / "docs/runbook/KNOWN_ISSUES.md").read_text(encoding="utf-8")
    assert "KI-041" in issues  # nothing written

    code = main(["KI-041", "not-an-id", "--root", str(root)])
    assert code == 1


def test_it_refuses_when_a_file_it_would_touch_has_uncommitted_changes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    _write(root, "docs/runbook/KNOWN_ISSUES.md", _known_issues(ROW_041))
    _write(root, "docs/runbook/GUARDS.md", "# Guards\n\nSee KI-041.\n")
    _commit_all(root)
    # An uncommitted, half-finished edit to a file the rename would touch.
    _write(root, "docs/runbook/GUARDS.md", "# Guards\n\nSee KI-041. Also a half-finished note.\n")

    code = main(["KI-041", "KI-099", "--root", str(root)])

    assert code == 1
    out = capsys.readouterr().out
    assert "docs/runbook/GUARDS.md" in out
    guards = (root / "docs/runbook/GUARDS.md").read_text(encoding="utf-8")
    assert "half-finished note" in guards
    assert "KI-041" in guards and "KI-099" not in guards
    issues = (root / "docs/runbook/KNOWN_ISSUES.md").read_text(encoding="utf-8")
    assert "KI-041" in issues  # untouched too

    # --dry-run writes nothing, so the same dirty tree does not block it.
    dry_code = main(["KI-041", "KI-099", "--root", str(root), "--dry-run"])
    assert dry_code == 0
    assert (root / "docs/runbook/GUARDS.md").read_text(encoding="utf-8") == guards


def test_a_dry_run_writes_nothing_and_lists_what_it_would_change(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    _write(root, "docs/runbook/KNOWN_ISSUES.md", _known_issues(ROW_041))
    _write(root, "docs/runbook/GUARDS.md", "# Guards\n\nSee KI-041 for the ordering rule.\n")
    _commit_all(root)
    before_issues = (root / "docs/runbook/KNOWN_ISSUES.md").read_bytes()
    before_guards = (root / "docs/runbook/GUARDS.md").read_bytes()

    code = main(["KI-041", "KI-099", "--root", str(root), "--dry-run"])

    assert code == 0
    out = capsys.readouterr().out
    assert "docs/runbook/KNOWN_ISSUES.md" in out
    assert "docs/runbook/GUARDS.md" in out
    assert "KI-041" in out
    assert "nothing written" in out
    assert (root / "docs/runbook/KNOWN_ISSUES.md").read_bytes() == before_issues
    assert (root / "docs/runbook/GUARDS.md").read_bytes() == before_guards


def test_it_never_rewrites_a_reference_record_and_reports_what_it_left(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    _write(root, "docs/runbook/KNOWN_ISSUES.md", _known_issues(ROW_041))
    _write(root, "docs/runbook/GUARDS.md", "# Guards\n\nSee KI-041.\n")
    _write(
        root,
        "docs/reference/reviews/2026-09-17-example-incident.md",
        "# Incident\n\nThe row was originally KI-041 before the fix.\n",
    )
    _commit_all(root)

    code = main(["KI-041", "KI-099", "--root", str(root)])

    assert code == 0
    ref = (root / "docs/reference/reviews/2026-09-17-example-incident.md").read_text(
        encoding="utf-8"
    )
    assert "KI-041" in ref and "KI-099" not in ref  # a reference record is never rewritten
    guards = (root / "docs/runbook/GUARDS.md").read_text(encoding="utf-8")
    assert "KI-099" in guards
    out = capsys.readouterr().out
    assert "renumber: 1 citation(s) of KI-041 left in docs/reference/reviews/" in out
    assert "docs/reference/reviews/2026-09-17-example-incident.md" in out


def test_a_longer_id_is_not_matched_by_a_shorter_one(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    _write(root, "docs/runbook/KNOWN_ISSUES.md", _known_issues(ROW_041))
    _write(
        root,
        "docs/runbook/GUARDS.md",
        "# Guards\n\nSee KI-041 here, and the unrelated KI-0410 stays put.\n",
    )
    _commit_all(root)

    code = main(["KI-041", "KI-099", "--root", str(root)])

    assert code == 0
    text = (root / "docs/runbook/GUARDS.md").read_text(encoding="utf-8")
    assert "KI-099" in text
    assert "KI-0410" in text  # the longer id is never truncated into a match
    assert token_pattern("KI-041").search(text) is None  # no bare KI-041 token survives


def test_it_rewrites_a_citation_in_code_a_docstring_and_a_test_name(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    _init_repo(root)
    _write(root, "docs/runbook/KNOWN_ISSUES.md", _known_issues(ROW_041))
    _write(
        root,
        "tests/unit/test_ordering.py",
        (
            '"""Regression note: KI-041 explains why the queue is ordered this way."""\n\n'
            "# KI-041: fixed by reordering\n"
            'ISSUE_ID = "KI-041"\n\n\n'
            "def test_case() -> None:\n"
            '    """KI-041 regression guard."""\n'
            "    assert True\n\n\n"
            'PARAMETRIZE_IDS = ["KI-041-case"]\n'
        ),
    )
    _commit_all(root)

    code = main(["KI-041", "KI-099", "--root", str(root)])

    assert code == 0
    text = (root / "tests/unit/test_ordering.py").read_text(encoding="utf-8")
    assert "KI-041" not in text
    assert text.count("KI-099") == 5  # docstring, comment, code, docstring, parametrize id
    assert '"KI-099-case"' in text  # the citation inside a test's own name
