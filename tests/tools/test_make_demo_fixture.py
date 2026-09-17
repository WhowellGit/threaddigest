"""``tools/make_demo_fixture.py``: the demo corpus is generated, so the generator carries
the properties the committed file used to carry by existing.

A corpus in git is inspectable and stable by definition; a generated one is neither unless
something says so. These tests say it: the script produces identical bytes on two runs of the
same day (run as a script, through the same command line ``make fixture`` uses, not through an
import that could hide state), its sources are exactly ``config/seed.yaml``'s, its newest post
is dated the day it was generated and no post is dated in the future, and its own corpus check
is not a no-op.
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
import yaml
from tools.make_demo_fixture import (
    EXPECTED_POSTS,
    SOURCES,
    check_corpus,
)

from threaddigest.services.report import WINDOW_DAYS

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "make_demo_fixture.py"
SEED_FILE = REPO_ROOT / "config" / "seed.yaml"

#: A day passed to ``--base`` so two runs can be compared byte for byte without the calendar
#: being part of the comparison. Any day would do; this is the fixed anchor the corpus carried
#: before the anchor became the current day.
PINNED_BASE = "2025-09-12"


def _generate(destination: Path, *, base: str | None = None) -> bytes:
    """Run the generator the way ``make fixture`` does and return what it wrote."""
    argv = [sys.executable, str(SCRIPT), str(destination)]
    if base is not None:
        argv += ["--base", base]
    result = subprocess.run(
        argv,
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
    )
    assert result.returncode == 0, result.stderr
    return destination.read_bytes()


def test_two_runs_produce_identical_bytes(tmp_path: Path) -> None:
    """Determinism, byte for byte. The fake gateway's ids come from a counter and its
    ``created_utc`` values from one anchor plus fixed offsets, so a stray ``random``, dict
    iteration order, or a second clock reading inside the builder would show up here as a
    diff -- and would otherwise show up as an end-to-end suite that passes on one machine and
    not another.

    ``--base`` pins the anchor at a day, because the anchor itself is a clock reading now (the
    test below is the one that holds it to the current day). The two runs still happen at two
    different instants, so a ``time.time()`` creeping into the builder is caught exactly as it
    was before the anchor moved: what the pin removes is the calendar, not the clock.
    """
    first = _generate(tmp_path / "first.json", base=PINNED_BASE)
    second = _generate(tmp_path / "second.json", base=PINNED_BASE)
    assert first == second
    assert len(first) > 100_000, "the corpus is suspiciously small for ~240 posts"


def test_the_default_anchor_ends_today_and_dates_no_post_in_the_future(tmp_path: Path) -> None:
    """The default anchor is the corpus's *end*, not its start: the newest generated post
    lands on today and nothing is dated after now, so the digest's window -- seven days back
    from the run that collected it (``services.report.WINDOW_DAYS``) -- means what it says.

    The defect this closes: the anchor used to be the corpus's *start* (midnight UTC of the
    day it was generated), so every source after the first drifted into the future -- a shape
    no real Reddit post has -- and the window held the entire corpus regardless of how old a
    source's offset said it was. Anchoring the end instead is asserted two ways: no timestamp
    exceeds "now", and the newest is within a day of it (both would fail against the old
    start-anchor, which put most of the corpus days to weeks into the future). The window
    itself is asserted too: the newest post (the largest offset, aivideo) falls inside it and
    the oldest (premiere's sticky, offset 0) falls outside it, so a corpus that happened to
    land in the window by some other route would not pass.
    """
    now_ts = int(datetime.now(tz=UTC).timestamp())
    data = json.loads(_generate(tmp_path / "default.json").decode("utf-8"))
    created = [int(post["created_utc"]) for post in data["posts"]]
    assert len(created) == EXPECTED_POSTS

    assert max(created) <= now_ts, "a generated post is dated in the future"
    assert now_ts - max(created) < 86_400, "the newest post is not within a day of now"

    window_start = now_ts - WINDOW_DAYS * 86_400
    assert max(created) >= window_start, "the newest post fell outside the digest window"
    assert min(created) < window_start, "the oldest post did not fall outside the digest window"


def test_the_generated_sources_are_exactly_the_seeded_subreddits() -> None:
    """The sweep drives off ``config/seed.yaml``; the fake gateway is built from this
    generator. Pinned at the *constants*, not only at the output file, so a drift is a red
    in this file rather than a demo run that quietly collects from two of three sources.
    """
    seeded = [
        name.lower() for name in yaml.safe_load(SEED_FILE.read_text(encoding="utf-8"))["subreddits"]
    ]
    generated = [source.name.lower() for source in SOURCES]
    assert generated == seeded


def test_check_corpus_rejects_a_corpus_that_disagrees_with_the_constants() -> None:
    """The generator checks its own output against its documented counts before writing.
    This is that check's positive control: a corpus missing a post must raise, or the check
    is decoration and the constants in the module docstring are unverified prose.
    """
    honest = {
        "subreddits": [{}] * len(SOURCES),
        "posts": [{}] * EXPECTED_POSTS,
        "comments": [],
    }
    check_corpus(honest)

    with pytest.raises(ValueError, match="generated corpus is"):
        check_corpus({**honest, "posts": [{}] * (EXPECTED_POSTS - 1)})
