#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash|Edit|Write|MultiEdit). The enforcement files are written
# only by the enforcement tooling: .ratchets/* changes only through tools/ratchet.py
# (make ratchet-bump, make ratchet-loosen), and .claude/settings.json (the hook
# registration) only by a human. Reads the tool-call JSON on stdin; exit 2 blocks the
# call with the one-line reason on stderr, exit 0 allows it. Any internal error also
# exits 2, so the hook fails closed. Registered in .claude/settings.json; documented in
# docs/runbook/GUARDS.md (external controls).
#
# Edit/Write/MultiEdit: blocked when file_path lies under a .ratchets/ directory or is a
#   .claude/settings.json.
# Bash: only judged when the command mentions .ratchets or .claude/settings.json. Each
#   pipeline segment that does must be `make ratchet-bump|ratchet-loosen`, an invocation
#   of tools/ratchet.py, a read-only command (cat, grep, diff, ls, jq, ...), or a
#   read-only or staging git subcommand (diff, show, log, status, blame, add, commit,
#   ...). Redirects into a protected path, sed -i, tee, cp, mv, rm, python -c, git
#   checkout/restore and everything else are blocked.
set -euo pipefail
trap 'echo "enforcement_files_script_only: internal error at: ${BASH_COMMAND}; failing closed" >&2; exit 2' ERR

DECIDE=$(cat <<'PYEOF'
import json
import os
import re
import shlex
import sys


def block(reason):
    sys.stderr.write("enforcement_files_script_only: BLOCKED: " + reason + "\n")
    sys.exit(2)


PROTECTED_DIR = ".ratchets"
PROTECTED_FILE = (".claude", "settings.json")
REFERENCE = re.compile(r"\.ratchets(?![\w-])|\.claude/settings\.json")
REDIRECT = re.compile(r">{1,2}\s*[\"']?[^\s\"'|;&]*(\.ratchets|\.claude/settings\.json)")
ASSIGNMENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*=")
WRAPPERS = {"command", "exec", "time", "nice", "nohup", "sudo", "env", "builtin"}
FILE_TOOLS = {"Edit", "Write", "MultiEdit"}
RATCHET_TARGETS = {"ratchet-bump", "ratchet-loosen"}
READ_ONLY = {
    "cat", "less", "more", "head", "tail", "grep", "egrep", "fgrep", "rg", "diff", "cmp",
    "wc", "ls", "stat", "file", "md5", "md5sum", "shasum", "sha256sum", "sort", "uniq",
    "jq", "yq", "bat", "find", "echo", "printf", "test", "[", "true", "od", "hexdump",
    "xxd", "tr", "cut", "awk", "sed", "column", "nl", "tac", "rev", "realpath",
    "readlink", "basename", "dirname", "du", "tree",
}
GIT_ALLOWED = {
    "diff", "show", "log", "status", "blame", "ls-files", "cat-file", "grep", "add",
    "commit", "rev-parse", "describe", "shortlog",
}
GIT_GLOBAL_WITH_VALUE = {"-C", "-c", "--git-dir", "--work-tree", "--namespace", "--exec-path"}


def is_protected_path(path, cwd):
    full = path if os.path.isabs(path) else os.path.join(cwd, path)
    parts = os.path.normpath(full).split(os.sep)
    if PROTECTED_DIR in parts:
        return True
    return len(parts) >= 2 and tuple(parts[-2:]) == PROTECTED_FILE


def segments(command):
    return [seg for seg in re.split(r"\|\||&&|;|\||\n", command) if seg.strip()]


def tokens(segment):
    cleaned = re.sub(r"[(){}]", " ", segment)
    try:
        return shlex.split(cleaned, posix=True)
    except ValueError:
        return cleaned.split()


def command_word(toks):
    for idx, tok in enumerate(toks):
        if ASSIGNMENT.match(tok) or os.path.basename(tok) in WRAPPERS:
            continue
        return idx
    return None


def git_subcommand(toks):
    i = 1
    while i < len(toks) and toks[i].startswith("-"):
        i += 2 if toks[i] in GIT_GLOBAL_WITH_VALUE else 1
    return toks[i] if i < len(toks) else ""


def check_bash_segment(segment):
    match = REFERENCE.search(segment)
    if match is None:
        return
    target = match.group(0)
    if REDIRECT.search(segment):
        block("redirect into %s; only tools/ratchet.py writes there" % target)
    toks = tokens(segment)
    idx = command_word(toks)
    if idx is None:
        return
    if any(tok.endswith("tools/ratchet.py") for tok in toks):
        return
    cmd = os.path.basename(toks[idx])
    args = toks[idx + 1:]
    if cmd == "make":
        if RATCHET_TARGETS & set(args):
            return
        block("make target other than ratchet-bump/ratchet-loosen touching %s" % target)
    if cmd == "git":
        sub = git_subcommand(toks[idx:])
        if sub in GIT_ALLOWED:
            return
        block("git %s on %s; ratchet files change only through tools/ratchet.py" % (sub, target))
    if cmd in READ_ONLY:
        if cmd == "sed" and any(a.startswith("-i") or a == "--in-place" for a in args):
            block("sed -i on %s; only tools/ratchet.py writes there" % target)
        if cmd in ("awk", "gawk") and "-i" in args:
            block("awk -i on %s; only tools/ratchet.py writes there" % target)
        return
    block(
        "%s may write %s; use make ratchet-bump / make ratchet-loosen (tools/ratchet.py), "
        "or ask a human for .claude/settings.json" % (cmd, target)
    )


def main():
    data = json.loads(sys.stdin.read())
    if not isinstance(data, dict) or not isinstance(data.get("tool_name"), str):
        block("malformed hook input (no tool_name)")
    tool = data["tool_name"]
    tool_input = data.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}
    cwd = data.get("cwd") or os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    if tool in FILE_TOOLS:
        path = tool_input.get("file_path")
        if not isinstance(path, str) or not path:
            block("malformed %s input (no file_path)" % tool)
        if is_protected_path(path, cwd):
            block(
                "%s on %s: .ratchets/ changes only through make ratchet-bump / "
                "make ratchet-loosen (tools/ratchet.py); .claude/settings.json only by a human"
                % (tool, path)
            )
        return
    if tool != "Bash":
        return
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return
    for segment in segments(command):
        check_bash_segment(segment)


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
  *) echo "enforcement_files_script_only: decision script failed (exit $rc); failing closed" >&2; exit 2 ;;
esac
