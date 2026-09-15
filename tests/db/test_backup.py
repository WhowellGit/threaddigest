"""``db/backup.py`` with no spec id (design-round5.md §10.1, §16): online backup under a
concurrent writer, sha256, ``quick_check``, restore swap, and WAL sidecar removal.

``tests/db/**`` is the one place outside ``src/insightminer/db/**`` where ``sqlite3`` and
``text()`` are lifted from ``TID251`` -- but this file needs neither: sources are built
with the project's own ``engine_for`` and Core statements, and ``db.backup`` is exercised
only through its public functions.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from pathlib import Path

import pytest

from insightminer.db.backup import (
    BACKUP_SUFFIXES,
    foreign_key_check,
    integrity_check,
    online_backup,
    quick_check,
    remove_sidecars,
    restore,
    sha256_of,
)
from insightminer.db.engine import engine_for
from insightminer.db.schema import Base
from insightminer.db.schema_dump import migrate_to_head


def _seed_db(path: Path) -> None:
    engine = engine_for(path)
    try:
        migrate_to_head(engine)
        ui_state = Base.metadata.tables["ui_state"]
        with engine.begin() as conn:
            conn.execute(ui_state.insert().values(key="seed", value="v1", updated_at=1))
    finally:
        engine.dispose()


def test_online_backup_produces_a_verified_copy(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    dest = tmp_path / "backup.db"
    _seed_db(source)

    result = online_backup(source, dest)

    assert dest.exists()
    assert result.path == dest
    assert result.sha256 == sha256_of(dest)
    assert result.integrity == "ok"
    assert result.size_bytes == dest.stat().st_size


def test_online_backup_leaves_no_partial_file_visible_under_its_final_name(
    tmp_path: Path,
) -> None:
    """The destination is written to ``<name>.partial`` and ``os.replace``d into place."""
    source = tmp_path / "source.db"
    dest = tmp_path / "backup.db"
    _seed_db(source)

    online_backup(source, dest)

    assert not dest.with_name(dest.name + ".partial").exists()


def test_online_backup_succeeds_while_the_source_has_an_uncommitted_writer(
    tmp_path: Path,
) -> None:
    """DB-41's mechanism: ``sqlite3.Connection.backup()`` is an online API, so a concurrent
    writer holding an open (uncommitted) transaction cannot tear the copy.
    """
    source = tmp_path / "source.db"
    dest = tmp_path / "backup.db"
    _seed_db(source)

    writer = engine_for(source)
    try:
        # AUTOCOMMIT: `engine_for` emits its own BEGIN from the `begin` event, and
        # `BEGIN IMMEDIATE` inside that is "cannot start a transaction within a transaction".
        with writer.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql("BEGIN IMMEDIATE")
            conn.exec_driver_sql(
                "INSERT INTO ui_state (key, value, updated_at) VALUES ('uncommitted', 'x', 1)"
            )
            result = online_backup(source, dest)
            conn.exec_driver_sql("ROLLBACK")
    finally:
        writer.dispose()

    assert result.integrity == "ok"
    assert quick_check(dest) == "ok"


def test_sha256_of_matches_hashlib_over_the_file_bytes(tmp_path: Path) -> None:
    source = tmp_path / "source.db"
    _seed_db(source)

    assert sha256_of(source) == hashlib.sha256(source.read_bytes()).hexdigest()


def test_quick_check_and_integrity_check_report_ok_on_a_healthy_file(tmp_path: Path) -> None:
    path = tmp_path / "healthy.db"
    _seed_db(path)

    assert quick_check(path) == "ok"
    assert integrity_check(path) == "ok"


def test_restore_swaps_the_file_and_removes_wal_sidecars(tmp_path: Path) -> None:
    backup_path = tmp_path / "backup.db"
    destination = tmp_path / "live.db"
    _seed_db(backup_path)
    _seed_db(destination)

    # A stale WAL/SHM pair next to the destination must not survive the restore -- a stale
    # WAL beside a restored main file is a silently corrupt database.
    destination.with_name(destination.name + "-wal").write_bytes(b"stale-wal")
    destination.with_name(destination.name + "-shm").write_bytes(b"stale-shm")

    expected_sha = sha256_of(backup_path)
    restore(backup_path, destination)

    assert sha256_of(destination) == expected_sha
    assert not destination.with_name(destination.name + "-wal").exists()
    assert not destination.with_name(destination.name + "-shm").exists()


def _crash_left_wal(live: Path) -> None:
    """Put a database at ``live`` whose only committed row lives in its ``-wal``: written with
    auto-checkpoint off, then the three files copied under the new name before the writer
    closes, which is what a crash leaves behind (KI-015)."""
    source = live.with_name("source-" + live.name)
    conn = sqlite3.connect(source)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA wal_autocheckpoint=0")
        conn.execute("CREATE TABLE notes(t TEXT)")
        conn.commit()
        conn.execute("INSERT INTO notes VALUES ('committed note')")
        conn.commit()
        for suffix in ("", *BACKUP_SUFFIXES):
            live.with_name(live.name + suffix).write_bytes(
                source.with_name(source.name + suffix).read_bytes()
            )
    finally:
        conn.close()


def test_a_restore_whose_copy_fails_leaves_the_live_database_and_its_log_untouched(
    tmp_path: Path,
) -> None:
    """KI-015: the copy is the step that can fail (a missing or unreadable backup, a full
    disk), and nothing live may be touched before it has succeeded. A crash-left ``-wal``
    holds committed transactions; deleting it first turned a failed restore into data loss."""
    live = tmp_path / "live.db"
    _crash_left_wal(live)
    wal = live.with_name(live.name + "-wal")
    wal_before = wal.read_bytes()

    with pytest.raises(FileNotFoundError):
        restore(tmp_path / "missing-backup.db", live)

    assert wal.read_bytes() == wal_before  # the log is exactly as the crash left it
    assert not live.with_name(live.name + ".restoring").exists()
    conn = sqlite3.connect(live)
    try:
        assert conn.execute("SELECT count(*) FROM notes").fetchone()[0] == 1
    finally:
        conn.close()


def test_backup_suffixes_are_the_wal_and_shm_sidecars() -> None:
    assert BACKUP_SUFFIXES == ("-wal", "-shm")


# --- panel P2-9: the atomic rename is not a durable one on its own ----------------------------

Ident = tuple[int, int]


def _ident(path: Path) -> Ident:
    """``(device, inode)``: what identifies a file or directory across a rename.

    The staged file keeps its inode when ``os.replace`` moves it to the destination, so an
    ``fsync`` recorded before the rename and the destination afterwards are the same object.
    """
    info = path.stat()
    return (info.st_dev, info.st_ino)


def _fsync_spy(monkeypatch: pytest.MonkeyPatch) -> list[Ident]:
    """Record every ``fsync``ed object by identity, then perform the real sync.

    ``monkeypatch.setattr`` on the ``os`` module attribute, never ``mock.patch``, which the
    working agreement confines to ``tests/adapters/``. A descriptor tells us nothing by
    itself, so the spy resolves it with ``os.fstat`` while it is still open -- which is also
    what makes "the file AND its directory" assertable rather than just a call count.
    """
    seen: list[Ident] = []
    real_fsync = os.fsync

    def spy(fd: int) -> None:
        info = os.fstat(fd)
        seen.append((info.st_dev, info.st_ino))
        real_fsync(fd)

    monkeypatch.setattr(os, "fsync", spy)
    return seen


def test_online_backup_fsyncs_the_copy_and_its_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``os.replace`` is atomic for readers but says nothing about durability: without these
    two syncs a power loss can leave the ``backups`` row and its recorded ``sha256`` pointing
    at a file that is empty, truncated or absent.
    """
    source = tmp_path / "source.db"
    dest_dir = tmp_path / "backups"
    dest_dir.mkdir()
    dest = dest_dir / "backup.db"
    _seed_db(source)
    seen = _fsync_spy(monkeypatch)

    online_backup(source, dest)

    assert _ident(dest) in seen, "the copy's bytes were never flushed"
    assert _ident(dest_dir) in seen, "the rename was never flushed"


def test_restore_fsyncs_the_restored_file_and_its_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A restore is the recovery path, so the crash during it is the one that matters."""
    live_dir = tmp_path / "live"  # not "data": the autouse isolation fixture owns that name
    live_dir.mkdir()
    backup_path = tmp_path / "backup.db"
    destination = live_dir / "live.db"
    _seed_db(backup_path)
    _seed_db(destination)
    seen = _fsync_spy(monkeypatch)

    restore(backup_path, destination)

    assert _ident(destination) in seen, "the restored bytes were never flushed"
    assert _ident(live_dir) in seen, "the rename was never flushed"


def test_quick_check_opens_the_file_read_only(tmp_path: Path) -> None:
    """The copy is verified *after* its ``sha256`` was recorded, so the verification must not
    be able to change the bytes that hash describes. A read-write ``sqlite3.connect`` can
    replay a WAL into the main file and -- given a path that is not there -- invents an empty
    database; a read-only one leaves the file alone and reports the missing one.

    The empty ``-wal`` / ``-shm`` pair a read-only connection needs in order to read a
    WAL-mode database at all is not part of that promise, which is why ``remove_sidecars``
    exists and why ``services/migrate.py`` calls it on the copy.
    """
    path = tmp_path / "healthy.db"
    _seed_db(path)
    before = sha256_of(path)

    assert quick_check(path) == "ok"

    assert sha256_of(path) == before, "quick_check changed the bytes it was verifying"
    remove_sidecars(path)
    assert sha256_of(path) == before

    missing = tmp_path / "not-there.db"
    assert quick_check(missing) != "ok"
    assert not missing.exists(), "quick_check created a database out of a typo'd path"


def test_remove_sidecars_keeps_the_file_and_removes_the_pair(tmp_path: Path) -> None:
    """The tidy-up ``services/migrate.py`` performs on a pre-migration copy."""
    path = tmp_path / "copy.db"
    _seed_db(path)
    for suffix in BACKUP_SUFFIXES:
        path.with_name(path.name + suffix).write_bytes(b"left behind")

    remove_sidecars(path)

    assert path.is_file()
    assert [path.with_name(path.name + s).exists() for s in BACKUP_SUFFIXES] == [False, False]


def test_foreign_key_check_reports_an_orphan_row(tmp_path: Path) -> None:
    """``PRAGMA foreign_key_check`` is what ``db upgrade``'s post-migration check reads; it
    must report a planted orphan and stay empty on a clean file.
    """
    path = tmp_path / "orphan.db"
    _seed_db(path)
    assert foreign_key_check(path) == []

    engine = engine_for(path)
    try:
        # foreign_keys=OFF on the raw connection, outside any transaction, is the only way to
        # create the orphan the check is supposed to find (§2.3's exec_driver_sql exception).
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            conn.exec_driver_sql("PRAGMA foreign_keys=OFF")
            conn.exec_driver_sql(
                "INSERT INTO run_subreddits (run_pk, subreddit_pk) VALUES (999, 999)"
            )
    finally:
        engine.dispose()

    violations = foreign_key_check(path)
    assert len(violations) == 2, "the orphan breaks both of run_subreddits' foreign keys"
    assert all("run_subreddits" in violation for violation in violations)


def test_a_failed_copy_leaves_no_partial_file_behind(tmp_path: Path) -> None:
    """The ``.partial`` staging file is removed when the copy raises, so a failed backup can
    never be mistaken for a good one.
    """
    source = tmp_path / "source.db"
    _seed_db(source)
    unreachable = tmp_path / "no-such-directory" / "backup.db"

    with pytest.raises(sqlite3.OperationalError, match="unable to open database file"):
        online_backup(source, unreachable)

    assert not unreachable.exists()
    assert not unreachable.with_name(unreachable.name + ".partial").exists()
