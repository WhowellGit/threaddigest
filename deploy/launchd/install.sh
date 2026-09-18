#!/bin/bash
# deploy/launchd/install.sh: install or refresh the Thread Digest launchd agents for this user.
#
#   deploy/launchd/install.sh            render, lint, write, and bootstrap both agents
#   deploy/launchd/install.sh --dry-run  print every step and the substituted paths; change nothing
#
# For each of io.github.whowellgit.threaddigest.run and io.github.whowellgit.threaddigest.doctor: substitute
# `__ROOT__` in deploy/launchd/<label>.plist with this repository's absolute path and
# `__LOG_DIR__` with the resolved data directory's `logs` folder, `plutil -lint` the rendered
# copy, write it to ~/Library/LaunchAgents, `launchctl bootout` any loaded version
# (errors ignored), then `launchctl bootstrap gui/$UID <plist>`. Refuses to install from a
# TCC-protected folder, where launchd would be silently denied access. Independent of `make`.
#
# The log directory comes from THREADDIGEST_DATA_DIR in .env, the same one run.sh resolves
# (common.sh's data_dir_of), so launchd's pre-wrapper output and the job log land together
# (KI-049). launchd reads the rendered plist, so a data directory moved after installation
# needs this script run again; the wrapper's own log path always follows .env.
#
# Must stay /bin/bash 3.2 compatible.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
# shellcheck source=common.sh
. "$SCRIPT_DIR/common.sh"

usage() { echo "usage: $0 [--dry-run]"; }

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      exit 64 # EX_USAGE
      ;;
  esac
done

ROOT="$(repo_root_of "${BASH_SOURCE[0]}")"
refuse_if_tcc_protected "$ROOT" "install.sh"

PY="$ROOT/.venv/bin/python"
if [ ! -x "$PY" ]; then
  echo "install.sh: $PY not found; run 'make setup' in $ROOT first." >&2
  exit 78 # EX_CONFIG
fi

AGENTS_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
LABELS="io.github.whowellgit.threaddigest.run io.github.whowellgit.threaddigest.doctor"

# .env decides where logs go, so it is read before anything is rendered (KI-049). Values are
# never printed; only the resolved directory is, which is a path and not a credential.
load_env "$ROOT/.env"
LOG_DIR="$(data_dir_of "$ROOT")/logs"

# say <text>: describe a step; prefixed in dry-run mode so the transcript reads honestly.
say() {
  if [ "$DRY_RUN" = 1 ]; then
    echo "[dry-run] would: $*"
  else
    echo "$*"
  fi
}

# render <src> <dest>: substitute __ROOT__ and __LOG_DIR__ with bash's own expansion, so any
# character in either path (spaces, `|`, `&`) is literal; sed would need escaping for each of
# them. __LOG_DIR__ goes first: it is the longer path and may itself contain __ROOT__.
render() {
  local content
  content="$(<"$1")"
  content="${content//__LOG_DIR__/$LOG_DIR}"
  printf '%s\n' "${content//__ROOT__/$ROOT}" >"$2"
}

# bootstrap <plist>: `launchctl bootout` is asynchronous, so a bootstrap that lands while the
# previous instance is still being torn down fails; retry briefly before giving up.
bootstrap() {
  local attempt
  for attempt in 1 2 3 4 5; do
    if launchctl bootstrap "$DOMAIN" "$1"; then
      return 0
    fi
    sleep 1
  done
  echo "install.sh: launchctl bootstrap $DOMAIN $1 failed after $attempt attempts" >&2
  return 1
}

WORK="$(mktemp -d "${TMPDIR:-/tmp}/threaddigest-launchd.XXXXXX")"
trap 'rm -rf "$WORK"' EXIT

echo "repo root:      $ROOT"
echo "interpreter:    $PY"
echo "launchd domain: $DOMAIN"
echo "agents dir:     $AGENTS_DIR"
echo "log directory:  $LOG_DIR"
if [ "$DRY_RUN" = 1 ]; then
  echo "mode:           dry run (nothing is written or loaded)"
fi
echo

say "mkdir -p $LOG_DIR   (launchd needs the directory for StandardOutPath)"
if [ "$DRY_RUN" = 0 ]; then
  mkdir -p "$LOG_DIR"
fi

for label in $LABELS; do
  src="$SCRIPT_DIR/$label.plist"
  rendered="$WORK/$label.plist"
  dest="$AGENTS_DIR/$label.plist"

  echo "== $label"
  for placeholder in __ROOT__ __LOG_DIR__; do
    if ! grep -Fq "$placeholder" "$src"; then
      echo "install.sh: $src contains no $placeholder placeholder; nothing would be substituted" >&2
      exit 1
    fi
  done
  render "$src" "$rendered"
  plutil -lint "$rendered" # the rendered copy, i.e. what launchd will read; a bad plist stops here
  # Both substituted paths, because the log directory may sit outside the checkout when the
  # data directory has been relocated (KI-049) and those two files are where a job that fails
  # before the wrapper's own log is open reports itself.
  echo "substituted paths:"
  if ! grep -F -e "$ROOT" -e "$LOG_DIR" "$rendered" | sed 's/^[[:space:]]*/    /'; then
    echo "install.sh: $rendered names neither $ROOT nor $LOG_DIR; substitution did nothing" >&2
    exit 1
  fi

  say "write $dest"
  say "launchctl bootout $DOMAIN/$label   (error ignored when not loaded)"
  say "launchctl enable $DOMAIN/$label"
  say "launchctl bootstrap $DOMAIN $dest"
  if [ "$DRY_RUN" = 0 ]; then
    mkdir -p "$AGENTS_DIR"
    cp "$rendered" "$dest"
    launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
    launchctl enable "$DOMAIN/$label" >/dev/null 2>&1 || true
    bootstrap "$dest"
  fi
  echo
done

if [ "$DRY_RUN" = 1 ]; then
  echo "dry run complete: nothing was written under $AGENTS_DIR and launchctl was not called."
else
  echo "installed."
fi
cat <<EOF

verify (look for "state =" and "last exit code ="; a fresh install shows no exit code yet):
  launchctl print $DOMAIN/io.github.whowellgit.threaddigest.run
  launchctl print $DOMAIN/io.github.whowellgit.threaddigest.doctor
trigger a run now instead of waiting for Monday or Thursday 06:30:
  launchctl kickstart $DOMAIN/io.github.whowellgit.threaddigest.run
logs (under the resolved data directory; re-run this script after moving it):
  $LOG_DIR/launchd-run.log       timestamped wrapper lines plus the run's output
  $LOG_DIR/launchd-doctor.log    the hourly staleness check
  $LOG_DIR/launchd-*.std*.log    anything printed before the wrapper opened its log
remove:
  $SCRIPT_DIR/uninstall.sh
EOF
