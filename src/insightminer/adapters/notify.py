"""Notifier adapters: log-only, macOS Notification Center, and a no-op.

Every notifier's ``notify()`` returns None and never raises: alerting is best-effort and a
broken alert path must not turn a partial run into a crashed one. ``MacNotifier.send()``
exposes the delivery result as a bool for ``insightminer notify --test`` and ``doctor``.
"""

from __future__ import annotations

import logging
import subprocess
from collections.abc import Callable, Sequence

_LEVELS = {
    "debug": logging.DEBUG,
    "info": logging.INFO,
    "warning": logging.WARNING,
    "error": logging.ERROR,
    "critical": logging.CRITICAL,
}

type Runner = Callable[[Sequence[str]], int]
"""Runs ``argv`` to completion and returns its exit code.

May raise ``OSError`` or ``subprocess.SubprocessError``; ``MacNotifier`` absorbs both.
"""


class LogNotifier:
    """Records every notification and mirrors it to a ``logging`` logger at the given level."""

    def __init__(self, logger: logging.Logger | None = None) -> None:
        self._log = logger or logging.getLogger("insightminer.notify")
        self.messages: list[tuple[str, str]] = []

    def notify(self, level: str, message: str) -> None:
        self.messages.append((level, message))
        self._log.log(_LEVELS.get(level.lower(), logging.INFO), "%s", message)


class NullNotifier:
    """Discards everything; for tests and ``--quiet`` runs."""

    def notify(self, level: str, message: str) -> None:
        return None


class FakeNotifier:
    """Records deliveries; ``fail_next()`` turns the next ones into recorded failures.

    Like every notifier it never raises: a failed delivery lands in ``failed`` instead of
    ``sent``, so a test can prove the caller noticed (``doctor`` records the last success).
    """

    def __init__(self) -> None:
        self.sent: list[tuple[str, str]] = []
        self.failed: list[tuple[str, str]] = []
        self._fail_remaining = 0

    def notify(self, level: str, message: str) -> None:
        if self._fail_remaining > 0:
            self._fail_remaining -= 1
            self.failed.append((level, message))
            return
        self.sent.append((level, message))

    def fail_next(self, times: int = 1) -> None:
        self._fail_remaining += times


def run_osascript(argv: Sequence[str]) -> int:
    """Default ``Runner``: run ``argv`` with a 10 s timeout and return the exit code."""
    completed = subprocess.run(list(argv), check=False, capture_output=True, timeout=10)
    return completed.returncode


class MacNotifier:
    """macOS Notification Center via ``osascript``.

    The message, title and level are passed as *arguments* to an ``on run argv`` handler, never
    spliced into AppleScript source, so quotes and backslashes in run errors cannot break or
    alter the script. ``runner`` is injectable so tests never spawn a process.
    """

    def __init__(self, title: str = "Insight Miner", runner: Runner | None = None) -> None:
        self.title = title
        self.runner: Runner = runner or run_osascript
        self.last_ok: bool | None = None
        self.sent: list[tuple[str, str]] = []

    def notify(self, level: str, message: str) -> None:
        self.last_ok = self.send(level, message)

    def send(self, level: str, message: str) -> bool:
        """Deliver one notification: True when ``osascript`` exited 0, else False. Never raises."""
        try:
            code = self.runner(self.argv(level, message))
        except (OSError, subprocess.SubprocessError):
            return False
        ok = code == 0
        if ok:
            self.sent.append((level, message))
        return ok

    def argv(self, level: str, message: str) -> list[str]:
        """The exact command line ``send`` runs (exposed for tests and ``doctor``)."""
        return [
            "osascript",
            "-e",
            "on run argv",
            "-e",
            "display notification (item 1 of argv) with title (item 2 of argv) "
            "subtitle (item 3 of argv)",
            "-e",
            "end run",
            "--",
            message,
            self.title,
            level.upper(),
        ]


__all__ = ["FakeNotifier", "LogNotifier", "MacNotifier", "NullNotifier", "Runner", "run_osascript"]
