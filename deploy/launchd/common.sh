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
