"""Makes ``tests.db`` a regular package so ``tests.db.sqlhelp`` is importable from
``tests/services/``, ``tests/e2e/`` and ``tests/gates/`` (design-round5.md §2.2 / §2.3)."""

from __future__ import annotations
