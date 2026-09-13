"""Hard-block hooks: each script blocks what it must, allows its twins, and fails closed.

The scripts under ``tools/hooks/`` are run exactly as Claude Code runs them (executable,
JSON on stdin, exit code is the decision) with ``CLAUDE_PROJECT_DIR`` and the JSON ``cwd``
pointing at a throwaway directory. Exit 2 blocks; 0 allows; malformed input must block.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.gate("hooks")

REPO_ROOT = Path(__file__).resolve().parents[2]
HOOKS_DIR = REPO_ROOT / "tools" / "hooks"
NO_BYPASS = HOOKS_DIR / "no_bypass_git.sh"
ENFORCEMENT = HOOKS_DIR / "enforcement_files_script_only.sh"
SETTINGS = REPO_ROOT / ".claude" / "settings.json"


def run_hook(
    script: Path, payload: str | dict[str, Any], project: Path
) -> subprocess.CompletedProcess[str]:
    stdin = payload if isinstance(payload, str) else json.dumps(payload)
    env = {"PATH": os.environ["PATH"], "HOME": str(project), "CLAUDE_PROJECT_DIR": str(project)}
    return subprocess.run(
        [str(script)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        cwd=project,
        check=False,
        timeout=60,
    )


def bash_payload(command: str, cwd: Path) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": str(cwd)}


def file_payload(tool: str, file_path: str, cwd: Path) -> dict[str, Any]:
    return {"tool_name": tool, "tool_input": {"file_path": file_path}, "cwd": str(cwd)}


def make_repo_on_branch(root: Path, branch: str) -> None:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(root),
    }
    subprocess.run(["git", "init", "-q"], cwd=root, check=True, env=env, timeout=60)
    subprocess.run(
        ["git", "symbolic-ref", "HEAD", f"refs/heads/{branch}"],
        cwd=root,
        check=True,
        env=env,
        timeout=60,
    )


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    return root


# --------------------------------------------------------------------------- no_bypass_git

GIT_ROWS: list[tuple[str, int]] = [
    # allowed twins
    ("git commit -m 'msg'", 0),
    ("git commit -am 'msg'", 0),
    ('git commit -m "prose mentioning -n and --no-verify is fine"', 0),
    ("git merge --no-ff feature", 0),
    ("git push origin feature", 0),
    ("git push -u origin HEAD:feature", 0),
    ("git push --force-with-lease origin feature", 0),
    ("git -c color.ui=false status", 0),
    ("git config user.name wes", 0),
    ("pre-commit install", 0),
    ("pre-commit run --all-files", 0),
    ("echo SKIP=this-is-an-argument-not-an-assignment", 0),
    ("ls -la && git status", 0),
    ("git log --oneline -n 5", 0),
    # blocked
    ("git commit --no-verify -m 'msg'", 2),
    ("git commit -m 'msg' --no-verify", 2),
    ("git commit --no-veri -m 'msg'", 2),
    ("git commit -n -m 'msg'", 2),
    ("git commit -anm 'msg'", 2),
    ("git merge --no-verify feature", 2),
    ("git merge -n feature", 2),
    ("git push --no-verify origin feature", 2),
    ("git push origin main", 2),
    ("git push -f origin HEAD:main", 2),
    ("git push origin feature:refs/heads/main", 2),
    ("git push origin +main", 2),
    ("git push --delete origin main", 2),
    ("git push --all origin", 2),
    ("git -c core.hooksPath=/dev/null commit -m 'msg'", 2),
    ("git config core.hooksPath /tmp/nohooks", 2),
    ("SKIP=ruff git commit -m 'msg'", 2),
    ("PRE_COMMIT_ALLOW_NO_CONFIG=1 git commit -m 'msg'", 2),
    ("export SKIP=ruff; git commit -m 'msg'", 2),
    ("env SKIP=gitleaks git commit -m 'msg'", 2),
    ("pre-commit uninstall", 2),
    ("uv run pre-commit uninstall", 2),
    ("cd sub && git commit --no-verify -m 'msg'", 2),
    ("(git commit --no-verify -m 'msg')", 2),
    ("ls | git commit -n -F -", 2),
]


@pytest.mark.parametrize(("command", "expected"), GIT_ROWS, ids=[row[0] for row in GIT_ROWS])
def test_no_bypass_git_decides_bash_commands(project: Path, command: str, expected: int) -> None:
    proc = run_hook(NO_BYPASS, bash_payload(command, project), project)
    assert proc.returncode == expected, proc.stderr
    if expected == 2:
        assert "BLOCKED" in proc.stderr and proc.stderr.count("\n") == 1


@pytest.mark.parametrize(
    ("command", "branch", "expected"),
    [
        ("git push", "main", 2),
        ("git push origin", "main", 2),
        ("git push", "feat/x", 0),
        ("git push origin", "feat/x", 0),
    ],
)
def test_no_bypass_git_reads_the_current_branch_for_bare_pushes(
    project: Path, command: str, branch: str, expected: int
) -> None:
    make_repo_on_branch(project, branch)
    proc = run_hook(NO_BYPASS, bash_payload(command, project), project)
    assert proc.returncode == expected, proc.stderr


def test_no_bypass_git_allows_bare_push_when_branch_is_unknown(project: Path) -> None:
    proc = run_hook(NO_BYPASS, bash_payload("git push", project), project)  # not a repo
    assert proc.returncode == 0, proc.stderr


def test_no_bypass_git_ignores_other_tools(project: Path) -> None:
    proc = run_hook(NO_BYPASS, file_payload("Edit", "src/x.py", project), project)
    assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------------- enforcement files

FILE_ROWS: list[tuple[str, str, int]] = [
    ("Edit", ".ratchets/coverage.txt", 2),
    ("Write", "{project}/.ratchets/tests.txt", 2),
    ("MultiEdit", ".claude/settings.json", 2),
    ("Write", "{project}/.claude/settings.json", 2),
    ("Edit", "sub/../.ratchets/skips.txt", 2),
    # allowed twins
    ("Edit", "src/insightminer/settings.py", 0),
    ("Write", "docs/runbook/GUARDS.md", 0),
    ("Write", "tests/gates/test_ratchet.py", 0),
    ("Edit", ".claude/settings.local.json", 0),
    ("Write", "{project}/tools/ratchet.py", 0),
]


@pytest.mark.parametrize(
    ("tool", "path", "expected"), FILE_ROWS, ids=[f"{r[0]}:{r[1]}" for r in FILE_ROWS]
)
def test_enforcement_files_decides_file_tools(
    project: Path, tool: str, path: str, expected: int
) -> None:
    payload = file_payload(tool, path.format(project=project), project)
    proc = run_hook(ENFORCEMENT, payload, project)
    assert proc.returncode == expected, proc.stderr
    if expected == 2:
        assert "BLOCKED" in proc.stderr


BASH_ROWS: list[tuple[str, int]] = [
    # allowed: read-only, staging, or the ratchet tooling itself
    ("cat .ratchets/coverage.txt", 0),
    ("ls -la .ratchets", 0),
    ("grep -n line_percent .ratchets/coverage.txt | head -1", 0),
    ("diff .ratchets/tests.txt /tmp/other.txt", 0),
    ("git diff main -- .ratchets/", 0),
    ("git show main:.ratchets/coverage.txt", 0),
    ("git add .ratchets/ && git commit -m 'bump ratchets'", 0),
    ("make ratchet-bump", 0),
    ('make ratchet-loosen KEY=coverage.line_percent REASON="dropped dead code"', 0),
    ("uv run python tools/ratchet.py bump && cat .ratchets/tests.txt", 0),
    ("uv run python tools/ratchet.py loosen KEY=skips.count=1 REASON='#12 flaky'", 0),
    ("jq . .claude/settings.json", 0),
    ("sed -n 1p .ratchets/coverage.txt", 0),
    ("echo hello", 0),
    # blocked: anything that could write
    ("echo 'line_percent=1.00' > .ratchets/coverage.txt", 2),
    ("printf 'x' >> .ratchets/skips.txt", 2),
    ("sed -i '' 's/1/0/' .ratchets/skips.txt", 2),
    ("rm -rf .ratchets", 2),
    ("rm .ratchets/coverage.txt", 2),
    ("cp /tmp/settings.json .claude/settings.json", 2),
    ("tee .claude/settings.json < /tmp/x", 2),
    ("cat x | tee .ratchets/tests.txt", 2),
    ("git checkout main -- .ratchets/", 2),
    ("git restore .ratchets/coverage.txt", 2),
    ("python -c \"open('.ratchets/coverage.txt','w').write('')\"", 2),
    ("mv .ratchets/coverage.txt /tmp/", 2),
    ("cat .ratchets/coverage.txt; rm .ratchets/coverage.txt", 2),
    ("make clean .ratchets", 2),
    ('cat > "$CLAUDE_PROJECT_DIR/.ratchets/coverage.txt" <<EOF\nline_percent=1\nEOF', 2),
]


@pytest.mark.parametrize(("command", "expected"), BASH_ROWS, ids=[row[0][:60] for row in BASH_ROWS])
def test_enforcement_files_decides_bash_commands(
    project: Path, command: str, expected: int
) -> None:
    proc = run_hook(ENFORCEMENT, bash_payload(command, project), project)
    assert proc.returncode == expected, proc.stderr
    if expected == 2:
        assert "BLOCKED" in proc.stderr and proc.stderr.count("\n") == 1


def test_enforcement_files_ignores_unmatched_tools(project: Path) -> None:
    payload = {"tool_name": "Read", "tool_input": {"file_path": ".ratchets/coverage.txt"}}
    proc = run_hook(ENFORCEMENT, payload, project)
    assert proc.returncode == 0, proc.stderr


# --------------------------------------------------------------------------- fail closed

MALFORMED: list[str] = [
    "",
    "not json",
    "[]",
    "null",
    json.dumps({"tool_input": {"command": "ls"}}),
    json.dumps({"tool_name": 7, "tool_input": {}}),
]


@pytest.mark.parametrize("script", [NO_BYPASS, ENFORCEMENT], ids=lambda p: p.name)
@pytest.mark.parametrize("payload", MALFORMED, ids=[repr(m)[:40] for m in MALFORMED])
def test_hooks_fail_closed_on_malformed_input(project: Path, script: Path, payload: str) -> None:
    proc = run_hook(script, payload, project)
    assert proc.returncode == 2, proc.stderr
    assert proc.stderr.strip()


def test_enforcement_files_blocks_a_file_tool_without_a_path(project: Path) -> None:
    proc = run_hook(ENFORCEMENT, {"tool_name": "Edit", "tool_input": {}}, project)
    assert proc.returncode == 2, proc.stderr


def test_hooks_fail_closed_without_a_python_interpreter(project: Path) -> None:
    env = {
        "PATH": str(project / "empty-bin"),
        "HOME": str(project),
        "CLAUDE_PROJECT_DIR": str(project),
    }
    (project / "empty-bin").mkdir()
    proc = subprocess.run(
        ["/bin/bash", str(NO_BYPASS)],
        input=json.dumps(bash_payload("ls", project)),
        capture_output=True,
        text=True,
        env=env,
        cwd=project,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 2
    assert "failing closed" in proc.stderr


# --------------------------------------------------------------------------- registration


def test_hook_scripts_are_executable_bash_that_fails_closed() -> None:
    for script in (NO_BYPASS, ENFORCEMENT):
        assert os.access(script, os.X_OK), f"{script.name} must be executable"
        text = script.read_text(encoding="utf-8")
        assert text.startswith("#!/usr/bin/env bash\n")
        assert "set -euo pipefail" in text
        assert "trap '" in text and "exit 2' ERR" in text


def test_settings_json_registers_both_hooks_with_timeout_5() -> None:
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    entries = settings["hooks"]["PreToolUse"]
    by_matcher = {entry["matcher"]: entry["hooks"] for entry in entries}
    assert set(by_matcher) == {"Bash", "Bash|Edit|Write|MultiEdit"}
    for matcher, script in (
        ("Bash", "no_bypass_git.sh"),
        ("Bash|Edit|Write|MultiEdit", "enforcement_files_script_only.sh"),
    ):
        (hook,) = by_matcher[matcher]
        assert hook["type"] == "command"
        assert hook["timeout"] == 5
        assert hook["command"].endswith(f"/tools/hooks/{script}")
        assert "$CLAUDE_PROJECT_DIR" in hook["command"]
        assert (HOOKS_DIR / script).is_file()
