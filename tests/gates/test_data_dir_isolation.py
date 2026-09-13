"""Gate G19: tests can never run against the real data directory.

Positive controls construct the bad state (pytest loaded, no ``INSIGHTMINER_DATA_DIR``)
and assert that ``Settings`` refuses before anything is created, in-process and across the
subprocess seam (``PYTEST_CURRENT_TEST`` is inherited by children). The negative controls
prove the refusal is keyed on the invariant, not on pytest merely being present: an
explicit temp ``data_dir``, the opt-in variable, and a plain interpreter all construct.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from insightminer.settings import DataDirRefused, Settings, default_data_dir

pytestmark = pytest.mark.gate("G19")

REPO_ROOT = Path(__file__).resolve().parents[2]
CHILD = (
    "from insightminer.settings import Settings, default_data_dir\n"
    "s = Settings()\n"
    "assert s.data_dir == default_data_dir().resolve(), s.data_dir\n"
    "print(s.data_dir)\n"
)


def _listing(path: Path) -> list[str] | None:
    return sorted(p.name for p in path.iterdir()) if path.exists() else None


def _child_env(**overrides: str) -> dict[str, str]:
    """A child environment with no pytest, coverage, or insightminer variables."""
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("INSIGHTMINER_", "PYTEST_", "COV_CORE_"))
    }
    env.update(overrides)
    return env


def test_refuses_default_data_dir_while_pytest_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INSIGHTMINER_DATA_DIR")
    monkeypatch.delenv("INSIGHTMINER_ALLOW_REAL_DATA_DIR", raising=False)
    assert "pytest" in sys.modules
    before = _listing(default_data_dir())

    with pytest.raises(DataDirRefused, match="INSIGHTMINER_DATA_DIR"):
        Settings()

    assert _listing(default_data_dir()) == before


def test_refuses_when_env_points_at_the_default_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INSIGHTMINER_DATA_DIR", str(default_data_dir()))
    with pytest.raises(DataDirRefused):
        Settings()


def test_explicit_temp_data_dir_constructs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("INSIGHTMINER_DATA_DIR")
    resolved = Settings(data_dir=tmp_path)
    assert resolved.data_dir == tmp_path.resolve()


def test_opt_in_variable_allows_the_default_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("INSIGHTMINER_DATA_DIR")
    monkeypatch.setenv("INSIGHTMINER_ALLOW_REAL_DATA_DIR", "1")
    before = _listing(default_data_dir())

    resolved = Settings()

    assert resolved.data_dir == default_data_dir().resolve()
    assert _listing(default_data_dir()) == before


def test_plain_interpreter_without_pytest_constructs_normally() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", CHILD],
        env=_child_env(),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(default_data_dir().resolve())


def test_child_process_under_pytest_current_test_refuses() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", CHILD],
        env=_child_env(PYTEST_CURRENT_TEST="tests/gates/x.py::test (call)"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "DataDirRefused" in proc.stderr
