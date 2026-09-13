"""Makes ``tests`` a regular package so ``tests.db.sqlhelp`` is importable from any
other test package (``tests/services/``, ``tests/e2e/``, ``tests/gates/``) under plain
``pytest`` (the console script), not only under ``python -m pytest``.

See design-round5.md §2.2 / §2.3 and ``pyproject.toml``'s ``pythonpath = ["."]``.
"""

from __future__ import annotations
