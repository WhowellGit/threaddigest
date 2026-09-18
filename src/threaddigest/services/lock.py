"""The collector flock: one lock file, one mechanism, and the process-liveness probe.

This is the **only** module in the project that imports ``fcntl`` (design-round5 §1). Three
facts, measured rather than assumed (§12.2), shape everything below:

* ``flock`` conflicts across open file *descriptions*, including two descriptions inside one
  process. Per-process semantics would need ``fcntl.lockf``, which this design does not use.
* A shared probe and an exclusive holder still conflict, so :func:`is_held` is valid from
  anywhere -- including inside the holder -- while two probes never block each other.
* Because a shared probe refuses an exclusive acquirer for the microseconds it is held,
  :func:`acquire` retries a non-blocking ``flock`` :data:`LOCK_RETRY_ATTEMPTS` times
  :data:`LOCK_RETRY_DELAY_SECONDS` apart before declaring the lock held. That bounded wait
  (<= 100 ms) is one of the two sleeps §1 allows, and only a genuinely held lock pays it.

**No pid file** (§12.2). Nothing is written into the lock file: the flock is the mechanism and
the ``runs`` row is the liveness record. :class:`LockInfo` describes *this* holder in memory so
a caller can log who took the lock, and is never read back from disk.

:func:`acquire` creates ``path.parent`` before opening the file (round5-findings.json P0
"lock acquisition versus directory creation", and §12.5): every mutating command takes this
lock before anything has created ``data/locks/``, so ``db init`` on a fresh data directory
would otherwise die with ``FileNotFoundError`` at step 1. :func:`is_held` does the opposite
on purpose -- it is a read-only probe (``doctor``'s ``lock_not_stale`` check is its only
caller outside a lock holder), and a diagnostic that creates the thing it is diagnosing is
not read-only: a missing parent or missing lock file both mean "not held," reported without
creating either.
"""

from __future__ import annotations

import fcntl
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Final

__all__ = [
    "LOCK_RELATIVE_PATH",
    "LOCK_RETRY_ATTEMPTS",
    "LOCK_RETRY_DELAY_SECONDS",
    "LockHeldError",
    "LockInfo",
    "acquire",
    "is_held",
    "lock_path_for",
    "pid_alive",
]

#: The collector lock file, relative to the resolved data directory (12.2). One spelling, in
#: the module that owns the lock: `cli`, `services.migrate` and `services.doctor` each built
#: this path themselves until 2026-09-17, and the duplication was load-bearing rather than
#: cosmetic -- a `doctor` probing a different path than the collector takes would report the
#: lock free during a run (the code panel's cut list, seat B section 4).
LOCK_RELATIVE_PATH: Final = Path("locks") / "collector.lock"

#: Non-blocking ``flock`` attempts before ``acquire`` declares the lock held.
LOCK_RETRY_ATTEMPTS: Final = 3
#: Pause between those attempts; ``(attempts - 1) * delay`` is the worst case (<= 100 ms).
LOCK_RETRY_DELAY_SECONDS: Final = 0.05


def lock_path_for(data_dir: Path) -> Path:
    """The collector lock inside ``data_dir``: the only way any caller names this file."""
    return data_dir / LOCK_RELATIVE_PATH


@dataclass(frozen=True, slots=True)
class LockInfo:
    """Who holds the lock, from the holder's own point of view (§3.3)."""

    path: Path
    pid: int | None
    written_at: int | None


class LockHeldError(RuntimeError):
    """Another open file description holds the collector flock.

    The message is built here, so call sites pass the path and never a string (TRY003).
    """

    def __init__(self, path: Path) -> None:
        super().__init__(f"another process holds the collector lock at {path}")
        self.path = path


def pid_alive(pid: int) -> bool:
    """``os.kill(pid, 0)``: does a process with this id exist?

    Fails **closed**: ``ProcessLookupError`` is the only answer that means "dead".
    ``PermissionError`` means alive and owned by somebody else, and any other ``OSError``
    leaves the question open, which the stale sweep must read as "still running" rather than
    condemning a live run's row (§12.2).
    """
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def is_held(path: Path) -> bool:
    """True when another description holds the lock.

    A **shared** probe, released immediately, so two probes never collide with each other and
    an hourly ``doctor`` cannot make a scheduled collector report ``skipped_locked`` (§12.2,
    §15.2). Valid inside the exclusive holder, which is what §11.3's dry-run probe needs.

    **Read-only, unlike** :func:`acquire`: this never creates ``path.parent`` or the lock
    file itself (round5 doctor-panel finding -- an hourly, no-network ``doctor`` run was
    conjuring ``data/locks/collector.lock`` into existence merely by asking whether anyone
    held it). Nothing on disk means nothing can hold a lock, so a missing parent or a missing
    file both answer "not held" without touching the filesystem to find out.
    """
    if not path.exists():
        return False
    with path.open("r", encoding="utf-8") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_SH | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    return False


def _lock_exclusive(fileno: int, path: Path, *, attempts: int, retry_delay_seconds: float) -> None:
    """``flock(LOCK_EX | LOCK_NB)``, retried, then :class:`LockHeldError`.

    ``attempts`` is floored at one, so a caller passing zero cannot enter the body of
    ``acquire`` holding nothing.
    """
    last = max(attempts, 1)
    for attempt in range(1, last + 1):
        try:
            fcntl.flock(fileno, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            if attempt >= last:
                raise LockHeldError(path) from exc
            time.sleep(retry_delay_seconds)
        else:
            return


@contextmanager
def acquire(
    path: Path,
    *,
    attempts: int = LOCK_RETRY_ATTEMPTS,
    retry_delay_seconds: float = LOCK_RETRY_DELAY_SECONDS,
) -> Iterator[LockInfo]:
    """Hold the collector flock for the body, or raise :class:`LockHeldError`.

    Creates ``path.parent`` first (round5-findings.json P0 #2). The flock is released by
    closing the description, which the ``finally`` does on every path, so an exception inside
    the body never leaves the lock behind.

    **Nesting is refused, not idempotent.** Each call opens its own file description, and
    ``flock`` conflicts across descriptions -- including two inside one process (the module
    docstring's first measured fact) -- so a second ``acquire`` on a path this process already
    holds raises :class:`LockHeldError` like any other contention, after the bounded retry.
    Re-locking would be a no-op only if the same *description* were re-locked, which nothing
    here does. One context manager per command (§12.2); a nested one is a bug the refusal
    surfaces rather than a deadlock or a silent pass (panel P2-4).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+", encoding="utf-8")
    try:
        _lock_exclusive(
            handle.fileno(),
            path,
            attempts=attempts,
            retry_delay_seconds=retry_delay_seconds,
        )
        yield LockInfo(path=path, pid=os.getpid(), written_at=int(time.time()))
    finally:
        handle.close()
