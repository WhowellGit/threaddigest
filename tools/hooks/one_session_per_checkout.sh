#!/usr/bin/env bash
# PreToolUse hook (matcher: Edit|Write|MultiEdit|Bash, the tools that change a working tree) and
# SessionEnd hook (no matcher), one script branching on hook_event_name. One live agent session
# per checkout: a second one works in its own git worktree.
#
# Born 2026-09-14, when two agent sessions were live in one checkout. One had files edited but
# uncommitted on a branch; the other committed its own change from the same working tree, swept
# those files into its commit, and fast-forwarded main, which went red on the hook-settings gate
# a commit early. Content right, label wrong: nothing tells `git commit` whose edits it is
# staging. Wes approved the hook on 2026-09-16.
#
# The lock is .build/hooks/session.lock inside the checkout that `git rev-parse --show-toplevel`
# names from the payload's cwd, so a worktree has its own lock and the remedy works. No lock, or
# a lock last seen more than the liveness window ago (a session that died without a SessionEnd),
# and this session takes it. The lock held by this session (a sub-agent carries the parent's
# session_id) refreshes it. The lock held by another live session is an intrusion. Outside a git
# repository the hook is silent.
#
# Two modes, read from tools/hooks/one_session_per_checkout.mode (committed, so a flip is a
# reviewed change):
#   log    append a ledger entry to .build/hooks/one_session_per_checkout.jsonl and allow
#          (a heuristic check logs first and blocks only once its ledger shows it is right);
#   block  exit 2 naming the holder and the remedy.
# An intrusion is logged once per (intruder session, holder session) pair, so the ledger stays
# readable while a blocked session keeps being told why. Internal errors are logged and allowed
# in log mode and fail closed (exit 2) in block mode.
# Registered in .claude/settings.json by a human only; documented in docs/runbook/GUARDS.md (G57).
set -uo pipefail

DECIDE=$(cat <<'PYEOF'
import datetime as dt
import json
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".").resolve()
MODE_FILE = PROJECT / "tools" / "hooks" / "one_session_per_checkout.mode"
#: The one place the liveness window is stated: a lock older than this belongs to a session that
#: is gone (the app was quit, the process died), so the next session may take it. Quoted in the
#: G57 row of docs/runbook/GUARDS.md.
LIVENESS_SECONDS = 15 * 60
#: What a second session does instead. The topic names the branch and the sibling directory.
REMEDY = "git worktree add ../threaddigest-<topic> -b <topic>"


def mode():
    try:
        text = MODE_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "log"
    return text if text in ("log", "block") else "log"


def now():
    return dt.datetime.now(dt.timezone.utc)


def stamp(moment):
    return moment.isoformat(timespec="seconds")


def moment_of(text):
    """A timestamp from the lock file, read as UTC when it carries no zone; None when unusable."""
    try:
        parsed = dt.datetime.fromisoformat(str(text))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def block(reason):
    sys.stderr.write("one_session_per_checkout: BLOCKED: " + reason + "\n")
    sys.exit(2)


def checkout(cwd):
    """The working tree ``cwd`` sits in (a worktree is its own), or None outside a repository."""
    proc = subprocess.run(
        ["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )
    top = proc.stdout.strip()
    return Path(top).resolve() if proc.returncode == 0 and top else None


def hooks_dir(root):
    return root / ".build" / "hooks"


def ledger(root, entry):
    path = hooks_dir(root) / "one_session_per_checkout.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def lock_file(root):
    return hooks_dir(root) / "session.lock"


def read_lock(root):
    try:
        held = json.loads(lock_file(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return held if isinstance(held, dict) and held.get("session_id") else None


def write_lock(root, session, transcript, acquired):
    entry = {"session_id": session, "acquired": acquired, "last_seen": stamp(now())}
    if transcript:
        entry["transcript_path"] = str(transcript)
    path = lock_file(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(entry, sort_keys=True) + "\n", encoding="utf-8")


def live(held, moment):
    seen = moment_of(held.get("last_seen"))
    return seen is not None and (moment - seen).total_seconds() < LIVENESS_SECONDS


def first_sighting(root, session, holder):
    """True the first time this intruder meets this holder; the pair is remembered after."""
    name = re.sub(r"[^A-Za-z0-9_-]", "_", session) + ".json"
    path = hooks_dir(root) / "one_session_cache" / name
    try:
        seen = set(json.loads(path.read_text(encoding="utf-8")).get("holders", []))
    except (OSError, ValueError):
        seen = set()
    if holder in seen:
        return False
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"holders": sorted(seen | {holder})}), encoding="utf-8")
    return True


def intrusion(root, payload, held, session, moment):
    holder = str(held.get("session_id"))
    current = mode()
    if first_sighting(root, session, holder):
        ledger(
            root,
            {
                "at": stamp(moment),
                "checkout": str(root),
                "holder": holder,
                "holder_last_seen": held.get("last_seen"),
                "mode": current,
                "session": session,
                "tool": payload.get("tool_name"),
            },
        )
    if current == "block":
        block(
            f"session {holder} is live in this checkout ({root.name}), last seen "
            f"{held.get('last_seen')}; two sessions in one working tree commit each other's "
            f"edits. Work in your own tree: {REMEDY}"
        )


def decide():
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("payload is not an object")
    session = str(payload.get("session_id") or "")
    if not session:
        raise ValueError("payload names no session_id")
    root = checkout(payload.get("cwd") or PROJECT)
    if root is None:
        return  # not a checkout: there is no working tree to share
    held = read_lock(root)
    if str(payload.get("hook_event_name") or "PreToolUse") == "SessionEnd":
        if held and held.get("session_id") == session:
            lock_file(root).unlink(missing_ok=True)  # a normal end releases the lock at once
        return
    moment = now()
    if held is None or not live(held, moment):
        write_lock(root, session, payload.get("transcript_path"), stamp(moment))
    elif held.get("session_id") == session:
        acquired = held.get("acquired") or stamp(moment)  # the refresh moves last_seen only
        write_lock(root, session, payload.get("transcript_path"), acquired)
    else:
        intrusion(root, payload, held, session, moment)


try:
    decide()
except SystemExit:
    raise
except Exception as exc:  # any internal error: the mode decides
    if mode() == "block":
        sys.stderr.write(
            f"one_session_per_checkout: internal error {type(exc).__name__}: {exc}; failing closed\n"
        )
        sys.exit(2)
    try:  # the checkout may not be known yet, so the error goes to the project's own ledger
        ledger(PROJECT, {"at": stamp(now()), "error": f"{type(exc).__name__}: {exc}", "mode": "log"})
    except Exception:
        pass
    sys.exit(0)
PYEOF
)

PYBIN="${CLAUDE_PROJECT_DIR:-.}/.venv/bin/python"
if [ ! -x "$PYBIN" ]; then
  PYBIN=python3
fi

rc=0
"$PYBIN" -c "$DECIDE" || rc=$?
case "$rc" in
  0) exit 0 ;;
  2) exit 2 ;;
  *)
    if [ "$(cat "${CLAUDE_PROJECT_DIR:-.}/tools/hooks/one_session_per_checkout.mode" 2>/dev/null)" = "block" ]; then
      echo "one_session_per_checkout: decision script failed (exit $rc); failing closed" >&2; exit 2
    fi
    exit 0 ;;
esac
