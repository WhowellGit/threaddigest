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

__all__ = [
    "BACKUP_SUFFIXES",
    "BackupResult",
    "foreign_key_check",
    "integrity_check",
    "online_backup",
    "quick_check",
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


def _remove_file_and_sidecars(path: Path) -> None:
    for candidate in (path, *_sidecars(path)):
        candidate.unlink(missing_ok=True)


def _pragma(path: Path, pragma: str) -> list[tuple[object, ...]]:
    """Run one PRAGMA against ``path`` and return its rows.

    The connection is read-write on purpose: opening a WAL database read-only can fail when
    no ``-shm`` file exists yet, and a clean close removes any sidecar this created.
    """
    connection = sqlite3.connect(path)
    try:
        return [tuple(row) for row in connection.execute(f"PRAGMA {pragma}").fetchall()]
    finally:
        connection.close()


def online_backup(source: Path, destination: Path, *, pages: int = 0) -> BackupResult:
    """Copy the live database at ``source`` to ``destination`` through SQLite's backup API.

    The copy is written to ``<destination>.partial`` and ``os.replace``d into place, so a
    failed copy never leaves a plausible-looking backup file. ``pages=0`` copies the whole
    database in one step. The returned ``integrity`` is ``PRAGMA integrity_check`` on the
    copy -- the caller decides what a non-``"ok"`` result means.
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
        os.replace(partial, destination)
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
    """``PRAGMA quick_check``: ``"ok"`` or SQLite's description of what is wrong."""
    rows = _pragma(path, "quick_check")
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
    back on. The swap goes through a temporary sibling and ``os.replace`` so ``destination``
    is never a half-written file.
    """
    for sidecar in _sidecars(destination):
        sidecar.unlink(missing_ok=True)
    staging = destination.with_name(destination.name + ".restoring")
    staging.unlink(missing_ok=True)
    try:
        shutil.copyfile(backup, staging)
        os.replace(staging, destination)
    finally:
        staging.unlink(missing_ok=True)
    for sidecar in _sidecars(destination):
        sidecar.unlink(missing_ok=True)
