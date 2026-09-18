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
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import yaml
from tools.make_demo_fixture import (
    EXPECTED_POSTS,
    SOURCES,
    build_demo_fixture,
    check_corpus,
    day_start_utc,
    refuses_real_data_dir,
)

from threaddigest.services.report import WINDOW_DAYS
from threaddigest.settings import ALLOW_REAL_DATA_DIR, DataDirRefused, default_data_dir
from tools import make_demo_fixture

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


# --- KI-048: a fabricated corpus never lands in the real data directory ------------------------


def _stand_in_default_dir(monkeypatch: pytest.MonkeyPatch, root: Path) -> Path:
    """A temp directory standing in for ``<repo>/data``.

    The refusal is asserted against a stand-in, never against the real directory (the rule
    ``tests/e2e/test_data_dir_writes.py`` states for its own control): if this guard ever
    regresses, the test that notices must not be the one that wrote a fabricated 316-post
    corpus into the operator's data tree. The real path is covered by the pure predicate
    below, which cannot write anything at all.
    """
    stand_in = root / "repo" / "data"
    stand_in.mkdir(parents=True)
    monkeypatch.setattr(make_demo_fixture, "default_data_dir", lambda: stand_in)
    return stand_in


def test_the_generator_refuses_to_write_into_the_default_data_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`make fixture` used to write ``data/demo.json``, beside the operator's own database.

    ``default_data_dir()`` is ``<repo>/data`` and this generator creates its target's parent,
    so a fabricated corpus was written into the live data tree -- which future tooling
    (backups, exports, retention) has no reason to treat as foreign -- while the resolved data
    directory of the run that reads it is ``.build/run-data``, so the write was outside the
    resolved directory as well (panel finding B4). The refusal is keyed on the path, not on
    pytest, so it holds for `make fixture` in a plain shell too.
    """
    monkeypatch.delenv(ALLOW_REAL_DATA_DIR, raising=False)
    stand_in = _stand_in_default_dir(monkeypatch, tmp_path)
    base = day_start_utc(date.fromisoformat(PINNED_BASE))

    with pytest.raises(DataDirRefused, match=ALLOW_REAL_DATA_DIR):
        build_demo_fixture(stand_in / "demo.json", base=base)
    # A deeper path under the same directory is the same refusal, and the nested directory is
    # not created on the way to finding that out.
    with pytest.raises(DataDirRefused):
        build_demo_fixture(stand_in / "fixtures" / "demo.json", base=base)

    assert sorted(path.name for path in stand_in.rglob("*")) == []


def test_the_real_data_directory_is_refused_by_the_predicate_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real path, checked by the half of the guard that cannot write: a pure predicate."""
    monkeypatch.delenv(ALLOW_REAL_DATA_DIR, raising=False)
    assert refuses_real_data_dir(default_data_dir() / "demo.json") is True
    assert refuses_real_data_dir(default_data_dir() / "nested" / "demo.json") is True
    assert refuses_real_data_dir(REPO_ROOT / ".build" / "demo.json") is False


def test_the_generator_writes_anywhere_else_without_the_opt_in(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The negative control: the refusal is about one directory, not about writing at all."""
    monkeypatch.delenv(ALLOW_REAL_DATA_DIR, raising=False)
    _stand_in_default_dir(monkeypatch, tmp_path)

    written = build_demo_fixture(
        tmp_path / "build" / "demo.json", base=day_start_utc(date.fromisoformat(PINNED_BASE))
    )

    assert written.is_file()


def test_the_opt_in_variable_lifts_the_refusal(monkeypatch: pytest.MonkeyPatch) -> None:
    """The same escape hatch the settings refusal takes, named by the same one literal."""
    monkeypatch.setenv(ALLOW_REAL_DATA_DIR, "1")
    assert refuses_real_data_dir(default_data_dir() / "demo.json") is False


def test_the_makefile_target_writes_into_the_build_directory() -> None:
    """The fix's other half: ``RUN_FIXTURE`` names ``.build/``, which is git-ignored scratch.

    Read out of the Makefile rather than restated, so a target that moves back into ``data/``
    is red here even though the generator would also refuse it.
    """
    makefile = (REPO_ROOT / "Makefile").read_text(encoding="utf-8")
    assignment = next(line for line in makefile.splitlines() if line.startswith("RUN_FIXTURE ?="))
    assert assignment == "RUN_FIXTURE ?= $(BUILD_DIR)/demo.json", assignment
