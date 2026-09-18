"""G19's second half: no test writes outside the data directory (code panel finding C-3(c)).

``tests/gates/test_data_dir_isolation.py`` holds the half that was already enforced, and it is
about the *settings*: it stops code that asks where the data directory is from being told the
real one. It cannot stop code that never asks, and the 2026-09-17 code panel's adversarial seat
proved the gap by planting a live write to a hard-coded path outside any data directory inside
``services/collect.py``. The suite sent that file 37 lines while ``ruff``, ``mypy``,
``lint-imports``, the ratchets and the whole of pytest stayed green. Irreversible rule 1 has two
halves and only one of them was mechanical.

The enforcer is the autouse fixture ``no_write_outside_the_data_dir`` in ``tests/conftest.py``,
which wraps the Python-level open paths and fails the test on a write outside the allowed tree.
Its rule is the pure function :func:`tests.conftest.write_outside`, which is why this file can
state the rule directly instead of trusting that the fixture was installed.

Two controls, in the two places a guard can be hollow:

* the rule, on planted paths -- the panel's own write is a finding, and every place a test
  legitimately writes is not;
* the fixture, end to end, in a child pytest run: red on a write one directory outside the
  temp tree, green on the same write inside it, so the finding is the location and not the
  writing.

Out of scope, stated so it is not mistaken for covered: SQLite's own file opens happen inside
the C library and pass through none of the wrapped functions (that is the data-directory seam's
job), and a write made by a *subprocess* is its own process's business -- which is why the
run-level snapshot in ``tests/e2e/test_data_dir_writes.py`` stays.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from tests.conftest import ALLOWED_REPO_DIRS, write_outside

pytestmark = pytest.mark.gate("G19")

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_the_write_rule_names_the_path_that_is_outside(
    tmp_path: Path, isolated_data_dir: Path
) -> None:
    """The rule stated directly, both directions on the same call."""
    allowed = (tmp_path.resolve(), isolated_data_dir.resolve())
    outside = tmp_path.parent / "collector-debug.log"

    finding = write_outside(outside, allowed)
    assert finding is not None
    assert str(outside.resolve()) in finding

    assert write_outside(tmp_path / "scratch.json", allowed) is None
    assert write_outside(isolated_data_dir / "threaddigest.db", allowed) is None
    assert write_outside(os.devnull, allowed) is None
    assert write_outside(REPO_ROOT / ".build" / "code_health.json", allowed) is None
    assert write_outside(REPO_ROOT / ".coverage.host.1234", allowed) is None
    assert write_outside(REPO_ROOT / "src" / "threaddigest" / "cli.pyc", allowed) is None
    assert write_outside(3, allowed) is None  # a file descriptor the caller already holds

    # The repository itself is not a scratch directory, and `data/` least of all.
    assert write_outside(REPO_ROOT / "data" / "threaddigest.db", allowed) is not None
    assert write_outside(REPO_ROOT / "config" / "settings.yaml", allowed) is not None
    assert write_outside(REPO_ROOT / "docs" / "PLAN.md", allowed) is not None


def test_the_allowed_repository_directories_are_all_gitignored() -> None:
    """The allow-list earns its place only while every entry is generated and ignored: a
    directory git tracks is one an operator's work could live in."""
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert {f"{name}/" for name in ALLOWED_REPO_DIRS} <= set(ignored)


#: The child run's test file. It writes with `Path.write_text`, which reaches the guard through
#: `io.open` -- the indirection most of the suite's writes take, and the one a guard that wrapped
#: only `builtins.open` would miss.
PLANTED_TEST = """\
from pathlib import Path


def test_writes_where_it_is_told(tmp_path):
    Path({target!r}).write_text("37 lines would have gone here\\n", encoding="utf-8")
"""

ALLOWED_TEST = """\
from pathlib import Path


def test_writes_where_it_is_told(tmp_path):
    (tmp_path / "fine.log").write_text("allowed\\n", encoding="utf-8")
"""


def _child_pytest(planted: Path, basetemp: Path) -> subprocess.CompletedProcess[str]:
    """A pytest run with ``tests/conftest.py`` loaded as a plugin and nothing else.

    ``-o addopts=`` drops the project's own options (coverage, the network block, warnings as
    errors), so the child is this one fixture and the planted test. ``--basetemp`` keeps the
    child's temp tree inside the parent's own ``tmp_path`` rather than as a sibling under the
    shared ``pytest-of-<user>`` directory, where the child's numbered-directory cleanup would
    be looking at the parent's, and where the planted path would land inside the child's own
    allowed tree and so prove nothing.
    """
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            str(planted),
            "-p",
            "tests.conftest",
            "-o",
            "addopts=",
            "-p",
            "no:cacheprovider",
            "--basetemp",
            str(basetemp),
            "-q",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=300,
    )


def test_positive_control_a_planted_write_outside_the_temp_tree_is_red(tmp_path: Path) -> None:
    """The fixture itself, end to end, in the two worlds that differ by one path."""
    outside = tmp_path / "outside" / "collector-debug.log"
    outside.parent.mkdir()
    planted = tmp_path / "test_planted_write.py"
    planted.write_text(PLANTED_TEST.format(target=str(outside)), encoding="utf-8")

    red = _child_pytest(planted, tmp_path / "basetemp-red")
    assert red.returncode != 0, red.stdout + red.stderr
    assert "write outside the data directory" in red.stdout, red.stdout
    assert str(outside) in red.stdout, red.stdout
    assert not outside.exists(), "the guard let the write through before failing the test"

    inside = tmp_path / "test_allowed_write.py"
    inside.write_text(ALLOWED_TEST, encoding="utf-8")
    green = _child_pytest(inside, tmp_path / "basetemp-green")
    assert green.returncode == 0, green.stdout + green.stderr
