#!/usr/bin/env bash
# PreToolUse hook (matcher: Edit|Write|MultiEdit). Read before you touch: when the file being
# edited matches a rule file's paths: globs (.claude/rules/*.md), the documents that rule
# file says to read first must have been consulted in this session, judged from the session
# transcript Claude Code passes as transcript_path (scanned incrementally, per session, so a
# call costs the bytes appended since the last call). Two modes, read from
# tools/hooks/read_before_touch.mode (committed, so a flip is a reviewed change):
#   log    append a ledger entry to .build/hooks/read_before_touch.jsonl and allow the call
#          (a heuristic check logs first and blocks only once its ledger shows it is right;
#          Wes, 2026-09-14; ledger review 2026-09-28);
#   block  exit 2 with the missing documents named.
# Internal errors are logged and allowed in log mode and fail closed (exit 2) in block mode.
# Registered in .claude/settings.json by a human only; documented in docs/runbook/GUARDS.md (G49).
set -uo pipefail

DECIDE=$(cat <<'PYEOF'
import datetime as dt
import fnmatch
import json
import os
import re
import sys
from pathlib import Path

FILE_TOOLS = {"Edit", "Write", "MultiEdit"}
PROJECT = Path(os.environ.get("CLAUDE_PROJECT_DIR") or ".").resolve()
MODE_FILE = PROJECT / "tools" / "hooks" / "read_before_touch.mode"
LEDGER = PROJECT / ".build" / "hooks" / "read_before_touch.jsonl"
CACHE_DIR = PROJECT / ".build" / "hooks" / "read_cache"
RULES = PROJECT / ".claude" / "rules"
READ_FIRST = re.compile(r"^Read first:(.*)$", re.MULTILINE)
BACKTICK = chr(96)  # kept out of the source: a literal backtick breaks the shell heredoc on bash 3.2
TOKEN = re.compile(BACKTICK + r"([^" + BACKTICK + r"\s]+)" + BACKTICK)


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
    sys.stderr.write("read_before_touch: BLOCKED: " + reason + "\n")
    sys.exit(2)


def rule_files():
    """(rule file name, its paths: globs, its read-first documents that exist)."""
    out = []
    if not RULES.is_dir():
        return out
    for path in sorted(RULES.glob("*.md")):
        text = path.read_text(encoding="utf-8")
        globs = []
        if text.startswith("---"):
            front = text.split("---", 2)[1]
            globs = re.findall(r'^\s*-\s*"?([^"\n]+?)"?\s*$', front, flags=re.MULTILINE)
        docs = []
        match = READ_FIRST.search(text)
        if match:
            docs = [tok for tok in TOKEN.findall(match.group(1)) if (PROJECT / tok).is_file()]
        out.append((path.name, globs, docs))
    return out


def matches(rel, glob):
    if glob.endswith("/**"):
        return rel.startswith(glob[:-2])
    return fnmatch.fnmatch(rel, glob)


def consulted(transcript, session, needed):
    """Which of the needed documents appear in the transcript so far (scanned incrementally)."""
    seen = set()
    offset = 0
    cache = CACHE_DIR / (re.sub(r"[^A-Za-z0-9_-]", "_", session or "unknown") + ".json")
    try:
        state = json.loads(cache.read_text(encoding="utf-8"))
        if state.get("transcript") == str(transcript):
            offset = int(state.get("offset", 0))
            seen = set(state.get("seen", []))
    except (OSError, ValueError, TypeError):
        pass
    if transcript is not None and transcript.is_file():
        size = transcript.stat().st_size
        if size < offset:
            offset, seen = 0, set()
        with transcript.open("rb") as handle:
            handle.seek(offset)
            data = handle.read()
        offset = size
        for doc in needed:
            if doc not in seen and doc.encode("utf-8") in data:
                seen.add(doc)
        try:
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            cache.write_text(
                json.dumps({"transcript": str(transcript), "offset": offset, "seen": sorted(seen)}),
                encoding="utf-8",
            )
        except OSError:
            pass
    return seen


def decide():
    payload = json.load(sys.stdin)
    if not isinstance(payload, dict):
        raise ValueError("payload is not an object")
    tool = payload.get("tool_name")
    if tool not in FILE_TOOLS:
        return
    file_path = (payload.get("tool_input") or {}).get("file_path")
    if not file_path:
        return  # the enforcement-files hook already blocks a file tool without a path
    target = Path(file_path)
    if not target.is_absolute():
        target = Path(payload.get("cwd") or PROJECT) / target
    try:
        rel = target.resolve().relative_to(PROJECT).as_posix()
    except ValueError:
        return  # outside the project: not this hook's business
    needed = {}
    for name, globs, docs in rule_files():
        if any(matches(rel, glob) for glob in globs):
            for doc in docs:
                needed.setdefault(doc, name)
    if not needed:
        return
    transcript = payload.get("transcript_path")
    seen = consulted(Path(transcript) if transcript else None, payload.get("session_id"), list(needed))
    missing = sorted(doc for doc in needed if doc not in seen)
    if not missing:
        return
    ledger(
        {
            "at": now(),
            "session": payload.get("session_id"),
            "tool": tool,
            "file": rel,
            "rules": sorted({needed[doc] for doc in missing}),
            "missing": missing,
            "mode": mode(),
        }
    )
    if mode() == "block":
        block(f"editing {rel} before reading " + ", ".join(missing) + " (its rule file says read first)")


try:
    decide()
except SystemExit:
    raise
except Exception as exc:  # any internal error: the mode decides
    if mode() == "block":
        sys.stderr.write(f"read_before_touch: internal error {type(exc).__name__}: {exc}; failing closed\n")
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
    if [ "$(cat "${CLAUDE_PROJECT_DIR:-.}/tools/hooks/read_before_touch.mode" 2>/dev/null)" = "block" ]; then
      echo "read_before_touch: decision script failed (exit $rc); failing closed" >&2; exit 2
    fi
    exit 0 ;;
esac
