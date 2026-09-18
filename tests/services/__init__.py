"""Makes ``tests.services`` a regular package, for the reason ``tests/db/__init__.py`` is one.

Two layers of one module are tested in two places -- ``core/trees.py`` in
``tests/unit/test_trees.py`` and ``services/trees.py`` in ``tests/services/test_trees.py`` --
and pytest's default import mode gives a test file in a directory without ``__init__.py`` a
top-level module name, so the second of two identical basenames is a collection error rather
than a test. Naming the package is the fix pytest's own hint asks for; renaming one of the
files would name the layer twice (``tests/services/test_tree_stage.py``) and leave the next
pair of layers to trip over the same thing.
"""

from __future__ import annotations
