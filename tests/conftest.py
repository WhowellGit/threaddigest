"""Shared fixtures.

Data-directory isolation (docs/learnings rank 1, guard G19): every test runs with
``THREADDIGEST_DATA_DIR`` pointing at a fresh temp directory and with every other
``THREADDIGEST_*`` variable removed, so a developer's real ``.env`` values never reach a
test and the real ``data/`` directory is never written. ``Settings`` refuses the default
data directory while pytest is loaded, so a test that bypasses this fixture fails instead
of touching live data.

``fake`` / ``seeded`` / ``BASE`` live here (design-round5.md §2.2) rather than under
``tests/adapters/`` so ``tests/services/`` and ``tests/e2e/`` share the one scenario
builder instead of each package inventing its own. ``demo_fixture_path`` joins them for the
same reason: ``tests/e2e/`` and ``tests/gates/`` both collect from the demo corpus, and a
generated corpus must be built once per session, not once per package.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from tools.make_demo_fixture import build_demo_fixture

from threaddigest.adapters.reddit_fake import FakeRedditGateway
from threaddigest.settings import Settings

ENV_PREFIX = "THREADDIGEST_"
BASE = 1_757_700_000  # 2025-09-12T18:40:00Z; seeded posts are spaced one minute apart from here


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


@pytest.fixture(scope="session")
def demo_fixture_path(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The demo corpus (every seeded subreddit, ~240 posts, one sticky, one crosspost, one
    unknown ``post_hint``, one deleted post -- section 11.7), **generated** into a session
    temp directory by ``tools/make_demo_fixture.py``.

    It is not a file in the repository. A generated corpus that is also committed is a
    second source of truth that drifts from its generator, and this one was 13,586 lines of
    JSON nobody read. The generator is the definition; ``make fixture`` writes the same
    bytes to the git-ignored ``data/demo.json`` for ``make run``.

    Session-scoped on purpose: every consumer takes it read-only (the CLI loads it, no test
    writes to it), so building it once is ~240 posts of work per session instead of per
    test. Its subreddit names come from the generator's ``SOURCES``, which
    ``tests/tools/test_make_demo_fixture.py`` holds to ``config/seed.yaml``.
    """
    return build_demo_fixture(tmp_path_factory.mktemp("demo-fixture") / "demo.json")


@pytest.fixture
def fake() -> Iterator[FakeRedditGateway]:
    """An empty scenario builder.

    At teardown every planted failure must have fired: a scenario that never reached its
    injected fault is a red, not a silent pass (panel-ingest rule 4).
    """
    gateway = FakeRedditGateway()
    yield gateway
    gateway.assert_no_unconsumed_injections()


@pytest.fixture
def seeded(fake: FakeRedditGateway) -> FakeRedditGateway:
    """r/premiere with 250 live posts (``post 0`` oldest ... ``post 249`` newest)."""
    fake.add_subreddit("premiere", subscribers=120_000)
    for i in range(250):
        fake.add_post(
            "premiere",
            title=f"post {i}",
            selftext=f"body {i}",
            author=f"u{i % 7}",
            created_utc=BASE + i * 60,
        )
    return fake
