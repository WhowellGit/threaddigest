#!/usr/bin/env python3
"""Print one derived line about this checkout's git hooks; `make check` ends with it.

"Pre-commit runs on every commit" was in CLAUDE.md for a week while the hooks were not
installed on the machine at all: the claim was narrated, never checked. This script asks
:func:`insightminer.services.doctor.check_hooks_installed` -- the same function the doctor
check contract covers, with its three states tested -- so the line at the end of every
``make check`` is derived from the filesystem rather than written by hand.

Informational, never a gate: it always exits 0. A checkout with no hooks must still be able
to run ``make check`` (and to see, at the bottom, exactly why its commits are ungated).
"""

from __future__ import annotations

from insightminer.services.doctor import check_hooks_installed


def main() -> None:
    check = check_hooks_installed()
    verdict = "installed" if check.ok else "NOT INSTALLED"
    print(f"git hooks: {verdict} ({check.detail})")


if __name__ == "__main__":
    main()
