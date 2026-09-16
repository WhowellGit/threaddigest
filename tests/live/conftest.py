"""The opt-in live suite (tranche B): tests that talk to Reddit with real credentials.

Nothing here runs under ``make check``: every test in this directory carries the ``live`` marker,
which the root ``addopts`` deselect, and ``--block-network`` refuses any socket a test opens. The
one home for the live invocation is ``make test-live``, which loads ``.env``, selects the marker,
and lifts the network block for Reddit's hosts only.

Ruled 2026-09-16 (the readiness seat's F1): without this file a live test could not pass even with
credentials, because the root ``isolated_data_dir`` fixture strips every ``THREADDIGEST_*``
variable from the environment, credentials included. This override keeps the three Reddit
credential variables and nothing else, and still points the process at a temporary data
directory, so a live test can never touch the real one.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

ENV_PREFIX = "THREADDIGEST_"
KEPT_PREFIX = "THREADDIGEST_REDDIT_"


def keep_credentials_only(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Strip every project variable except the Reddit credentials; isolate the data directory."""
    for name in list(os.environ):
        if name.startswith(ENV_PREFIX) and not name.startswith(KEPT_PREFIX):
            monkeypatch.delenv(name)
    data_dir = tmp_path / "data"
    data_dir.mkdir(exist_ok=True)
    monkeypatch.setenv(f"{ENV_PREFIX}DATA_DIR", str(data_dir))
    return data_dir


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Overrides the root fixture of the same name for this directory only."""
    yield keep_credentials_only(monkeypatch, tmp_path)
