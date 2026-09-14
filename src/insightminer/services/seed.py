"""``config/seed.yaml`` applied idempotently, scoped to one workspace (T14, §10.3 step 7).

Tranche A seeds **subreddits only** (§18.6). ``config/seed.yaml`` also carries a ``themes:``
key, which is read past without complaint: there is no theme table to seed into at M1a, and a
seed file that refused to load because of a key a later milestone owns would make ``db init``
fail for a reason the operator cannot act on. The ignoring is deliberate, so a test pins it.

The write itself is ``repo.seed_subreddits``: one
``ON CONFLICT(workspace_pk, name_lower) DO NOTHING``, which is what makes a second ``db init``
add nothing rather than duplicate three sources. Names are lowercased by the repo, so a file
that says ``VideoEditing`` and a row that says ``videoediting`` are the same source.

Consumed by ``db init`` today and by the web setup wizard at M2, which is why it takes a
``Connection`` rather than an ``Engine``: the caller owns the transaction, and ``db init``
needs the seed to live or die with its own (T14).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Final

import yaml
from sqlalchemy import Connection

from insightminer.db import repo

__all__ = ["DEFAULT_SEED_FILE", "apply_seed", "read_seed_names"]

#: The shipped seed file. ``src/insightminer/services/seed.py`` -> repo root -> ``config/``.
DEFAULT_SEED_FILE: Final = Path(__file__).resolve().parents[3] / "config" / "seed.yaml"

_SUBREDDITS_KEY: Final = "subreddits"


def read_seed_names(seed_path: Path | None = None) -> list[str]:
    """The subreddit names in ``seed_path`` (default: the shipped ``config/seed.yaml``).

    Raises :class:`TypeError` when the file is not a mapping or ``subreddits`` is not a list
    of strings -- a malformed seed must fail loudly at ``db init`` rather than quietly seed
    nothing and leave a workspace with no sources. A missing or empty ``subreddits`` key is
    not malformed, only empty.
    """
    path = DEFAULT_SEED_FILE if seed_path is None else seed_path
    with path.open(encoding="utf-8") as handle:
        loaded: Any = yaml.safe_load(handle)
    if loaded is None:
        return []
    if not isinstance(loaded, dict):
        msg = f"{path}: top level must be a mapping, got {type(loaded).__name__}"
        raise TypeError(msg)
    names = loaded.get(_SUBREDDITS_KEY) or []
    if not isinstance(names, list) or any(not isinstance(name, str) for name in names):
        msg = f"{path}: `{_SUBREDDITS_KEY}` must be a list of strings"
        raise TypeError(msg)
    return [str(name) for name in names]


def apply_seed(
    conn: Connection, *, workspace_pk: int, now: int, seed_path: Path | None = None
) -> int:
    """Add the seed file's sources to ``workspace_pk``; return how many rows were added.

    Idempotent and workspace-scoped: a name already present in **this** workspace is left
    alone, and a name present in another workspace is unrelated (``subreddits`` is one row
    per ``(workspace, name_lower)``, §5.1). ``themes:`` is ignored (§18.6).
    """
    return repo.seed_subreddits(
        conn, workspace_pk=workspace_pk, names=read_seed_names(seed_path), now=now
    )
