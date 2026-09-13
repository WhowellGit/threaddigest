"""Gate: the pytest configuration that keeps tests offline and honest is in force.

The addopts are read from ``pyproject.toml`` (the invariant, not a proxy), and the
network block is proven behaviorally: a real ``connect`` inside a test must raise
the pytest-recording error, not reach the operating system.
"""

from __future__ import annotations

import socket
import tomllib
import warnings
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _addopts() -> str:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    addopts = data["tool"]["pytest"]["ini_options"]["addopts"]
    assert isinstance(addopts, str)
    return addopts


def test_addopts_block_the_network() -> None:
    assert "--block-network" in _addopts()


def test_addopts_deselect_live_tests() -> None:
    assert "-m 'not live'" in _addopts()


def test_addopts_make_markers_strict_and_warnings_errors() -> None:
    addopts = _addopts()
    assert "--strict-markers" in addopts
    assert "-W error" in addopts


@pytest.mark.gate
def test_socket_connect_raises_under_block_network() -> None:
    # Port 9 (discard) on localhost: without the block this would reach the OS and raise
    # ConnectionRefusedError (an OSError), which is not the RuntimeError asserted here.
    with socket.socket() as sock, pytest.raises(RuntimeError, match="Network is disabled"):
        sock.connect(("127.0.0.1", 9))


@pytest.mark.gate
def test_warnings_are_errors_inside_tests() -> None:
    with pytest.raises(UserWarning, match="must become an error"):
        warnings.warn("this warning must become an error", UserWarning, stacklevel=1)


def test_pythonpath_puts_the_repo_root_on_sys_path() -> None:
    addopts = _addopts()
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    assert data["tool"]["pytest"]["ini_options"]["pythonpath"] == ["."]
    assert "pythonpath" not in addopts  # it is its own ini key, not smuggled into addopts


def test_sqlhelp_is_importable_from_every_test_package() -> None:
    """§2.2/§2.3: tests/services/, tests/e2e/ and tests/gates/ are not on TID251's
    per-file-ignore list, so they reach ``tests.db.sqlhelp`` for the Core-only helpers
    (``table_digest``, ``read_run``) rather than importing ``sqlalchemy.text`` themselves.
    This pins the exact import spelling so the wiring (tests/__init__.py,
    tests/db/__init__.py, pythonpath) cannot rot into a reason to widen that list.
    """
    from tests.db.sqlhelp import read_run, table_digest

    assert callable(table_digest)
    assert callable(read_run)
