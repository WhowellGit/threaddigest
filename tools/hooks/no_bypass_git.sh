#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash). Blocks git commands that bypass the commit gate or
# land directly on main. Reads the tool-call JSON on stdin; exit 2 blocks the call with
# the one-line reason on stderr, exit 0 allows it. Any internal error also exits 2, so
# the hook fails closed. Registered in .claude/settings.json; documented in
# docs/runbook/GUARDS.md (external controls).
#
# Blocked:
#   git commit|merge ... --no-verify (or any unambiguous prefix) or -n / a short cluster with n
#   git push ... --no-verify
#   git push to main: refspec whose destination is main, --all/--mirror, or no refspec while
#     the current branch (of the tool call's cwd) is main
#   git -c core.hooksPath=... / git config core.hooksPath ...
#   SKIP=... or PRE_COMMIT_ALLOW_NO_CONFIG=... assignments in front of a command (or exported)
#   pre-commit uninstall
set -euo pipefail
trap 'echo "no_bypass_git: internal error at: ${BASH_COMMAND}; failing closed" >&2; exit 2' ERR

DECIDE=$(cat <<'PYEOF'
import json
import os
import re
import shlex
import subprocess
import sys


def block(reason):
    sys.stderr.write("no_bypass_git: BLOCKED: " + reason + "\n")
    sys.exit(2)


ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
ENV_BYPASS = re.compile(r"^(SKIP|PRE_COMMIT_ALLOW_NO_CONFIG)=")
SHORT_CLUSTER_WITH_N = re.compile(r"^-[A-Za-z]*n[A-Za-z]*$")
WRAPPERS = {"command", "exec", "time", "nice", "nohup", "sudo", "env", "export", "builtin"}
GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path", "--config-env"}
COMMIT_VALUE_OPTS = {
    "-m", "--message", "-F", "--file", "-C", "-c", "--reuse-message", "--reedit-message",
    "--fixup", "--squash", "--author", "--date", "-t", "--template", "--cleanup", "--trailer",
}
PUSH_VALUE_OPTS = {"-o", "--push-option", "--repo", "--receive-pack", "--exec", "--recurse-submodules"}


def segments(command):
    return [seg for seg in re.split(r"\|\||&&|;|\||\n", command) if seg.strip()]


def tokens(segment):
    cleaned = re.sub(r"[(){}]", " ", segment)
    try:
        return shlex.split(cleaned, posix=True)
    except ValueError:
        return cleaned.split()


def is_no_verify(tok):
    return len(tok) >= 6 and "--no-verify".startswith(tok)


def current_branch(cwd):
    try:
        proc = subprocess.run(
            ["git", "symbolic-ref", "--short", "-q", "HEAD"],
            cwd=cwd, capture_output=True, text=True, timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    name = proc.stdout.strip()
    return name if proc.returncode == 0 and name else None


def check_commit_or_merge(sub, rest):
    j = 0
    while j < len(rest):
        tok = rest[j]
        if is_no_verify(tok):
            block("git %s --no-verify skips the pre-commit gate" % sub)
        if tok in COMMIT_VALUE_OPTS:
            j += 2
            continue
        if tok.startswith("-") and not tok.startswith("--") and SHORT_CLUSTER_WITH_N.match(tok):
            block("git %s %s: -n is --no-verify" % (sub, tok))
        j += 1


def check_push(rest, cwd):
    positionals = []
    j = 0
    while j < len(rest):
        tok = rest[j]
        if is_no_verify(tok):
            block("git push --no-verify skips the pre-push gate")
        if tok in ("--all", "--mirror"):
            block("git push %s includes main; push one branch" % tok)
        if tok == "--":
            positionals.extend(rest[j + 1:])
            break
        if tok in PUSH_VALUE_OPTS:
            j += 2
            continue
        if tok.startswith("-"):
            j += 1
            continue
        positionals.append(tok)
        j += 1
    refspecs = positionals[1:]
    for spec in refspecs:
        dst = spec.split(":", 1)[1] if ":" in spec else spec
        dst = dst.lstrip("+")
        if dst.startswith("refs/heads/"):
            dst = dst[len("refs/heads/"):]
        if dst == "main":
            block("direct push to main (%s); open a PR instead" % spec)
    if not refspecs and current_branch(cwd) == "main":
        block("git push from branch main pushes main directly; open a PR instead")


def check_git(toks, cwd):
    i = 1
    git_cwd = cwd
    while i < len(toks) and toks[i].startswith("-"):
        tok = toks[i]
        if tok in GIT_GLOBAL_WITH_VALUE:
            value = toks[i + 1] if i + 1 < len(toks) else ""
            if tok == "-c" and "core.hookspath" in value.lower():
                block("git -c core.hooksPath disables the installed hooks")
            if tok == "-C" and value:
                git_cwd = value if os.path.isabs(value) else os.path.join(cwd, value)
            i += 2
            continue
        if "core.hookspath" in tok.lower():
            block("git core.hooksPath override disables the installed hooks")
        i += 1
    if i >= len(toks):
        return
    sub, rest = toks[i], toks[i + 1:]
    if sub == "config" and any("core.hookspath" in t.lower() for t in rest):
        block("git config core.hooksPath redirects the installed hooks")
    if sub in ("commit", "merge"):
        check_commit_or_merge(sub, rest)
    elif sub == "push":
        check_push(rest, git_cwd)


def check_segment(toks, cwd):
    for idx, tok in enumerate(toks):
        if os.path.basename(tok) == "pre-commit" and "uninstall" in toks[idx + 1:]:
            block("pre-commit uninstall removes the commit gate")
    k = 0
    while k < len(toks):
        tok = toks[k]
        if ASSIGNMENT.match(tok):
            if ENV_BYPASS.match(tok):
                block("%s bypasses pre-commit" % tok.split("=", 1)[0])
            k += 1
            continue
        if os.path.basename(tok) in WRAPPERS:
            k += 1
            continue
        break
    if k < len(toks) and os.path.basename(toks[k]) == "git":
        check_git(toks[k:], cwd)


def main():
    data = json.loads(sys.stdin.read())
    if not isinstance(data, dict) or not isinstance(data.get("tool_name"), str):
        block("malformed hook input (no tool_name)")
    if data["tool_name"] != "Bash":
        return
    tool_input = data.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str) or not command.strip():
        return
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    for segment in segments(command):
        check_segment(tokens(segment), cwd)


main()
PYEOF
)

PYBIN="${CLAUDE_PROJECT_DIR:-.}/.venv/bin/python"
if [ ! -x "$PYBIN" ]; then
  PYBIN=python3
fi
command -v "$PYBIN" >/dev/null 2>&1

rc=0
"$PYBIN" -c "$DECIDE" || rc=$?
case "$rc" in
  0) exit 0 ;;
  2) exit 2 ;;
  *) echo "no_bypass_git: decision script failed (exit $rc); failing closed" >&2; exit 2 ;;
esac
