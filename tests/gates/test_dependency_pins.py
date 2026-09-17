"""Gate: dependency declarations that carry a behavioural contract keep their bound.

Two contracts live here. The first is PRAW (external round one, reviewer C-11): PRAW 8's
``replace_more`` discovers
up to 100 comments per request where PRAW 7 discovered 20, and the collector's request budgeting
assumes the tested major. The bound ``praw>=8,<9`` makes a major upgrade a deliberate change
gated behind replaying the adapter fixtures on the probe day. The test-methodology seat found the
pin had shipped with no positive control, so an accidental loosening back to ``praw>=7.8`` (the
exact regression C-11 fixed) was invisible; this reads the invariant (``pyproject.toml``) and goes
red on any spec that admits PRAW 9 or drops the lower bound.

The second is ``tzdata`` (KI-031, the first CI run on 2026-09-16). ``display_timezone`` is
resolved with ``zoneinfo``, which reads the host's IANA database; a slim Linux container has
none, so a zone every developer machine knows was unknown there. The database is therefore a
runtime dependency of this package rather than an assumption about the machine, and the test
below proves the resolution with the host's database taken away, in both directions.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.version import Version

REPO_ROOT = Path(__file__).resolve().parents[2]
#: A zone the shipped configuration does not use, so the proof is about the database and not
#: about ``UTC`` (which ``core.digest`` answers without any lookup at all).
ZONE = "America/Los_Angeles"
#: Hides the ``tzdata`` package from an interpreter without uninstalling it: the positive
#: control for a machine that has neither a system database nor the package.
HIDE_TZDATA = """
import sys


class _Hide:
    def find_spec(self, name, path=None, target=None):
        if name == "tzdata" or name.startswith("tzdata."):
            msg = "tzdata hidden by the positive control"
            raise ImportError(msg)
        return None


sys.meta_path.insert(0, _Hide())
"""

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


def _without_a_system_zone_database(prelude: str, empty: Path) -> subprocess.CompletedProcess[str]:
    """Resolve ``ZONE`` in a child whose ``zoneinfo`` search path is one directory that is not
    there, which is what a slim Linux container looks like to ``zoneinfo``."""
    script = (
        f"{prelude}\n"
        "import zoneinfo\n"
        f"assert zoneinfo.TZPATH == ({str(empty)!r},), zoneinfo.TZPATH\n"
        "from threaddigest.core.digest import known_display_timezone\n"
        f"print(known_display_timezone({ZONE!r}))\n"
    )
    return subprocess.run(
        [sys.executable, "-c", script],
        env={**os.environ, "PYTHONTZPATH": str(empty)},
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )


def test_the_zone_database_is_a_dependency_not_an_assumption_about_the_host(tmp_path: Path) -> None:
    """KI-031: the shipped zone database travels with the package.

    A runtime dependency, not a dev one -- the digest renders on whatever machine runs the
    schedule, and that machine may be a container with no ``/usr/share/zoneinfo``.
    """
    _requirement("tzdata")  # raises if it is not in [project].dependencies
    empty = tmp_path / "no-system-zoneinfo"  # deliberately never created
    proc = _without_a_system_zone_database("", empty)
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == ZONE


def test_positive_control_without_the_package_the_zone_is_unknown(tmp_path: Path) -> None:
    """The other half: with neither the host's database nor the package, the same call fails
    exactly the way the first CI run failed, so the test above is proving the package and not
    some fallback of its own."""
    empty = tmp_path / "no-system-zoneinfo"
    proc = _without_a_system_zone_database(HIDE_TZDATA, empty)
    assert proc.returncode != 0
    assert f"unknown display_timezone {ZONE!r}" in proc.stderr
