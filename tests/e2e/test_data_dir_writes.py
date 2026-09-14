"""DB-19's M1a half: a full run through the CLI writes nothing outside its data directory
(design-round5.md section 16's DB-19 note, verbatim recipe).

``INSIGHTMINER_DATA_DIR`` is already a tmp path outside the repo (``tests/conftest.py``'s
autouse ``isolated_data_dir``), so the snapshot below is of the REPO ROOT: a full run must
change nothing in it at all.

:func:`_snapshot` takes the root it walks, which is what keeps this file honest both ways:
the run test reads the real repository and writes nothing, and the positive control writes
into a tmp tree of its own. No test here creates a file inside the real ``data/`` directory
(panel P2-5).
"""

from __future__ import annotations

import os
from pathlib import Path

from insightminer import cli
from insightminer.adapters.reddit_fake import FakeRedditGateway

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Directories that legitimately change during test/dev tooling and carry nothing an
#: operator's data lives in. Neither "data" nor "config" is in this list (section 16's
#: DB-19 note): a write there must be caught, not excused.
VOLATILE: tuple[str, ...] = (
    ".git",
    ".venv",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".hypothesis",
    ".import_linter_cache",
    ".build",
    ".ratchets",
    "__pycache__",
)

Snapshot = dict[str, tuple[int, int]]


def _snapshot(root: Path) -> Snapshot:
    """``{relative path: (size, st_mtime_ns)}`` for every file under ``root``, pruning
    :data:`VOLATILE` directories before descending into them (never just filtering their
    results out afterward -- ``.venv`` alone is hundreds of megabytes).
    """
    out: Snapshot = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in VOLATILE]
        for name in filenames:
            if name == ".coverage":
                continue
            path = Path(dirpath) / name
            rel = path.relative_to(root)
            try:
                stat = path.stat()
            except OSError:
                continue
            out[str(rel)] = (stat.st_size, stat.st_mtime_ns)
    return out


def test_volatile_exclusion_list_contains_neither_data_nor_config() -> None:
    """A write into ``data/`` or ``config/`` must be detectable, never excused away."""
    assert "data" not in VOLATILE
    assert "config" not in VOLATILE


def test_a_full_run_changes_no_file_outside_the_data_dir(
    cli_runner, db_at_head: Path, loaded_gateway: FakeRedditGateway, demo_fixture_path: Path
) -> None:
    """The one test that looks at the real repository, and it only ever READS it."""
    before = _snapshot(REPO_ROOT)
    result = cli_runner.invoke(
        cli.app, ["run", "--gateway", "fake", "--fixture", str(demo_fixture_path)]
    )
    assert result.exit_code == 0, result.output
    after = _snapshot(REPO_ROOT)
    assert after == before


def test_control_a_write_into_a_data_directory_is_detected(tmp_path: Path) -> None:
    """The positive control: the comparison must go red on a real write, so it cannot be
    passing by looking at nothing.

    Run against a tmp tree shaped like the repository, never the repository itself (panel
    P2-5). The control used to write ``REPO_ROOT/data/probe`` -- a real file inside the real
    data directory, created by the very test file whose subject is that a run never writes
    there. The ``finally`` removed it, but a crash, a ``SIGKILL``, or a failure between the
    two statements left it behind, and G19's rule is about the write, not the residue.

    The ``.git`` file proves the :data:`VOLATILE` prune is doing its job in the same breath:
    a volatile directory's contents never enter a snapshot, so they can never make one
    differ.
    """
    root = tmp_path / "repo"
    (root / "data").mkdir(parents=True)
    (root / "data" / "insightminer.db").write_bytes(b"a database that was already there")
    (root / ".git").mkdir()
    (root / ".git" / "index").write_bytes(b"volatile")

    before = _snapshot(root)
    (root / "data" / "probe").write_bytes(b"x")
    after = _snapshot(root)

    assert str(Path(".git") / "index") not in before
    assert after != before
    assert set(after) - set(before) == {str(Path("data") / "probe")}
