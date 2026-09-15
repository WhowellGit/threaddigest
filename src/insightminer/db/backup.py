"""Online backup, verification and atomic restore -- the only module importing ``sqlite3``.

``pyproject``'s ``TID251`` per-file-ignore lifts the banned-API rule for all of
``src/insightminer/db/**`` (ruff cannot lift one name), so the narrower rule -- *only this
module* imports ``sqlite3`` -- is enforced structurally by
``tests/gates/test_sqlite3_confined.py``.

Why the driver and not the engine: :meth:`sqlite3.Connection.backup` is SQLite's online
backup API, so a concurrent writer cannot tear the copy. SQLAlchemy exposes no equivalent,
and a file copy of a live WAL database is not a backup.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from urllib.parse import quote

__all__ = [
    "BACKUP_SUFFIXES",
    "BackupResult",
    "foreign_key_check",
    "integrity_check",
    "online_backup",
    "quick_check",
    "remove_sidecars",
    "restore",
    "sha256_of",
]

#: The sidecar files SQLite keeps next to a WAL database. A stale one beside a restored
#: main file is a silently corrupt database, so :func:`restore` removes both.
BACKUP_SUFFIXES: Final = ("-wal", "-shm")

#: Filenames use this stamp: no colons, which several platforms refuse.
TIMESTAMP_FORMAT: Final = "%Y%m%dT%H%M%SZ"

_READ_CHUNK: Final = 1 << 20


@dataclass(frozen=True, slots=True)
class BackupResult:
    path: Path
    sha256: str
    size_bytes: int
    integrity: str


def _sidecars(path: Path) -> tuple[Path, ...]:
    return tuple(path.with_name(path.name + suffix) for suffix in BACKUP_SUFFIXES)


def remove_sidecars(path: Path) -> None:
    """Delete ``path``'s ``-wal`` / ``-shm`` companions, keeping ``path`` itself.

    For a file **nothing else has open**: a backup copy, never a live database. Its one
    caller is ``services/migrate.py`` tidying the pre-migration copy after
    :func:`quick_check`, whose read-only connection can leave an empty pair behind -- a
    read-only connection is not allowed to delete them when it closes, and a stale sidecar
    beside a database file is precisely what :func:`restore` treats as dangerous.
    """
    for sidecar in _sidecars(path):
        sidecar.unlink(missing_ok=True)


def _remove_file_and_sidecars(path: Path) -> None:
    for candidate in (path, *_sidecars(path)):
        candidate.unlink(missing_ok=True)


def _fsync(path: Path) -> None:
    """``fsync`` one file or directory, by path.

    A directory is opened ``O_RDONLY`` and synced the same way, which is how a rename is made
    durable: ``os.replace`` only reaches the filesystem's own buffers.
    """
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _durable_replace(staged: Path, destination: Path) -> None:
    """``os.replace`` bracketed by the two syncs that make it survive a power loss.

    ``os.replace`` is atomic with respect to *readers* -- no reader ever sees a half file --
    but atomicity is not durability: after it returns, both the staged file's contents and
    the rename itself can still be sitting in the filesystem's buffers, so a crash can leave
    a ``backups`` row and a ``sha256`` pointing at a file that is empty, truncated, or absent.
    Both callers here are the last line of defence for a database, so both pay two syncs.

    **The directory sync goes after the rename, not before it** (panel P2-9, which asked for
    both "before ``os.replace``"). Syncing the parent beforehand cannot make a rename durable
    that has not happened yet; the recipe that works -- and the one every database uses -- is
    sync the file, rename, sync the directory. The finding's intent (neither the bytes nor the
    link may be lost to a crash) is what this implements.
    """
    _fsync(staged)
    os.replace(staged, destination)
    _fsync(destination.parent)


def _connect(path: Path, *, read_only: bool) -> sqlite3.Connection:
    """A driver connection to ``path``, read-only through a ``file:`` URI when asked."""
    if not read_only:
        return sqlite3.connect(path)
    return sqlite3.connect(f"file:{quote(str(path))}?mode=ro", uri=True)


def _pragma(path: Path, pragma: str, *, read_only: bool = False) -> list[tuple[object, ...]]:
    """Run one PRAGMA against ``path`` and return its rows.

    ``read_only=False`` connects read-write, which is what the two checks that run against a
    *live* database need: opening a WAL database read-only fails while its ``-shm`` file is
    missing, and a clean close removes any sidecar this created.

    A ``sqlite3.DatabaseError`` is **reported, not raised**. When the corruption reaches the
    schema page -- the ordinary shape of a damaged SQLite file -- the driver refuses to run
    the PRAGMA at all and raises ``database disk image is malformed`` instead of returning
    it as a row. Letting that escape would make the one caller that exists for corruption
    (``doctor``'s ``quick_check`` check, design-round5 §15.2) unreachable in exactly the case
    it is there for, and ``services/`` cannot catch the driver's exception class without
    importing ``sqlite3`` (§10.1). The message SQLite gives is the string these functions
    already promise to return.
    """
    try:
        connection = _connect(path, read_only=read_only)
    except sqlite3.DatabaseError as exc:
        return [(str(exc),)]
    try:
        return [tuple(row) for row in connection.execute(f"PRAGMA {pragma}").fetchall()]
    except sqlite3.DatabaseError as exc:
        return [(str(exc),)]
    finally:
        connection.close()


def online_backup(source: Path, destination: Path, *, pages: int = 0) -> BackupResult:
    """Copy the live database at ``source`` to ``destination`` through SQLite's backup API.

    The copy is written to ``<destination>.partial`` and ``os.replace``d into place, so a
    failed copy never leaves a plausible-looking backup file. ``pages=0`` copies the whole
    database in one step. The returned ``integrity`` is ``PRAGMA integrity_check`` on the
    copy -- the caller decides what a non-``"ok"`` result means.

    The rename goes through :func:`_durable_replace`, so the bytes and the link are both
    flushed to stable storage rather than left in the filesystem's buffers (panel P2-9).
    """
    partial = destination.with_name(destination.name + ".partial")
    _remove_file_and_sidecars(partial)
    replaced = False
    try:
        src = sqlite3.connect(source)
        try:
            dst = sqlite3.connect(partial)
            try:
                src.backup(dst, pages=pages)
            finally:
                dst.close()
        finally:
            src.close()
        integrity = integrity_check(partial)
        for sidecar in _sidecars(partial):
            sidecar.unlink(missing_ok=True)
        _durable_replace(partial, destination)
        replaced = True
    finally:
        if not replaced:
            _remove_file_and_sidecars(partial)
    return BackupResult(
        path=destination,
        sha256=sha256_of(destination),
        size_bytes=destination.stat().st_size,
        integrity=integrity,
    )


def sha256_of(path: Path) -> str:
    """SHA-256 of the file's bytes."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(_READ_CHUNK):
            digest.update(chunk)
    return digest.hexdigest()


def quick_check(path: Path) -> str:
    """``PRAGMA quick_check``: ``"ok"`` or SQLite's description of what is wrong.

    **Read-only**, unlike the other two (panel P2-9). Its caller of record is ``db upgrade``
    verifying the pre-migration *copy* immediately after :func:`online_backup` hashed it: a
    read-write connection can create sidecars, replay a WAL, and otherwise change the bytes
    of the very file whose ``sha256`` has already been written into the ``backups`` row, so
    the recorded hash would stop matching the file it describes. A verification must not be
    able to modify what it verifies. It also means a missing file is reported rather than
    created -- read-write ``sqlite3.connect`` would have made an empty database out of a
    typo'd path.

    A read-only connection to a WAL-mode database still creates the empty ``-wal`` / ``-shm``
    pair it needs to read one, and cannot delete them again on close. The main file's bytes
    are untouched (which is what the recorded ``sha256`` is about); tidying the pair belongs
    to whoever owns the file, which for the pre-migration copy is
    ``services/migrate.py`` calling :func:`remove_sidecars`. Nothing here deletes a sidecar
    of a database it did not create, because a live ``-wal`` holds committed transactions.
    """
    rows = _pragma(path, "quick_check", read_only=True)
    return "\n".join(str(row[0]) for row in rows)


def integrity_check(path: Path) -> str:
    """``PRAGMA integrity_check``: ``"ok"`` or SQLite's description of what is wrong."""
    rows = _pragma(path, "integrity_check")
    return "\n".join(str(row[0]) for row in rows)


def foreign_key_check(path: Path) -> list[str]:
    """``PRAGMA foreign_key_check``: one string per violating row, empty when clean."""
    return [str(tuple(row)) for row in _pragma(path, "foreign_key_check")]


def restore(backup: Path, destination: Path) -> None:
    """Put ``backup``'s content at ``destination`` atomically, sidecars removed.

    The caller owns the engines: this function disposes nothing, and calling it while an
    engine still holds ``destination`` open is a bug on the caller's side.

    Removing ``destination-wal`` and ``destination-shm`` is mandatory -- a stale WAL next to
    a restored main file is a silently corrupt database. The backup file itself survives the
    restore: the ``backups`` row the post-restore bookkeeping writes points at it, and a
    restore that consumed the only copy would leave a second failure with nothing to fall
    back on. The swap goes through a temporary sibling and :func:`_durable_replace`, so
    ``destination`` is never a half-written file **and** never a half-flushed one: a restore
    is the recovery path, so a crash during it is exactly the crash that matters
    (panel P2-9).

    **Order (KI-015).** The copy comes first, because it is the one step that can fail (a
    missing or unreadable backup, a full disk), and nothing live is touched until it has
    succeeded: a crash-left ``-wal`` holds committed transactions the next open would have
    recovered, and the earlier order deleted it before copying, so a failed restore lost
    them. The sidecar removal and the swap then run back to back; the window between them is
    accepted, being microseconds against a copy that can take minutes.
    """
    staging = destination.with_name(destination.name + ".restoring")
    _remove_file_and_sidecars(staging)
    try:
        shutil.copyfile(backup, staging)  # the step that can fail; nothing live touched yet
        for sidecar in _sidecars(destination):
            sidecar.unlink(missing_ok=True)
        _durable_replace(staging, destination)
    finally:
        _remove_file_and_sidecars(staging)
    for sidecar in _sidecars(destination):
        sidecar.unlink(missing_ok=True)
