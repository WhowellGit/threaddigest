"""Hard-block hooks: each script blocks what it must, allows its twins, and fails closed.

The scripts under ``tools/hooks/`` are run exactly as Claude Code runs them (executable,
JSON on stdin, exit code is the decision) with ``CLAUDE_PROJECT_DIR`` and the JSON ``cwd``
pointing at a throwaway directory. Exit 2 blocks; 0 allows; malformed input must block.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.gate("G23")

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


# ------------------------------------------------- no_bypass_git: attribution trailers
#
# Wes's rule: a commit message ends at its last content line and never names the model that
# wrote it. The two banned strings are assembled at runtime so that this file does not carry
# them (see tests/gates/test_no_imported_identifiers.py, which scans every tracked text file).

TRAILER = "Co-Authored" + "-By: Someone <someone@example.invalid>"
GENERATED = "Generated with [" + "Claude Code]"

TRAILER_ROWS: list[tuple[str, int]] = [
    # allowed twins: ordinary messages, and the same words in a non-commit command
    ("git commit -m 'Land the sweep and the gate'", 0),
    ("git commit -m 'describe the attribution rule without quoting it'", 0),
    (f"grep -rn '{TRAILER}' docs/", 0),
    (f"echo '{GENERATED}' > /tmp/scratch", 0),
    (f"git log --grep '{TRAILER}'", 0),
    ("grep -F pattern docs/PLAN.md && git commit -m 'msg'", 0),  # a -F that is not a message file
    # blocked: the trailer in the command text, in any of git commit's message options
    (f"git commit -m 'msg\n\n{TRAILER}'", 2),
    (f'git commit -m "msg" -m "{TRAILER}"', 2),
    (f"git commit -m 'msg\n\n{GENERATED}'", 2),
    (f"git commit --trailer '{TRAILER}'", 2),
    ("git commit -am 'msg\n\n" + TRAILER.lower() + "'", 2),  # the match is case-insensitive
    # blocked: a message this hook cannot read
    ("git commit -F -", 2),
    ("git commit -F /nonexistent/message.txt", 2),
]


@pytest.mark.parametrize(
    ("command", "expected"), TRAILER_ROWS, ids=[row[0][:48] for row in TRAILER_ROWS]
)
def test_no_bypass_git_refuses_attribution_trailers(
    project: Path, command: str, expected: int
) -> None:
    proc = run_hook(NO_BYPASS, bash_payload(command, project), project)
    assert proc.returncode == expected, proc.stderr
    if expected == 2:
        assert "BLOCKED" in proc.stderr and proc.stderr.count("\n") == 1


@pytest.mark.gate("G36")
@pytest.mark.parametrize("option", ["-F", "--file", "-F{path}", "--file={path}"])
def test_positive_control_a_trailer_in_a_message_file_is_red(project: Path, option: str) -> None:
    """The same tree goes red with the trailer in the -F file and green once it is gone."""
    message = project / "COMMIT_MSG.txt"
    argument = option.format(path=message) if "{path}" in option else f"{option} {message}"

    message.write_text(f"Land the gate\n\nBody line.\n\n{TRAILER}\n", encoding="utf-8")
    red = run_hook(NO_BYPASS, bash_payload(f"git commit {argument}", project), project)
    assert red.returncode == 2, red.stderr
    assert "BLOCKED" in red.stderr and "attribution trailer" in red.stderr

    message.write_text("Land the gate\n\nBody line.\n", encoding="utf-8")
    green = run_hook(NO_BYPASS, bash_payload(f"git commit {argument}", project), project)
    assert green.returncode == 0, green.stderr


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


#: Every script under ``tools/hooks/`` and the matcher it is registered under. Registration
#: is a human-only edit, so this is the gate that makes it happen: a script that exists but is
#: not registered has never run (installed-ness, not existence), and the registered set must
#: equal the on-disk set. A new script turns this red until a human registers it; an entry
#: naming a script that is not here is a typo in the settings.
EXPECTED_MATCHERS: dict[str, str] = {
    "no_bypass_git.sh": "Bash",
    "enforcement_files_script_only.sh": "Bash|Edit|Write|MultiEdit",
    "read_before_touch.sh": "Edit|Write|MultiEdit",
}


def test_settings_json_registers_every_hook_script_with_timeout_5() -> None:
    on_disk = sorted(p.name for p in HOOKS_DIR.glob("*.sh"))
    assert on_disk == sorted(EXPECTED_MATCHERS), "a hook script without an expected matcher"
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    entries = settings["hooks"]["PreToolUse"]
    by_matcher = {entry["matcher"]: entry["hooks"] for entry in entries}
    assert len(by_matcher) == len(entries), "two PreToolUse entries share a matcher"
    assert set(by_matcher) == set(EXPECTED_MATCHERS.values())
    for script, matcher in EXPECTED_MATCHERS.items():
        (hook,) = by_matcher[matcher]
        assert hook["type"] == "command"
        assert hook["timeout"] == 5
        assert hook["command"].endswith(f"/tools/hooks/{script}")
        assert "$CLAUDE_PROJECT_DIR" in hook["command"]
        assert (HOOKS_DIR / script).is_file()


# ------------------------------------------------------------- read_before_touch (G49)
#
# The third hook, added on Wes's ruling of 2026-09-14 against the two-hook cut (N-16): an edit
# under a rule file's ``paths:`` must follow a read of the documents that rule file names first.
# Log-first: it writes a ledger entry and allows until its mode file says ``block``. Every test
# runs the script the way Claude Code would, with a synthetic project, rule file, and transcript.

READ_BEFORE = HOOKS_DIR / "read_before_touch.sh"


def _routed_project(project: Path, mode: str) -> Path:
    """One rule file routing ``src/x/db/**`` to two documents, in the given mode."""
    (project / ".claude" / "rules").mkdir(parents=True)
    (project / ".claude" / "rules" / "db.md").write_text(
        '---\npaths:\n  - "src/x/db/**"\n---\n# db\n\n'
        "Read first: `docs/DB.md` §1 and `docs/RUNBOOK.md` § Migrate.\n",
        encoding="utf-8",
    )
    (project / "docs").mkdir()
    (project / "docs" / "DB.md").write_text("# db\n", encoding="utf-8")
    (project / "docs" / "RUNBOOK.md").write_text("# runbook\n", encoding="utf-8")
    (project / "tools" / "hooks").mkdir(parents=True)
    (project / "tools" / "hooks" / "read_before_touch.mode").write_text(
        mode + "\n", encoding="utf-8"
    )
    (project / "src" / "x" / "db").mkdir(parents=True)
    return project


def _read_line(project: Path, rel: str) -> str:
    """One transcript line shaped like a Read tool call on ``rel``."""
    content = [{"type": "tool_use", "name": "Read", "input": {"file_path": str(project / rel)}}]
    return json.dumps({"type": "assistant", "message": {"content": content}})


def _transcript(project: Path, *read_paths: str) -> Path:
    transcript = project / "transcript.jsonl"
    transcript.write_text(
        "".join(_read_line(project, p) + "\n" for p in read_paths), encoding="utf-8"
    )
    return transcript


def _edit_payload(project: Path, rel: str, transcript: Path, session: str = "s1") -> dict[str, Any]:
    return {
        "tool_name": "Edit",
        "tool_input": {"file_path": str(project / rel)},
        "cwd": str(project),
        "session_id": session,
        "transcript_path": str(transcript),
    }


def _ledger(project: Path) -> list[dict[str, Any]]:
    path = project / ".build" / "hooks" / "read_before_touch.jsonl"
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


@pytest.mark.gate("G49")
def test_read_before_touch_logs_and_allows_in_log_mode(project: Path) -> None:
    _routed_project(project, "log")
    transcript = _transcript(project)  # nothing read yet
    proc = run_hook(READ_BEFORE, _edit_payload(project, "src/x/db/repo.py", transcript), project)
    assert proc.returncode == 0, proc.stderr
    (entry,) = _ledger(project)
    assert entry["missing"] == ["docs/DB.md", "docs/RUNBOOK.md"]
    assert (
        entry["rules"] == ["db.md"]
        and entry["mode"] == "log"
        and entry["file"] == "src/x/db/repo.py"
    )


@pytest.mark.gate("G49")
def test_read_before_touch_blocks_in_block_mode_and_allows_once_read(project: Path) -> None:
    _routed_project(project, "block")
    half = _transcript(project, "docs/DB.md")  # one of the two documents read
    proc = run_hook(READ_BEFORE, _edit_payload(project, "src/x/db/repo.py", half), project)
    assert proc.returncode == 2, proc.stderr
    assert "before reading docs/RUNBOOK.md" in proc.stderr
    both = _transcript(project, "docs/DB.md", "docs/RUNBOOK.md")
    proc = run_hook(READ_BEFORE, _edit_payload(project, "src/x/db/repo.py", both, "s2"), project)
    assert proc.returncode == 0, proc.stderr


@pytest.mark.gate("G49")
def test_read_before_touch_ignores_unrouted_files_and_other_tools(project: Path) -> None:
    _routed_project(project, "block")
    transcript = _transcript(project)
    unrouted = _edit_payload(project, "src/x/other.py", transcript)
    assert run_hook(READ_BEFORE, unrouted, project).returncode == 0
    assert run_hook(READ_BEFORE, bash_payload("echo hi", project), project).returncode == 0
    outside = {**unrouted, "tool_input": {"file_path": "/elsewhere/a.py"}}
    assert run_hook(READ_BEFORE, outside, project).returncode == 0
    assert _ledger(project) == []


@pytest.mark.gate("G49")
def test_read_before_touch_scans_the_transcript_incrementally(project: Path) -> None:
    _routed_project(project, "log")
    transcript = _transcript(project)
    run_hook(READ_BEFORE, _edit_payload(project, "src/x/db/a.py", transcript), project)
    with transcript.open("a", encoding="utf-8") as handle:
        handle.write(_read_line(project, "docs/DB.md") + "\n")
        handle.write(json.dumps({"summary": f"read {project / 'docs/RUNBOOK.md'}"}) + "\n")
    run_hook(READ_BEFORE, _edit_payload(project, "src/x/db/a.py", transcript), project)
    assert len(_ledger(project)) == 1, "the second call must find both documents in the new bytes"
    (cache,) = (project / ".build" / "hooks" / "read_cache").glob("*.json")
    state = json.loads(cache.read_text(encoding="utf-8"))
    assert state["offset"] == transcript.stat().st_size
    assert set(state["seen"]) == {"docs/DB.md", "docs/RUNBOOK.md"}


@pytest.mark.gate("G49")
@pytest.mark.parametrize(("mode", "expected"), [("log", 0), ("block", 2)])
def test_read_before_touch_internal_errors_follow_the_mode(
    project: Path, mode: str, expected: int
) -> None:
    _routed_project(project, mode)
    proc = run_hook(READ_BEFORE, "{not json", project)
    assert proc.returncode == expected, proc.stderr
    if mode == "log":
        (entry,) = _ledger(project)
        assert "error" in entry
    else:
        assert "failing closed" in proc.stderr


def test_read_before_touch_is_executable_bash_with_a_committed_mode() -> None:
    assert os.access(READ_BEFORE, os.X_OK)
    text = READ_BEFORE.read_text(encoding="utf-8")
    assert text.startswith("#!/usr/bin/env bash\n") and "set -uo pipefail" in text
    mode = (HOOKS_DIR / "read_before_touch.mode").read_text(encoding="utf-8").strip()
    assert mode in {"log", "block"}


def test_every_registered_hook_command_is_an_existing_executable_script() -> None:
    """Registration is checked against the tree: a registered command naming a script that
    does not exist is a hook that never runs (installed-ness, not existence)."""
    settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
    for entry in settings["hooks"]["PreToolUse"]:
        for hook in entry["hooks"]:
            rel = hook["command"].split('"$CLAUDE_PROJECT_DIR"/', 1)[1]
            assert os.access(REPO_ROOT / rel, os.X_OK), rel


# ------------------------------------------------ no_bypass_git: main receives checked trees
#
# 2026-09-14, from the packet panel's dry run: with no remote and the check on the push hook,
# nothing mechanical stopped a red tree from being fast-forwarded into main, and the
# two-sessions incident that morning did exactly that. make check now ends by stamping the
# tree it passed on (tools/check_stamp.py); the hook refuses a merge into main of any other tree.

CHECK_STAMP = REPO_ROOT / "tools" / "check_stamp.py"


def git_in(root: Path, *args: str) -> str:
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
        "HOME": str(root),
        "GIT_AUTHOR_NAME": "hook-test",
        "GIT_AUTHOR_EMAIL": "hook-test@example.invalid",
        "GIT_COMMITTER_NAME": "hook-test",
        "GIT_COMMITTER_EMAIL": "hook-test@example.invalid",
    }
    proc = subprocess.run(
        ["git", *args], cwd=root, check=True, capture_output=True, text=True, env=env, timeout=60
    )
    return proc.stdout.strip()


def repo_with_feature(root: Path) -> str:
    """main with one commit, a feature branch one commit ahead; returns the feature tree hash."""
    make_repo_on_branch(root, "main")
    (root / "a.txt").write_text("base\n", encoding="utf-8")
    git_in(root, "add", "-A")
    git_in(root, "commit", "-q", "-m", "base")
    git_in(root, "switch", "-q", "-c", "feature")
    (root / "b.txt").write_text("feature\n", encoding="utf-8")
    git_in(root, "add", "-A")
    git_in(root, "commit", "-q", "-m", "feature")
    tree = git_in(root, "rev-parse", "feature^{tree}")
    git_in(root, "switch", "-q", "main")
    return tree


def write_stamp(root: Path, tree: str) -> None:
    (root / ".build").mkdir(exist_ok=True)
    (root / ".build" / "check-green.json").write_text(
        json.dumps({"tree": tree, "commit": "x", "at": "now"}), encoding="utf-8"
    )


def test_merge_into_main_needs_the_green_stamp_for_that_tree(project: Path) -> None:
    tree = repo_with_feature(project)
    blocked = run_hook(NO_BYPASS, bash_payload("git merge --ff-only feature", project), project)
    assert blocked.returncode == 2 and "no green check stamp" in blocked.stderr
    write_stamp(project, "0" * 40)
    stale = run_hook(NO_BYPASS, bash_payload("git merge --ff-only feature", project), project)
    assert stale.returncode == 2 and "different tree" in stale.stderr
    write_stamp(project, tree)
    allowed = run_hook(NO_BYPASS, bash_payload("git merge --ff-only feature", project), project)
    assert allowed.returncode == 0, allowed.stderr
    allowed = run_hook(
        NO_BYPASS, bash_payload("git switch main && git merge --ff-only feature", project), project
    )
    assert allowed.returncode == 0, allowed.stderr
    unknown = run_hook(
        NO_BYPASS, bash_payload("git merge --ff-only nosuchbranch", project), project
    )
    assert unknown.returncode == 2 and "cannot resolve" in unknown.stderr
    pull = run_hook(NO_BYPASS, bash_payload("git pull", project), project)
    assert pull.returncode == 2 and "git pull on main" in pull.stderr


def test_merge_elsewhere_than_main_needs_no_stamp(project: Path) -> None:
    repo_with_feature(project)
    git_in(project, "switch", "-q", "-c", "integration")
    proc = run_hook(NO_BYPASS, bash_payload("git merge --ff-only feature", project), project)
    assert proc.returncode == 0, proc.stderr
    proc = run_hook(NO_BYPASS, bash_payload("git pull", project), project)
    assert proc.returncode == 0, proc.stderr


def run_stamp(root: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(CHECK_STAMP), "--root", str(root)],
        capture_output=True,
        text=True,
        check=False,
        cwd=root,
        timeout=60,
    )


def test_check_stamp_names_the_staged_tree_and_refuses_untracked_files(project: Path) -> None:
    repo_with_feature(project)
    git_in(project, "switch", "-q", "feature")
    proc = run_stamp(project)
    assert proc.returncode == 0 and "green for tree" in proc.stdout
    stamp = json.loads((project / ".build" / "check-green.json").read_text(encoding="utf-8"))
    assert stamp["tree"] == git_in(project, "rev-parse", "HEAD^{tree}")
    # staged but uncommitted changes: the stamp names the tree the commit will have
    (project / "b.txt").write_text("feature, revised\n", encoding="utf-8")
    git_in(project, "add", "-A")
    proc = run_stamp(project)
    assert "tracked changes" in proc.stdout
    stamped = json.loads((project / ".build" / "check-green.json").read_text(encoding="utf-8"))[
        "tree"
    ]
    git_in(project, "commit", "-q", "-m", "revised")
    assert stamped == git_in(project, "rev-parse", "HEAD^{tree}")
    # an untracked file: no stamp, and the stale one is removed
    (project / "c.txt").write_text("untracked\n", encoding="utf-8")
    proc = run_stamp(project)
    assert proc.returncode == 0 and "untracked" in proc.stdout
    assert not (project / ".build" / "check-green.json").exists()


def test_a_branch_switch_earlier_in_the_command_counts(project: Path) -> None:
    """The principal-engineer seat's hole (2026-09-14): the hook judged the branch the command
    started on, so `git switch main && git merge feature` from a feature branch slipped past."""
    tree = repo_with_feature(project)
    git_in(project, "switch", "-q", "feature")
    for command in (
        "git switch main && git merge --ff-only feature",
        "git checkout main && git merge feature",
        "git checkout main && git pull",
        "git switch main && git push",
    ):
        proc = run_hook(NO_BYPASS, bash_payload(command, project), project)
        assert proc.returncode == 2, (command, proc.stderr)
    for command in (
        "git switch -c scratch && git merge feature",
        "git checkout -b scratch && git merge feature",
        "git checkout -- README.md && git merge feature",
    ):
        proc = run_hook(NO_BYPASS, bash_payload(command, project), project)
        assert proc.returncode == 0, (command, proc.stderr)
    write_stamp(project, tree)
    proc = run_hook(
        NO_BYPASS, bash_payload("git switch main && git merge --ff-only feature", project), project
    )
    assert proc.returncode == 0, proc.stderr


def test_make_check_removes_the_stamp_before_it_runs() -> None:
    """A stamp from an earlier green run must not outlive a check that goes red: the target's
    first step removes it, and the stamp step is the last, so only a fully green run leaves one."""
    lines = (REPO_ROOT / "Makefile").read_text(encoding="utf-8").splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("check:"))
    recipe = [line.strip() for line in lines[start + 1 :] if line.startswith("\t")]
    body = []
    for line in lines[start + 1 :]:
        if line.startswith("\t"):
            body.append(line.strip())
        elif line.strip() == "" or line.startswith("#"):
            continue
        else:
            break
    assert body[0].startswith("@rm -f") and "check-green.json" in body[0], body[0]
    assert "check_stamp.py" in body[-1], body[-1]
    assert recipe  # the recipe was found at all
