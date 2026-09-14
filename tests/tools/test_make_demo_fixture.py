"""``tools/make_demo_fixture.py``: the demo corpus is generated, so the generator carries
the properties the committed file used to carry by existing.

A corpus in git is inspectable and stable by definition; a generated one is neither unless
something says so. These tests say it: the script produces identical bytes on two runs (run
as a script, through the same command line ``make fixture`` uses, not through an import that
could hide state), its sources are exactly ``config/seed.yaml``'s, and its own corpus check
is not a no-op.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from tools.make_demo_fixture import EXPECTED_POSTS, SOURCES, check_corpus

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "tools" / "make_demo_fixture.py"
SEED_FILE = REPO_ROOT / "config" / "seed.yaml"


def _generate(destination: Path) -> bytes:
    """Run the generator the way ``make fixture`` does and return what it wrote."""
    result = subprocess.run(
        [sys.executable, str(SCRIPT), str(destination)],
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
    ``created_utc`` values from constants, so a stray ``random``, ``time.time()`` or dict
    iteration order creeping in would show up here as a diff -- and would otherwise show up
    as an end-to-end suite that passes on one machine and not another.
    """
    first = _generate(tmp_path / "first.json")
    second = _generate(tmp_path / "second.json")
    assert first == second
    assert len(first) > 100_000, "the corpus is suspiciously small for ~240 posts"


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
