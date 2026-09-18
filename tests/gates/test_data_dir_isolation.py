"""Gate G19: tests can never run against the real data directory, and no write leaves it.

Positive controls construct the bad state (pytest loaded, no ``THREADDIGEST_DATA_DIR``)
and assert that ``Settings`` refuses before anything is created, in-process and across the
subprocess seam (``PYTEST_CURRENT_TEST`` is inherited by children). The negative controls
prove the refusal is keyed on the invariant, not on pytest merely being present: an
explicit temp ``data_dir``, the opt-in variable, and a plain interpreter all construct.

Since 2026-09-17 the gate carries the other half of irreversible rule 1 as well: a *path* an
operator supplies cannot make a write land outside the resolved directory. ``probe
--save-fixture NAME`` joined the operator's name straight onto ``<data_dir>/probe/``, and
``pathlib`` lets a traversing or absolute right operand win, so the name
``../tests/fixtures/json/captures/x`` wrote a raw capture into the committed fixture tree --
the one step ``promotion_command`` exists to keep deliberate (KI-047, the 2026-09-17 code
panel's seat B finding B3). The name check and the confinement check are both asserted here,
with a control that the unchecked join really did escape.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from threaddigest.services import probe
from threaddigest.settings import DataDirRefused, Settings, default_data_dir

pytestmark = pytest.mark.gate("G19")

REPO_ROOT = Path(__file__).resolve().parents[2]
CHILD = (
    "from threaddigest.settings import Settings, default_data_dir\n"
    "s = Settings()\n"
    "assert s.data_dir == default_data_dir().resolve(), s.data_dir\n"
    "print(s.data_dir)\n"
)


def _listing(path: Path) -> list[str] | None:
    return sorted(p.name for p in path.iterdir()) if path.exists() else None


def _child_env(**overrides: str) -> dict[str, str]:
    """A child environment with no pytest, coverage, or threaddigest variables."""
    env = {
        name: value
        for name, value in os.environ.items()
        if not name.startswith(("THREADDIGEST_", "PYTEST_", "COV_CORE_"))
    }
    env.update(overrides)
    return env


def test_refuses_default_data_dir_while_pytest_is_loaded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("THREADDIGEST_DATA_DIR")
    monkeypatch.delenv("THREADDIGEST_ALLOW_REAL_DATA_DIR", raising=False)
    assert "pytest" in sys.modules
    before = _listing(default_data_dir())

    with pytest.raises(DataDirRefused, match="THREADDIGEST_DATA_DIR"):
        Settings()

    assert _listing(default_data_dir()) == before


def test_refuses_when_env_points_at_the_default_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("THREADDIGEST_DATA_DIR", str(default_data_dir()))
    with pytest.raises(DataDirRefused):
        Settings()


def test_explicit_temp_data_dir_constructs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("THREADDIGEST_DATA_DIR")
    resolved = Settings(data_dir=tmp_path)
    assert resolved.data_dir == tmp_path.resolve()


def test_opt_in_variable_allows_the_default_dir(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("THREADDIGEST_DATA_DIR")
    monkeypatch.setenv("THREADDIGEST_ALLOW_REAL_DATA_DIR", "1")
    before = _listing(default_data_dir())

    resolved = Settings()

    assert resolved.data_dir == default_data_dir().resolve()
    assert _listing(default_data_dir()) == before


def test_plain_interpreter_without_pytest_constructs_normally() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", CHILD],
        env=_child_env(),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == str(default_data_dir().resolve())


def test_child_process_under_pytest_current_test_refuses() -> None:
    proc = subprocess.run(
        [sys.executable, "-c", CHILD],
        env=_child_env(PYTEST_CURRENT_TEST="tests/gates/x.py::test (call)"),
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    assert proc.returncode != 0
    assert "DataDirRefused" in proc.stderr


# --- KI-047: a supplied name cannot steer a write out of the resolved directory ---------------

#: Names ``probe --save-fixture`` must refuse. Each is one of the four shapes that can move a
#: write: a traversal, a deeper traversal, an absolute path, and a sub-path; plus the two
#: directory names that match the safe alphabet but name a directory rather than a file, and
#: the empty name, which would write ``.json``.
UNSAFE_FIXTURE_NAMES: tuple[str, ...] = (
    "../escape",
    "../../escape/pwned",
    "../tests/fixtures/json/captures/promoted_by_accident",
    "sub/dir/name",
    ".",
    "..",
    "",
    "has space",
    "quote'd",
)

#: The names the probe day actually uses (runbook § 9): the negative control, so the guard is
#: keyed on the shape that can escape and not on anything unfamiliar.
SAFE_FIXTURE_NAMES: tuple[str, ...] = (
    "about_premiere",
    "listing-premiere-new",
    "tree.t3_abc123",
    "P-08",
)


def _capture() -> probe.Capture:
    return probe.Capture(mode="about", target="premiere", payload={"kind": "t5"}, requests_used=1)


def _tree(root: Path) -> set[Path]:
    return {path for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("name", UNSAFE_FIXTURE_NAMES)
def test_probe_save_refuses_a_name_that_is_not_one_safe_segment(tmp_path: Path, name: str) -> None:
    """The refusal, and that nothing at all was written -- inside the data dir or out of it."""
    data_dir = tmp_path / "resolved"
    data_dir.mkdir()
    (tmp_path / "escape").mkdir()
    before = _tree(tmp_path)

    with pytest.raises(probe.UnsafeFixtureTargetError) as raised:
        probe.save(_capture(), data_dir=data_dir, name=name)

    assert name in str(raised.value) or not name, "the refusal must name what it refused"
    assert _tree(tmp_path) == before, "a refused save still wrote something"


def test_probe_save_refuses_an_absolute_name_and_writes_nothing_there(tmp_path: Path) -> None:
    """An absolute right operand wins a ``pathlib`` join outright, so it is its own case."""
    data_dir = tmp_path / "resolved"
    data_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    absolute = str(outside / "absolute")

    with pytest.raises(probe.UnsafeFixtureTargetError):
        probe.save(_capture(), data_dir=data_dir, name=absolute)

    assert _tree(outside) == set()


@pytest.mark.parametrize("name", SAFE_FIXTURE_NAMES)
def test_probe_save_accepts_the_names_the_probe_day_uses(tmp_path: Path, name: str) -> None:
    """The negative control: the guard refuses a shape, not an unfamiliar-looking name."""
    written = probe.save(_capture(), data_dir=tmp_path, name=name)

    assert written == tmp_path / probe.PROBE_SUBDIR / f"{name}.json"
    assert written.is_file()


def test_positive_control_the_unchecked_join_really_did_escape(tmp_path: Path) -> None:
    """The guard is not vacuous: the join it replaced resolves outside the data directory.

    This is the pre-fix behaviour stated as an assertion rather than as a memory of one --
    ``probe_dir / f"{name}.json"`` with a traversing name lands in the repository tree, which
    is what made ``--save-fixture ../tests/fixtures/json/captures/x`` write a raw capture
    straight into committed history.
    """
    data_dir = (tmp_path / "resolved").resolve()
    probe_dir = data_dir / probe.PROBE_SUBDIR
    escaped = (probe_dir / f"{'../../escape/pwned'}.json").resolve()

    assert not escaped.is_relative_to(probe_dir)
    assert not escaped.is_relative_to(data_dir)
    assert escaped.parent == (tmp_path / "escape").resolve()


def test_probe_save_refuses_a_probe_directory_that_is_a_symlink_out_of_the_data_tree(
    tmp_path: Path,
) -> None:
    """The second guard, which no check of the *name* could make: a safe name, a moved dir.

    The name is exactly the one the probe day uses; what has moved is ``<data_dir>/probe``
    itself. Without the confinement check the capture lands wherever the link points, which is
    the same rule-1 violation by another route.
    """
    data_dir = tmp_path / "resolved"
    data_dir.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (data_dir / probe.PROBE_SUBDIR).symlink_to(outside, target_is_directory=True)

    with pytest.raises(probe.UnsafeFixtureTargetError, match="resolves to"):
        probe.save(_capture(), data_dir=data_dir, name="about_premiere")

    assert _tree(outside) == set()
