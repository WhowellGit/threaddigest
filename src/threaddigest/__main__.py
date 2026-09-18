"""``python -m threaddigest``: the entry point the scheduled jobs run.

``deploy/launchd/run.sh`` invokes ``"$ROOT/.venv/bin/python" -m threaddigest run`` (and
``… doctor --alert-if-stale 5d``) rather than the console script, because the interpreter is
chosen by absolute path and a ``PATH`` lookup under launchd resolves to whatever launchd's
minimal ``PATH`` finds first. Without this module both jobs exited 1 before doing anything
(KI-045): the collector never ran and the hourly ``doctor``, the control that would have
noticed, died on the same line.

The same :data:`threaddigest.cli.app` the ``threaddigest`` console script names
(``pyproject.toml`` ``[project.scripts]``), imported rather than rebuilt: one command tree, so
the scheduled job and the operator's shell cannot diverge
(``tests/deploy/test_entry_point.py``).
"""

from __future__ import annotations

from threaddigest.cli import app

__all__ = ["app"]

if __name__ == "__main__":
    app()
