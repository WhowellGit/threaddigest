"""Gate: dependency pins that carry a behavioural contract keep their bound.

The one pin here is PRAW (external round one, reviewer C-11): PRAW 8's ``replace_more`` discovers
up to 100 comments per request where PRAW 7 discovered 20, and the collector's request budgeting
assumes the tested major. The bound ``praw>=8,<9`` makes a major upgrade a deliberate change
gated behind replaying the adapter fixtures on the probe day. The test-methodology seat found the
pin had shipped with no positive control, so an accidental loosening back to ``praw>=7.8`` (the
exact regression C-11 fixed) was invisible; this reads the invariant (``pyproject.toml``) and goes
red on any spec that admits PRAW 9 or drops the lower bound.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.gate("G53")


def _requirement(name: str) -> Requirement:
    with (REPO_ROOT / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    for spec in data["project"]["dependencies"]:
        req = Requirement(spec)
        if req.name == name:
            return req
    msg = f"{name} is not a project dependency"
    raise AssertionError(msg)


def test_praw_is_pinned_to_the_tested_major() -> None:
    req = _requirement("praw")
    # PRAW 9 must be excluded (the behavioural contract), and 8.x must be admitted.
    assert not req.specifier.contains("9.0.0"), f"praw spec {req.specifier} admits PRAW 9 (C-11)"
    assert req.specifier.contains("8.0.3"), f"praw spec {req.specifier} excludes the tested 8.x"
    # A lower bound of at least 8 (no accidental fall back to 7.x).
    assert not req.specifier.contains("7.8.0"), f"praw spec {req.specifier} still admits PRAW 7"


def test_installed_praw_satisfies_the_pin() -> None:
    """The resolved lockfile agrees with the spec, so the environment a run actually uses is on
    the tested major, not merely allowed to be."""
    import importlib.metadata

    installed = Version(importlib.metadata.version("praw"))
    assert installed.major == 8, f"installed praw is {installed}, not the tested 8.x"
    assert _requirement("praw").specifier.contains(installed)
