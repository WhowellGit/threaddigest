"""The command line the launchd wrapper actually runs, run by the real interpreter.

``tests/deploy/test_launchd.py`` proves the wrapper's plumbing -- the exit-code map, the
notification argv, the ``.env`` parse -- against a *stub* ``threaddigest`` module it writes
itself and puts on ``PYTHONPATH``. That stub manufactures the ``__main__`` entry point, so the
whole deployment gate could be green while ``python -m threaddigest`` did not exist at all,
which is exactly what the 2026-09-17 code panel found (seat B finding B1, KI-045): both
launchd jobs exited 1 the instant they started, and the hourly ``doctor`` that would have
noticed a collector which had stopped collecting died by the same line.

So this module runs the wrapper's own command form through the **real** interpreter and the
**real** package: no stub, no ``PYTHONPATH`` shadow, no fake repository root. It is
cross-platform on purpose (the same reason ``test_schedule_contract.py`` exists): the entry
point is a property of the package, not of macOS, and the macOS-gated module is deselected on
the Linux CI matrix.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

from threaddigest import __version__

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_SH = REPO_ROOT / "deploy" / "launchd" / "run.sh"

#: How the wrapper spells the job it runs: ``"$PY" -m <module> <job>``. Read out of the script
#: rather than restated, so a wrapper that changes its invocation changes what is tested here.
WRAPPER_MODULE = re.compile(r'set -- "\$PY" -m (?P<module>[\w.]+) (?P<job>run|doctor)\b')


def _module_the_wrapper_runs() -> str:
    text = RUN_SH.read_text(encoding="utf-8")
    modules = {match["module"] for match in WRAPPER_MODULE.finditer(text)}
    assert modules == {"threaddigest"}, (
        f"run.sh runs {sorted(modules)} as a module; this test knows only `-m threaddigest`. "
        "If the wrapper now calls the console script by path instead, replace this module."
    )
    return modules.pop()


def test_the_wrapper_runs_the_collector_and_the_doctor_as_a_module() -> None:
    """Both jobs go through ``-m``, which is why the entry point below is load-bearing."""
    text = RUN_SH.read_text(encoding="utf-8")
    assert {match["job"] for match in WRAPPER_MODULE.finditer(text)} == {"run", "doctor"}


def test_python_m_threaddigest_starts_and_prints_the_version() -> None:
    """The one line the deployment gate could not see: the package is runnable with ``-m``.

    ``--version`` is eager and touches neither settings nor the database, so this asserts the
    entry point and nothing else. Before ``src/threaddigest/__main__.py`` existed this exited
    1 with "No module named threaddigest.__main__".
    """
    result = subprocess.run(
        [sys.executable, "-m", _module_the_wrapper_runs(), "--version"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        cwd=REPO_ROOT,
        check=False,
        timeout=120,
    )

    assert result.returncode == 0, f"stdout={result.stdout!r} stderr={result.stderr!r}"
    assert result.stdout.strip() == f"threaddigest {__version__}"
    assert result.stderr == ""


def test_the_module_entry_point_and_the_console_script_run_the_same_app() -> None:
    """``pyproject.toml``'s ``threaddigest`` script and ``-m threaddigest`` are one object.

    A second Typer application, or a ``__main__`` that rebuilt the command tree, would let the
    scheduled job and the developer's shell diverge silently -- the shape of failure B1 was.
    """
    from threaddigest import __main__, cli

    assert __main__.app is cli.app
