"""section 11.8: the clock ``cli`` builds refuses to sleep under pytest, so a planted
transient/rate-limit scenario in the e2e suite cannot silently burn real wall time.
"""

from __future__ import annotations

import pytest

from threaddigest import cli
from threaddigest.adapters.clock import SystemClock


@pytest.mark.gate("G46")
def test_cli_builds_a_guard_clock_under_pytest() -> None:
    """This test itself runs under pytest, so ``PYTEST_CURRENT_TEST`` is set."""
    assert isinstance(cli.build_clock(), cli.GuardClock)


@pytest.mark.gate("G46")
def test_cli_builds_a_system_clock_without_pytest(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    assert isinstance(cli.build_clock(), SystemClock)


@pytest.mark.gate("G46")
def test_guard_clock_sleep_raises() -> None:
    """The positive control: a ``GuardClock`` that silently returned would defeat the
    whole point of the guard.
    """
    clock = cli.GuardClock()
    assert clock.now() > 0
    with pytest.raises(AssertionError):
        clock.sleep(1)
