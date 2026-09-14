#!/usr/bin/env python3
"""Print derived lines about this checkout's hooks; `make check` ends with them.

"Pre-commit runs on every commit" was in CLAUDE.md for a week while the hooks were not
installed on the machine at all: the claim was narrated, never checked. The first line asks
:func:`insightminer.services.doctor.check_hooks_installed` -- the same function the doctor
check contract covers, with its states tested -- so it is derived from the filesystem rather
than written by hand. The second line (2026-09-14) compares the hook scripts under
``tools/hooks/`` with the commands registered in the Claude Code hook settings, because a
script that exists but is not registered has never run either; registration is a human-only
edit, so the line says what is missing rather than fixing it.

Informational, never a gate: it always exits 0. A checkout with no hooks must still be able
to run ``make check`` (and to see, at the bottom, exactly why its commits are ungated).
"""

from __future__ import annotations

import json
from pathlib import Path

from insightminer.services.doctor import check_hooks_installed

ROOT = Path(__file__).resolve().parents[1]
SETTINGS = ROOT / ".claude" / "settings.json"
SCRIPTS = ROOT / "tools" / "hooks"


def registration_line() -> str:
    scripts = sorted(p.name for p in SCRIPTS.glob("*.sh"))
    try:
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        commands = [
            hook["command"]
            for entries in settings.get("hooks", {}).values()
            for entry in entries
            for hook in entry.get("hooks", [])
        ]
    except (OSError, ValueError, KeyError, TypeError):
        return "claude hooks: settings unreadable; nothing is registered"
    registered = [name for name in scripts if any(cmd.endswith("/" + name) for cmd in commands)]
    missing = [name for name in scripts if name not in registered]
    where = ".claude/settings.json"
    line = f"claude hooks: {len(registered)} of {len(scripts)} scripts registered in {where}"
    return line + (f" (not registered: {', '.join(missing)}; a human adds them)" if missing else "")


def main() -> None:
    check = check_hooks_installed()
    verdict = "installed" if check.ok else "NOT INSTALLED"
    print(f"git hooks: {verdict} ({check.detail})")
    print(registration_line())


if __name__ == "__main__":
    main()
