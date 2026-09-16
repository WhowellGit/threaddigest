"""Gate: the pytest configuration that keeps tests offline and honest is in force.

The addopts are read from ``pyproject.toml`` (the invariant, not a proxy), and the
network block is proven behaviorally: a real ``connect`` inside a test must raise
the pytest-recording error, not reach the operating system.
"""

from __future__ import annotations

import importlib.util
import os
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


def test_the_live_suite_keeps_the_reddit_credentials_and_nothing_else(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Widened 2026-09-16 (readiness seat F1): the root fixture strips every THREADDIGEST_*
    variable, credentials included, so a live test could not pass even with credentials. The
    live suite's conftest keeps exactly the three Reddit variables and still isolates the data
    directory; ``make test-live`` is the one invocation and lifts the block for Reddit only."""
    spec = importlib.util.spec_from_file_location(
        "live_conftest", REPO_ROOT / "tests" / "live" / "conftest.py"
    )
    assert spec is not None and spec.loader is not None
    live = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(live)
    monkeypatch.setenv("THREADDIGEST_REDDIT_CLIENT_ID", "id")
    monkeypatch.setenv("THREADDIGEST_REDDIT_CLIENT_SECRET", "secret")
    monkeypatch.setenv("THREADDIGEST_REDDIT_USERNAME", "user")
    monkeypatch.setenv("THREADDIGEST_UI_PASSWORD", "must-go")
    data_dir = live.keep_credentials_only(monkeypatch, tmp_path)
    assert os.environ["THREADDIGEST_REDDIT_CLIENT_ID"] == "id"
    assert os.environ["THREADDIGEST_REDDIT_USERNAME"] == "user"
    assert "THREADDIGEST_UI_PASSWORD" not in os.environ
    assert os.environ["THREADDIGEST_DATA_DIR"] == str(data_dir) and data_dir.is_dir()
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    target = makefile[makefile.index("test-live:") :].split("\n\n", 1)[0]
    assert "pytest tests/live -m live" in target and "--allowed-hosts=" in target
    assert "reddit" in target and "--env-file .env" in target
