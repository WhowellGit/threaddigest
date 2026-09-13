"""Shared fixtures for adapter tests."""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from insightminer.adapters.reddit_fake import FakeRedditGateway

BASE = 1_757_700_000  # 2025-09-12T18:40:00Z; seeded posts are spaced one minute apart from here


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
