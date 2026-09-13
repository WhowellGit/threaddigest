"""``db/backup.py`` with no spec id (design-round5.md §10.1, §16): online backup under a
concurrent writer, sha256, ``quick_check``, restore swap, and WAL sidecar removal.

``tests/db/**`` is the one place outside ``src/insightminer/db/**`` where ``sqlite3`` and
``text()`` are lifted from ``TID251`` -- but this file needs neither: sources are built
with the project's own ``engine_for`` and Core statements, and ``db.backup`` is exercised
only through its public functions.
"""

from __future__ import annotations

import hashlib
import sqlite3
from pathlib import Path

import pytest

from insightminer.db.backup import (
    BACKUP_SUFFIXES,
    foreign_key_check,
    integrity_check,
    online_backup,
    quick_check,
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


def test_backup_suffixes_are_the_wal_and_shm_sidecars() -> None:
    assert BACKUP_SUFFIXES == ("-wal", "-shm")


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
