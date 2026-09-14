"""RL-02 service half: ``services/lock.py``'s flock, its bounded retry, ``pid_alive`` and the
shared ``is_held`` probe (design-round5.md §12.2, §12.5).

``services/lock.py`` does not exist yet -- every test here is expected to fail on
``ModuleNotFoundError`` until step 3 implements it. Nothing here sleeps for real: the one
exception the design carries (§1) is ``lock.acquire``'s own bounded retry, measured rather
than skipped.
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from insightminer.services import lock


@pytest.fixture
def lock_path(tmp_path: Path) -> Path:
    """A lock file under a directory that does not exist yet.

    Round5-findings.json P0 #2 requires ``acquire`` and ``is_held`` to create
    ``path.parent`` before opening the file: every command takes this lock before anything
    else has created ``data/locks/``. Starting every test from a missing parent makes that
    the default case rather than a special one.
    """
    return tmp_path / "locks" / "collector.lock"


def test_second_acquire_from_another_fd_raises(lock_path: Path) -> None:
    """``flock`` conflicts across descriptions, including two inside one process (§12.2)."""
    with lock.acquire(lock_path):
        with pytest.raises(lock.LockHeldError):
            with lock.acquire(lock_path, attempts=1, retry_delay_seconds=0.0):
                pytest.fail("the second acquire must not enter its body")


def test_acquire_against_a_genuinely_held_lock_still_raises(lock_path: Path) -> None:
    """``retry_delay_seconds=0.0`` so the retry cannot hide a real holder (§12.2)."""
    with lock.acquire(lock_path):
        with pytest.raises(lock.LockHeldError):
            with lock.acquire(lock_path, retry_delay_seconds=0.0):
                pytest.fail("a genuinely held lock must never be granted")


def test_a_nested_acquire_is_refused_and_leaves_the_outer_holder_alone(lock_path: Path) -> None:
    """``acquire``'s docstring used to claim a nested acquire was "a no-op rather than a
    deadlock" (panel P2-4). It is neither: each call opens a NEW file description, ``flock``
    conflicts across descriptions, and the inner call raises :class:`LockHeldError`.

    The full default ``attempts`` budget is spent (only ``retry_delay_seconds`` is zeroed, as
    in the sibling test above, so the suite does not sleep for real): the claim was about an
    ordinary second ``acquire`` inside one command, not about a caller who disabled the
    retry. The outer holder surviving is the other half -- a refusal that closed the inner
    description must not release the outer flock, which shares the same file.
    """
    with lock.acquire(lock_path):
        with pytest.raises(lock.LockHeldError) as caught:
            with lock.acquire(lock_path, retry_delay_seconds=0.0):
                pytest.fail("a nested acquire must not enter its body")
        assert caught.value.path == lock_path
        assert lock.is_held(lock_path) is True  # the outer holder still has it

    assert lock.is_held(lock_path) is False


def test_acquire_on_a_free_lock_does_not_pay_the_retry(lock_path: Path) -> None:
    """The retry is paid only by a held lock; a free one is instant (§12.2)."""
    started = time.monotonic()
    with lock.acquire(lock_path):
        pass
    assert time.monotonic() - started < lock.LOCK_RETRY_DELAY_SECONDS


def test_is_held_is_true_inside_the_holder(lock_path: Path) -> None:
    """``is_held`` is a SHARED probe, valid even from inside the exclusive holder (§12.2)."""
    with lock.acquire(lock_path):
        assert lock.is_held(lock_path) is True


def test_lock_released_on_exception(lock_path: Path) -> None:
    """An exception inside the ``with`` block still releases the flock."""
    with pytest.raises(RuntimeError, match="boom"):
        with lock.acquire(lock_path):
            raise RuntimeError("boom")
    # The earlier holder's fd is gone; a fresh acquire with no retry budget must succeed.
    with lock.acquire(lock_path, retry_delay_seconds=0.0):
        pass


def test_pid_alive_is_false_for_a_dead_pid() -> None:
    """``os.kill(pid, 0)`` raises ``ProcessLookupError`` for a pid nothing could hold."""
    assert lock.pid_alive(2**31 - 1) is False


def test_pid_alive_is_true_for_pid_1() -> None:
    """pid 1 is always alive but never ours: ``PermissionError`` means alive (fail closed)."""
    assert lock.pid_alive(1) is True


# --- round5-findings.json P0 #2: the lock directory does not exist before the first command
# creates it, so ``acquire`` must create it itself rather than raising ``FileNotFoundError``.


def test_acquire_creates_the_locks_directory_when_missing(lock_path: Path) -> None:
    assert not lock_path.parent.exists()
    with lock.acquire(lock_path):
        pass
    assert lock_path.parent.is_dir()


# --- round5 doctor-panel finding: ``is_held`` is read-only and must never create the thing
# it is diagnosing -- unlike ``acquire``, a missing parent or missing lock file both mean
# "not held," answered without touching the filesystem to find out.


def test_is_held_on_a_missing_parent_returns_false_without_creating_anything(
    lock_path: Path,
) -> None:
    """``doctor``'s ``lock_not_stale`` check calls ``is_held`` on every ``--no-network`` run;
    an hourly, read-only ``doctor`` must not conjure ``data/locks/`` into existence merely by
    asking whether anyone holds it (round5 doctor-panel finding)."""
    assert not lock_path.parent.exists()

    assert lock.is_held(lock_path) is False

    assert not lock_path.parent.exists()
    assert not lock_path.exists()


def test_is_held_with_an_existing_parent_but_no_lock_file_does_not_create_the_file(
    lock_path: Path,
) -> None:
    """The other half of the same fix: even when ``data/locks/`` already exists (say, a
    prior run's ``acquire`` created it and then released), a probe against a lock file that
    was never written must not write it into existence either."""
    lock_path.parent.mkdir(parents=True)

    assert lock.is_held(lock_path) is False

    assert not lock_path.exists()
