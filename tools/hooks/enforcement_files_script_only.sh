#!/usr/bin/env bash
# PreToolUse hook (matcher: Bash|Edit|Write|MultiEdit). The enforcement files are written
# only by the enforcement tooling: .ratchets/* changes only through tools/ratchet.py
# (make ratchet-bump, make ratchet-loosen), and .claude/settings.json (the hook
# registration) only by a human, who runs a Terminal script the agent generates
# (docs/runbook/RUNBOOK.md section 1; Wes, 2026-09-14). Reads the tool-call JSON on stdin; exit 2 blocks the
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
#   ...). Redirects into a protected path, sed -i or sed's w command, tee, cp, mv, rm,
#   python -c, git checkout/restore and everything else are blocked.
# Indirection (KI-020, external round one, 2026-09-14): a command that assigns a variable and
#   then writes through an expansion (a redirect target, a writing command's argument) is
#   refused whenever the command names a fragment of a protected path anywhere, because the
#   hook cannot resolve what the variable holds. A script file the agent writes and then runs
#   is outside this hook's sight by design (docs/runbook/GUARDS.md, G23).
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
# Slash-tolerant and case-insensitive (external round one panel, 2026-09-15): `.claude//settings
# .json` (a doubled slash from `$dir/` concatenation) and `.Ratchets` / `.CLAUDE` on the
# case-insensitive macOS filesystem both named the same protected file while a single-slash,
# case-sensitive regex let them through.
REFERENCE = re.compile(r"\.ratchets(?![\w-])|\.claude/+settings\.json", re.IGNORECASE)
REDIRECT = re.compile(
    r">{1,2}\s*[\"']?[^\s\"'|;&]*(\.ratchets|\.claude/+settings\.json)", re.IGNORECASE
)
# Indirection (KI-020, external round one, 2026-09-14): a protected path can reach a write
# through a variable set earlier in the same command, whole or in pieces. When the command
# holds a bare assignment AND names a fragment of a protected path anywhere, a write whose
# target or argument is an expansion is refused: the hook cannot resolve it, so it fails closed.
FRAGMENT = re.compile(r"ratch|settings|\.claude|hooks", re.IGNORECASE)
EXPANSION = re.compile(r"\$[A-Za-z_{(]")


def assigns(toks):
    """True when the segment starts with an assignment (after wrappers), whatever follows: a
    command substitution tokenizes as an assignment followed by a command, so this is the
    test, never "no command word"."""
    for tok in toks:
        if os.path.basename(tok) in WRAPPERS:
            continue
        return ASSIGNMENT.match(tok) is not None
    return False
REDIRECT_TO_EXPANSION = re.compile(r">{1,2}\s*[\"']?\$")
# sed's w / W commands and the s///w flag write a file without a redirect or -i.
SED_WRITE = re.compile(r"(^|[;{}\s/])([wW])\s+(\S+)")
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
    # Case-fold every segment (external round one panel, 2026-09-15): the macOS filesystem is
    # case-insensitive, so `.Ratchets` / `.CLAUDE/Settings.json` name the protected paths and
    # a case-sensitive compare let a Write to them through. normpath already collapses `//`.
    parts = [part.lower() for part in os.path.normpath(full).split(os.sep)]
    if PROTECTED_DIR in parts:
        return True
    return len(parts) >= 2 and tuple(parts[-2:]) == PROTECTED_FILE


def segments(command):
    return [seg for seg in re.split(r"\|\||&&|;|\||\n", command) if seg.strip()]


def tokens(segment):
    cleaned = re.sub(r"[(){}]", " ", segment)
    lexer = shlex.shlex(cleaned, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = "#"  # a trailing `# comment` is not part of the command
    try:
        return list(lexer)
    except ValueError:
        return [tok for tok in cleaned.split() if not tok.startswith("#")]


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
        for arg in args:
            for written in (m.group(3) for m in SED_WRITE.finditer(arg)) if cmd == "sed" else ():
                if REFERENCE.search(written) or written.startswith("$"):
                    block("sed's w command writes %s; only tools/ratchet.py writes there" % target)
        if cmd in ("awk", "gawk") and "-i" in args:
            block("awk -i on %s; only tools/ratchet.py writes there" % target)
        return
    block(
        "%s may write %s; use make ratchet-bump / make ratchet-loosen (tools/ratchet.py), "
        "or, for .claude/settings.json, generate a Terminal script for the human to run "
        "(docs/runbook/RUNBOOK.md section 1)" % (cmd, target)
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
                "make ratchet-loosen (tools/ratchet.py); .claude/settings.json only by a human: "
                "generate a Terminal script for them to run (docs/runbook/RUNBOOK.md section 1)"
                % (tool, path)
            )
        return
    if tool != "Bash":
        return
    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return
    # Join backslash-newline continuations as the shell does before parsing (external round one
    # panel, 2026-09-15): a protected path split across a continuation was invisible otherwise.
    command = command.replace("\\\r\n", "").replace("\\\n", "")
    segs = segments(command)
    for segment in segs:
        check_bash_segment(segment)
    check_indirection(segs, command)


def check_indirection(segs, command):
    """KI-020: a bare assignment plus a write through an expansion, in a command that names a
    fragment of a protected path anywhere, is refused as unresolvable."""
    if not FRAGMENT.search(command):
        return
    if not any(assigns(tokens(seg)) for seg in segs):
        return
    for seg in segs:
        toks = tokens(seg)
        idx = command_word(toks)
        if idx is None or not EXPANSION.search(seg):
            continue
        cmd = os.path.basename(toks[idx])
        writes = REDIRECT_TO_EXPANSION.search(seg) is not None
        if not writes:
            exempt = cmd in READ_ONLY or cmd in ("git", "make") or any(
                tok.endswith("tools/ratchet.py") for tok in toks
            )
            writes = not exempt or (cmd == "sed" and any(SED_WRITE.search(a) for a in toks[idx + 1:]))
        if writes:
            block(
                "%s writes through a shell variable set in this command, which names a protected "
                "path fragment; spell the path out so the hook can judge it" % cmd
            )


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
