# deploy/launchd/common.sh: helpers shared by run.sh, install.sh and uninstall.sh.
# Sourced, never executed. Must stay /bin/bash 3.2 compatible (the bash launchd runs).

# repo_root_of <script path>: the repository root two levels above deploy/launchd/, with
# symlinks resolved, so every path the scripts print or compare is the physical one.
repo_root_of() {
  local dir
  dir="$(cd "$(dirname "$1")" && pwd -P)"
  (cd "$dir/../.." && pwd -P)
}

# canonical_home: $HOME with symlinks resolved. When HOME is unset (it never is under launchd's
# gui domain, but a bare `env -i` test harness may drop it) bash's tilde falls back to the
# account's home directory from the password database.
canonical_home() {
  local home="${HOME:-}"
  if [ -z "$home" ]; then
    home=~
  fi
  (cd "$home" 2>/dev/null && pwd -P) || printf '%s\n' "$home"
}

# tcc_protected_parent <path>: print the TCC-protected folder that contains <path> and return 0;
# return 1 when <path> is outside all of them. launchd agents are denied access to these
# folders without any error being raised: the job starts, reads nothing, writes nothing.
tcc_protected_parent() {
  local path="$1" home protected
  home="$(canonical_home)"
  for protected in "$home/Desktop" "$home/Documents" "$home/Downloads" "/Volumes"; do
    case "$path/" in
      "$protected"/*)
        printf '%s\n' "$protected"
        return 0
        ;;
    esac
  done
  return 1
}

# refuse_if_tcc_protected <root> <script name>: explain and exit 78 (EX_CONFIG) when <root> is
# inside a TCC-protected folder. docs/PLAN.md § Deployment path, "Location constraint".
refuse_if_tcc_protected() {
  local root="$1" who="$2" protected
  if protected="$(tcc_protected_parent "$root")"; then
    {
      echo "$who: refusing to run: $root is inside $protected, a TCC-protected folder."
      echo "$who: launchd agents are silently denied access to ~/Desktop, ~/Documents, ~/Downloads"
      echo "$who: and /Volumes/*: the job would start, read nothing, and report nothing useful."
      echo "$who: move the repo to ~/repos/insightminer (anywhere outside those folders) and run"
      echo "$who: deploy/launchd/install.sh again."
    } >&2
    exit 78
  fi
}

# How many THREADDIGEST_* keys the last load_env exported; empty when there was no such file.
# The caller reports it, because load_env itself must not log: run.sh's log file lives at a
# path this parse decides (KI-049), so the count is written after the file is open.
ENV_KEYS_LOADED=""

# load_env <file>: export the THREADDIGEST_* assignments of a dotenv file. The file is parsed
# line by line, never sourced, so it cannot run commands; keys must be plain identifiers;
# values are never printed. One pair of surrounding quotes is stripped, nothing else.
# Shared by run.sh (the job's environment) and install.sh (which needs the data directory to
# render the plists' log paths), so the two cannot come to read .env differently.
load_env() {
  local file="$1" line key value count=0
  ENV_KEYS_LOADED=""
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
  ENV_KEYS_LOADED="$count"
}

# data_dir_of <root>: the data directory this checkout resolves to, from THREADDIGEST_DATA_DIR
# (exported by the caller's environment, or by load_env out of .env) and falling back to
# <root>/data, which is what `settings.default_data_dir()` returns. A relative value is
# resolved against <root>, not the caller's working directory: launchd's WorkingDirectory is
# the checkout and a log path must not depend on who started the job. `~/` is expanded the way
# `Settings` expands it. One definition for both readers -- run.sh's job log and install.sh's
# rendered plists -- so the wrapper and the plists cannot disagree about where logs go.
data_dir_of() {
  local root="$1" value="${THREADDIGEST_DATA_DIR:-}"
  case "$value" in
    "") printf '%s\n' "$root/data" ;;
    /*) printf '%s\n' "$value" ;;
    "~/"*) printf '%s\n' "$(canonical_home)/${value#\~/}" ;;
    *) printf '%s\n' "$root/$value" ;;
  esac
}
