#!/bin/bash
# deploy/launchd/uninstall.sh: unload and remove the Insight Miner launchd agents for this user.
#
#   deploy/launchd/uninstall.sh            bootout both agents and delete their plists
#   deploy/launchd/uninstall.sh --dry-run  print what would happen; change nothing
#
# Only the two plists under ~/Library/LaunchAgents are removed. The repository, the database,
# and every log under data/logs stay exactly as they are.
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
AGENTS_DIR="$HOME/Library/LaunchAgents"
DOMAIN="gui/$(id -u)"
LABELS="com.wesmax.insightminer.run com.wesmax.insightminer.doctor"

say() {
  if [ "$DRY_RUN" = 1 ]; then
    echo "[dry-run] would: $*"
  else
    echo "$*"
  fi
}

for label in $LABELS; do
  dest="$AGENTS_DIR/$label.plist"
  say "launchctl bootout $DOMAIN/$label   (error ignored when not loaded)"
  if [ -f "$dest" ]; then
    say "rm $dest"
  else
    echo "$dest is not present"
  fi
  if [ "$DRY_RUN" = 0 ]; then
    launchctl bootout "$DOMAIN/$label" >/dev/null 2>&1 || true
    rm -f "$dest"
  fi
done

if [ "$DRY_RUN" = 1 ]; then
  echo "dry run complete: nothing was removed and launchctl was not called."
else
  echo "removed. Logs remain in $ROOT/data/logs; reinstall with $SCRIPT_DIR/install.sh."
fi
