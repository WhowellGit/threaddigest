"""Shared fixtures.

Data-directory isolation (docs/learnings rank 1, guard G19): every test runs with
``INSIGHTMINER_DATA_DIR`` pointing at a fresh temp directory and with every other
``INSIGHTMINER_*`` variable removed, so a developer's real ``.env`` values never reach a
test and the real ``data/`` directory is never written. ``Settings`` refuses the default
data directory while pytest is loaded, so a test that bypasses this fixture fails instead
of touching live data.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest

from insightminer.settings import Settings

ENV_PREFIX = "INSIGHTMINER_"


@pytest.fixture(autouse=True)
def isolated_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Path]:
    """Point the process at a fresh data directory and clear inherited settings."""
    for name in list(os.environ):
        if name.startswith(ENV_PREFIX):
            monkeypatch.delenv(name)
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setenv(f"{ENV_PREFIX}DATA_DIR", str(data_dir))
    yield data_dir


@pytest.fixture
def settings(isolated_data_dir: Path) -> Settings:
    """Settings resolved from the isolated environment and the shipped settings.yaml."""
    resolved = Settings()
    assert resolved.data_dir == isolated_data_dir.resolve()
    return resolved
