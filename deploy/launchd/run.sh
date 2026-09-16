#!/bin/bash
# deploy/launchd/run.sh: the wrapper launchd invokes for every scheduled Thread Digest job.
#
#   run.sh run      the collector run       (io.github.whowellgit.threaddigest.run: Monday and Thursday 06:30, D-30)
#   run.sh doctor   the staleness check     (io.github.whowellgit.threaddigest.doctor: hourly at :15, --alert-if-stale 5d)
#
# What it guarantees (docs/PLAN.md § Deployment path, § Resilience to outages):
#   - the repo root comes from this file's location, never from the caller's cwd or PATH;
#   - it refuses to run from a TCC-protected folder, where launchd is silently denied access;
#   - the project's virtualenv interpreter is used by absolute path (stock python3 is 3.9);
#   - the job runs under `caffeinate -i` when available, so a closed lid cannot strand a run;
#   - THREADDIGEST_* settings are loaded from .env without their values ever being printed;
#   - every wrapper line is timestamped in data/logs/launchd-<job>.log next to the job's output;
#   - the job's exit code is mapped to an operator action and then passed through unchanged.
#
# Exit code map (the CLI's codes, docs/PLAN.md):
#   0 ok, 75 locked, 130 cancelled     log only
#   4 rate limited, 5 network          log "will retry at the next interval": launchd runs the
#                                      job again at the next StartCalendarInterval entry
#   1 failed, 78 config               macOS notification with the status and the UI address
#   3 partial                         logged only: amber is read in the digest, never notified
#   anything else                      macOS notification "unexpected exit"
#
# Must stay /bin/bash 3.2 compatible: that is the interpreter launchd runs it with.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

JOB="${1:-run}"
case "$JOB" in
  run | doctor) ;;
  *)
    echo "usage: $0 {run|doctor}" >&2
    exit 64 # EX_USAGE
    ;;
esac

ROOT="$(repo_root_of "${BASH_SOURCE[0]}")"
refuse_if_tcc_protected "$ROOT" "run.sh"

# The virtualenv interpreter, by absolute path. Never `python3`: on stock macOS that is 3.9,
# and a PATH lookup under launchd resolves to whatever its minimal PATH happens to find first.
PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "run.sh: $PY is missing or not executable; run 'make setup' in $ROOT first." >&2
  exit 78 # EX_CONFIG
fi

LOG_DIR="$ROOT/data/logs"
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/launchd-$JOB.log"

# log <text>: one timestamped line to the job log and to stdout (launchd's StandardOutPath).
# A logging failure (disk full) is reported by tee on stderr and never aborts the job itself.
log() {
  printf '%s [%s] %s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$JOB" "$*" | tee -a "$LOG" || true
}

# load_env <file>: export the THREADDIGEST_* assignments of a dotenv file. The file is parsed
# line by line, never sourced, so it cannot run commands; keys must be plain identifiers;
# values are never printed. One pair of surrounding quotes is stripped, nothing else.
load_env() {
  local file="$1" line key value count=0
  [ -f "$file" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line#"${line%%[![:space:]]*}"}" # left-trim
    line="${line#export }"
    case "$line" in
      THREADDIGEST_*=*) ;;
      *) continue ;;
    esac
    key="${line%%=*}"
    value="${line#*=}"
    case "$key" in
      *[!A-Z0-9_]*) continue ;; # not an identifier: skip rather than guess
    esac
    case "$value" in
      \"*\")
        value="${value#\"}"
        value="${value%\"}"
        ;;
      \'*\')
        value="${value#\'}"
        value="${value%\'}"
        ;;
    esac
    export "$key=$value"
    count=$((count + 1))
  done <"$file"
  log ".env: exported $count THREADDIGEST_* key(s) from $file (values are never logged)"
}
load_env "$ROOT/.env"

UI_URL="${THREADDIGEST_UI_URL:-http://127.0.0.1:8765}"

# notify <status> <message>: macOS Notification Center via osascript. The text travels as
# *arguments* to an `on run argv` handler, never spliced into AppleScript source, so quotes or
# backslashes in a message cannot alter the script. Alerting is best-effort: a failure is
# logged and never changes the job's exit status.
notify() {
  local status="$1" message="$2" rc=0
  if ! command -v osascript >/dev/null 2>&1; then
    log "notification skipped (osascript not found): $status"
    return 0
  fi
  osascript \
    -e 'on run argv' \
    -e 'display notification (item 1 of argv) with title (item 2 of argv) subtitle (item 3 of argv)' \
    -e 'end run' \
    -- "$message" "Thread Digest" "$status" >>"$LOG" 2>&1 || rc=$?
  if [ "$rc" -eq 0 ]; then
    log "notification posted: $status"
  else
    log "notification failed (osascript exit $rc); the job's own status is unchanged: $status"
  fi
}

case "$JOB" in
  run)
    set -- "$PY" -m threaddigest run
    UI_PAGE="$UI_URL/runs"
    ;;
  doctor)
    set -- "$PY" -m threaddigest doctor --alert-if-stale 5d
    UI_PAGE="$UI_URL/system"
    ;;
esac
# -i: prevent idle sleep (not display sleep) while the job runs; caffeinate exits with the
# job's own status. No caffeinate (a non-Mac) simply means no sleep assertion.
if command -v caffeinate >/dev/null 2>&1; then
  set -- caffeinate -i "$@"
fi

cd "$ROOT"
log "start: $*"
rc=0
"$@" >>"$LOG" 2>&1 || rc=$?
log "exit $rc"

case "$rc" in
  0) log "$JOB ok" ;;
  75) log "another Thread Digest process holds the lock; nothing to do" ;;
  130) log "$JOB was cancelled by the operator; no notification" ;;
  4) log "rate limited by Reddit; will retry at the next interval" ;;
  5) log "network unavailable; will retry at the next interval" ;;
  1) notify "failed" "Scheduled $JOB failed (exit 1). Details: $UI_PAGE" ;;
  3) log "$JOB finished with warnings (exit 3); amber is read in the digest and on the Runs page, never notified (ruled 2026-09-16)" ;;
  78) notify "config error" "Scheduled $JOB refused to start: configuration or credentials (exit 78). Details: $UI_PAGE" ;;
  *) notify "unexpected exit $rc" "Scheduled $JOB exited with code $rc. Details: $UI_PAGE" ;;
esac
exit "$rc"
