#!/usr/bin/env bash
# Stop hook (no matcher: it runs when the main agent finishes a turn). Open questions reach Wes
# in the session: if a document gained a line that parks a question for him during this
# session ("pending Wes", "waiting on Wes", "held for Wes", ...), the turn's closing message
# must present it. Born 2026-09-16, when eight decisions were recorded in the decisions log
# and the message only pointed at the log; Wes: "I'm not going to search through a log".
# The message is judged from the session transcript Claude Code passes as transcript_path
# (its tail only: the file grows large), the added lines from git (commits since the
# session started plus the working tree), and a question is judged once per session.
# Two modes, read from tools/hooks/questions_in_session.mode (committed, so a flip is a
# reviewed change):
#   log    append a ledger entry to .build/hooks/questions_in_session.jsonl and allow
#          (a heuristic check logs first and blocks only once its ledger shows it is right);
#   block  exit 2 with the unpresented questions named, so the turn cannot end silently.
# Internal errors are logged and allowed in log mode and fail closed (exit 2) in block mode.
# Registered in .claude/settings.json by a human only; documented in docs/runbook/GUARDS.md (G56).
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
MODE_FILE = PROJECT / "tools" / "hooks" / "questions_in_session.mode"
LEDGER = PROJECT / ".build" / "hooks" / "questions_in_session.jsonl"
CACHE_DIR = PROJECT / ".build" / "hooks" / "questions_cache"
WATCHED = ("docs", "CLAUDE.md")
#: A line that parks a question for Wes in a document.
QUESTION = re.compile(
    r"pending wes|waiting on wes|wes to (?:decide|rule|confirm)|wes'?s (?:call|ruling)|held for wes",
    re.IGNORECASE,
)
#: A closing message that presents a question rather than pointing at a file.
PRESENTED = re.compile(
    r"pending|waiting on you|your call|your decision|open question|recommend|decide|decision"
    r"|question for you|needs? your|for you to",
    re.IGNORECASE,
)
TAIL_BYTES = 2_000_000
HEAD_BYTES = 65_536


def mode():
    try:
        text = MODE_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        return "log"
    return text if text in ("log", "block") else "log"


def now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def ledger(entry):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, sort_keys=True) + "\n")


def block(reason):
    sys.stderr.write("questions_in_session: BLOCKED: " + reason + "\n")
    sys.exit(2)


def git(*args):
    proc = subprocess.run(
        ["git", "-C", str(PROJECT), *args], capture_output=True, text=True, check=False, timeout=30
    )
    return proc.stdout if proc.returncode == 0 else ""


def session_start(transcript):
    """The first line's timestamp, or the epoch when it has none."""
    with transcript.open("rb") as handle:
        first = handle.read(HEAD_BYTES).split(b"\n", 1)[0]
    try:
        stamp = json.loads(first).get("timestamp")
    except ValueError:
        stamp = None
    return stamp if isinstance(stamp, str) and stamp else "1970-01-01T00:00:00Z"


def last_message(transcript):
    """The text of the last assistant message that has text (tool calls alone do not count)."""
    size = transcript.stat().st_size
    with transcript.open("rb") as handle:
        handle.seek(max(0, size - TAIL_BYTES))
        tail = handle.read().decode("utf-8", errors="replace")
    for line in reversed(tail.splitlines()):
        if '"assistant"' not in line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if obj.get("type") != "assistant":
            continue
        content = (obj.get("message") or {}).get("content") or []
        texts = [b.get("text", "") for b in content if isinstance(b, dict) and b.get("type") == "text"]
        if any(t.strip() for t in texts):
            return "\n".join(texts)
    return ""


def added_questions(since):
    """Question lines added to the watched documents since the session started: commits in
    that window plus the working tree."""
    diffs = git("log", f"--since={since}", "--format=", "-p", "--", *WATCHED)
    diffs += git("diff", "HEAD", "--", *WATCHED)
    found = set()
    for line in diffs.splitlines():
        if line.startswith("+") and not line.startswith("+++") and QUESTION.search(line):
            found.add(line[1:].strip())
    return found


def decide():
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("payload is not an object")
    if payload.get("stop_hook_active"):
        return  # this turn was already continued by a stop hook; never loop
    transcript = Path(str(payload.get("transcript_path") or ""))
    if not transcript.is_file():
        raise FileNotFoundError(f"transcript {transcript} not found")
    session = str(payload.get("session_id") or "unknown")
    cache = CACHE_DIR / (re.sub(r"[^A-Za-z0-9_-]", "_", session) + ".json")
    try:
        seen = set(json.loads(cache.read_text(encoding="utf-8")).get("seen", []))
    except (OSError, ValueError):
        seen = set()
    questions = added_questions(session_start(transcript))
    new = sorted(questions - seen)
    if not new:
        return
    presented = bool(PRESENTED.search(last_message(transcript)))
    ledger({"at": now(), "session": session, "questions": new, "presented": presented, "mode": mode()})
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps({"seen": sorted(seen | set(new))}), encoding="utf-8")
    if not presented and mode() == "block":
        block(
            "a document gained a question for Wes this session that the closing message did not "
            "present; say it in the session with a recommendation: " + " | ".join(new[:3])[:600]
        )


try:
    decide()
except SystemExit:
    raise
except Exception as exc:  # any internal error: the mode decides
    if mode() == "block":
        sys.stderr.write(f"questions_in_session: internal error {type(exc).__name__}: {exc}; failing closed\n")
        sys.exit(2)
    try:
        ledger({"at": now(), "error": f"{type(exc).__name__}: {exc}", "mode": "log"})
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
    if [ "$(cat "${CLAUDE_PROJECT_DIR:-.}/tools/hooks/questions_in_session.mode" 2>/dev/null)" = "block" ]; then
      echo "questions_in_session: decision script failed (exit $rc); failing closed" >&2; exit 2
    fi
    exit 0 ;;
esac
