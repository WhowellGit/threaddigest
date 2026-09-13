"""KI-001: mypy daemon state must never be tracked, and the daemon must be rooted per tree.

A tracked ``.dmypy.json`` pointed every clone on the same machine at this repo's running
daemon, so the mypy step of ``make check`` type-checked the wrong tree while printing green.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def tracked_files() -> set[str]:
    out = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"], capture_output=True, text=True, check=True
    ).stdout
    return set(out.split())


def test_dmypy_state_is_not_tracked_and_is_ignored() -> None:
    assert ".dmypy.json" not in tracked_files()
    assert ".dmypy.json" in (ROOT / ".gitignore").read_text(encoding="utf-8")


def test_dmypy_invocations_use_a_build_dir_status_file() -> None:
    for path in (ROOT / "Makefile", ROOT / ".pre-commit-config.yaml"):
        text = path.read_text(encoding="utf-8")
        for line in text.splitlines():
            if "dmypy" in line and "run" in line and "kill" not in line:
                assert "--status-file" in line and "dmypy.json" in line, f"{path.name}: {line}"
                assert ".build/" in line or "$(BUILD_DIR)" in line, f"{path.name}: {line}"
