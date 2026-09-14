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
#   git merge ... while the current branch is main, unless .build/check-green.json (written by
#     tools/check_stamp.py as the last step of make check) names the tree of the branch being
#     merged: main only ever receives a tree the check passed on (2026-09-14, from the packet
#     panel's dry run: nothing else stops a red fast-forward while there is no remote). git pull
#     on main is refused for the same reason. A `git switch main` or `git checkout main` earlier
#     in the same command counts: the branch the merge lands on is the one the command will be
#     on, not the one it started on (the principal-engineer seat's hole, 2026-09-14).
#   git commit whose command text, or whose -F/--file message file, carries an attribution
#     trailer (Wes's rule: a commit message ends at its last content line, and never names the
#     model that wrote it). A message file that cannot be read, and -F - (message on stdin, which
#     this hook cannot see), are blocked too: the check fails closed like every other one here.
#     The patterns below are spelled with a redundant character class so that this script does
#     not carry the very strings it bans; a regex engine treats the two spellings identically.
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
ATTRIBUTION = re.compile(r"Co-Authored[-]By|Generated with \[Claude Code\]", re.IGNORECASE)
MESSAGE_FILE_OPTS = ("--file", "-F")
MERGE_VALUE_OPTS = {"-m", "-F", "--file", "-S", "--gpg-sign", "-X", "--strategy-option", "-s", "--strategy", "--into-name"}
STAMP = os.path.join(".build", "check-green.json")


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


ASSUMED_BRANCH = None  # set by main() when an earlier segment switched branches


def effective_branch(cwd):
    """The branch the current segment will run on: a switch earlier in the command wins over
    the branch the command started on."""
    return ASSUMED_BRANCH if ASSUMED_BRANCH is not None else current_branch(cwd)


def branch_switch(toks):
    """The branch a `git switch` / `git checkout` segment lands on, "" for a detached head,
    None when the segment is not a branch change (a file checkout, another command)."""
    k = 0
    while k < len(toks) and (ASSIGNMENT.match(toks[k]) or os.path.basename(toks[k]) in WRAPPERS):
        k += 1
    if k >= len(toks) or os.path.basename(toks[k]) != "git":
        return None
    i = k + 1
    while i < len(toks) and toks[i].startswith("-"):
        i += 2 if toks[i] in GIT_GLOBAL_WITH_VALUE else 1
    if i >= len(toks) or toks[i] not in ("switch", "checkout"):
        return None
    rest = toks[i + 1:]
    if "--" in rest:
        return None  # a path checkout, never a branch change
    j = 0
    while j < len(rest):
        tok = rest[j]
        if tok in ("-c", "-C", "--create", "--force-create", "-b", "-B", "--orphan"):
            return rest[j + 1] if j + 1 < len(rest) else ""
        if tok in ("-d", "--detach"):
            return ""
        if tok.startswith("-"):
            j += 1
            continue
        return tok
    return None


def message_files(rest):
    """Every -F/--file value in a git commit argument list, in all four spellings."""
    paths = []
    j = 0
    while j < len(rest):
        tok = rest[j]
        for opt in MESSAGE_FILE_OPTS:
            if tok == opt:
                if j + 1 < len(rest):
                    paths.append(rest[j + 1])
                    j += 1
                break
            if tok.startswith(opt + "="):
                paths.append(tok[len(opt) + 1:])
                break
            if opt == "-F" and tok.startswith("-F") and len(tok) > 2:
                paths.append(tok[2:])
                break
        j += 1
    return paths


def commits(command):
    """True when any pipeline segment invokes git commit."""
    for segment in segments(command):
        names = [os.path.basename(tok) for tok in tokens(segment)]
        if "git" in names and "commit" in names[names.index("git") + 1:]:
            return True
    return False


def check_message_files(rest, cwd):
    """Read every -F/--file message file of one git commit. Unreadable, or stdin, blocks."""
    for path in message_files(rest):
        if path == "-":
            block("git commit -F - reads the message from stdin, which cannot be checked for an attribution trailer")
        full = path if os.path.isabs(path) else os.path.join(cwd, path)
        try:
            with open(full, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            block("git commit -F %s: message file cannot be read; failing closed" % path)
        if ATTRIBUTION.search(text):
            block("message file %s carries an attribution trailer; remove it before committing" % path)


def git_out(args, cwd):
    try:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, timeout=5)
    except (OSError, subprocess.SubprocessError):
        return None
    out = proc.stdout.strip()
    return out if proc.returncode == 0 and out else None


def check_merge_into_main(rest, cwd):
    """main receives only a tree the check passed on: the stamp must name the merged tree."""
    if effective_branch(cwd) != "main":
        return
    sources = []
    j = 0
    while j < len(rest):
        tok = rest[j]
        if tok in MERGE_VALUE_OPTS:
            j += 2
            continue
        if tok.startswith("-"):
            j += 1
            continue
        sources.append(tok)
        j += 1
    if len(sources) != 1:
        block("git merge into main must name exactly one branch (got %d)" % len(sources))
    source = sources[0]
    top = git_out(["rev-parse", "--show-toplevel"], cwd) or cwd
    try:
        with open(os.path.join(top, STAMP), encoding="utf-8") as handle:
            stamp = json.load(handle)
        stamped = stamp["tree"]
    except (OSError, ValueError, KeyError, TypeError):
        block("no green check stamp; run make check on %s (staged, no untracked files) before merging into main" % source)
    tree = git_out(["rev-parse", "--verify", "--quiet", source + "^{tree}"], cwd)
    if tree is None:
        block("cannot resolve %s to a tree; failing closed" % source)
    if tree != stamped:
        block("the green check stamp is for a different tree than %s; run make check on it before merging into main" % source)


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
    if not refspecs and effective_branch(cwd) == "main":
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
        if sub == "commit":
            check_message_files(rest, git_cwd)
        else:
            check_merge_into_main(rest, git_cwd)
    elif sub == "pull" and effective_branch(git_cwd) == "main":
        block("git pull on main merges without the check stamp; fetch, then merge a checked branch")
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
    global ASSUMED_BRANCH
    for segment in segments(command):
        toks = tokens(segment)
        check_segment(toks, cwd)
        landed = branch_switch(toks)
        if landed is not None:
            ASSUMED_BRANCH = landed
    # The trailer scan is judged on the WHOLE command text, not per segment: a -m message may
    # contain newlines and segments() splits on those, so a per-segment scan would miss a trailer
    # sitting on its own line. The -F files are read per segment (check_git), so a -F belonging to
    # some other command in the pipeline -- grep -F, say -- is never read as a commit message.
    if commits(command) and ATTRIBUTION.search(command):
        block("git commit carries an attribution trailer; a commit message ends at its last content line")


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
