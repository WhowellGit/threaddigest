"""Clock and Notifier adapters."""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Sequence

import pytest

from threaddigest.adapters.clock import FakeClock, SystemClock
from threaddigest.adapters.notify import (
    FakeNotifier,
    LogNotifier,
    MacNotifier,
    NullNotifier,
    run_osascript,
)
from threaddigest.ports import Clock, Notifier


class TestFakeClock:
    def test_starts_at_start(self) -> None:
        assert FakeClock(1_000).now() == 1_000

    def test_advance_moves_time(self) -> None:
        clock = FakeClock(1_000)
        clock.advance(86_400)
        assert clock.now() == 87_400

    def test_advance_negative_for_skew_tests(self) -> None:
        clock = FakeClock(1_000)
        clock.advance(-500)
        assert clock.now() == 500

    def test_sleep_records_and_advances(self) -> None:
        clock = FakeClock(1_000)
        clock.sleep(30)
        clock.sleep(2.5)
        assert clock.sleeps == [30.0, 2.5]
        assert clock.now() == 1_032
        assert clock.total_slept == 32.5

    def test_sleep_never_blocks(self) -> None:
        clock = FakeClock(0)
        started = time.perf_counter()
        clock.sleep(3_600)
        assert time.perf_counter() - started < 0.5
        assert clock.now() == 3_600

    def test_negative_sleep_rejected(self) -> None:
        with pytest.raises(ValueError, match="negative"):
            FakeClock(0).sleep(-1)

    def test_satisfies_clock_protocol(self) -> None:
        assert isinstance(FakeClock(0), Clock)


class TestSystemClock:
    def test_now_is_epoch_seconds_int(self) -> None:
        before = int(time.time())
        now = SystemClock().now()
        assert isinstance(now, int)
        assert before <= now <= before + 2

    def test_sleep_zero_returns(self) -> None:
        SystemClock().sleep(0)

    def test_satisfies_clock_protocol(self) -> None:
        assert isinstance(SystemClock(), Clock)


class TestLogNotifier:
    def test_records_messages_in_order(self) -> None:
        notifier = LogNotifier(logging.getLogger("test.notify"))
        notifier.notify("info", "started")
        notifier.notify("error", "failed")
        assert notifier.messages == [("info", "started"), ("error", "failed")]

    def test_logs_at_the_requested_level(self, caplog: pytest.LogCaptureFixture) -> None:
        notifier = LogNotifier(logging.getLogger("test.notify.level"))
        with caplog.at_level(logging.DEBUG, logger="test.notify.level"):
            notifier.notify("warning", "budget low")
            notifier.notify("ERROR", "run failed")
        levels = [(r.levelno, r.getMessage()) for r in caplog.records]
        assert levels == [(logging.WARNING, "budget low"), (logging.ERROR, "run failed")]

    def test_unknown_level_falls_back_to_info(self, caplog: pytest.LogCaptureFixture) -> None:
        notifier = LogNotifier(logging.getLogger("test.notify.unknown"))
        with caplog.at_level(logging.DEBUG, logger="test.notify.unknown"):
            notifier.notify("shout", "hello")
        assert [r.levelno for r in caplog.records] == [logging.INFO]

    def test_satisfies_notifier_protocol(self) -> None:
        assert isinstance(LogNotifier(), Notifier)


class TestNullNotifier:
    def test_discards_and_returns_none(self) -> None:
        assert NullNotifier().notify("error", "anything") is None

    def test_satisfies_notifier_protocol(self) -> None:
        assert isinstance(NullNotifier(), Notifier)


class TestFakeNotifier:
    def test_records_sent_messages(self) -> None:
        notifier = FakeNotifier()
        notifier.notify("info", "started")
        notifier.notify("error", "failed")
        assert notifier.sent == [("info", "started"), ("error", "failed")]
        assert notifier.failed == []

    def test_fail_next_records_failures_without_raising(self) -> None:
        notifier = FakeNotifier()
        notifier.fail_next(2)
        notifier.notify("error", "one")
        notifier.notify("error", "two")
        notifier.notify("error", "three")
        assert notifier.failed == [("error", "one"), ("error", "two")]
        assert notifier.sent == [("error", "three")]

    def test_satisfies_notifier_protocol(self) -> None:
        assert isinstance(FakeNotifier(), Notifier)


class _Recorder:
    """Injectable runner that records argv and returns a fixed code or raises."""

    def __init__(self, code: int = 0, raises: BaseException | None = None) -> None:
        self.code = code
        self.raises = raises
        self.argvs: list[list[str]] = []

    def __call__(self, argv: Sequence[str]) -> int:
        self.argvs.append(list(argv))
        if self.raises is not None:
            raise self.raises
        return self.code


class TestMacNotifier:
    def test_success_returns_true_and_records(self) -> None:
        runner = _Recorder(code=0)
        notifier = MacNotifier(runner=runner)
        assert notifier.send("error", "run failed") is True
        assert notifier.sent == [("error", "run failed")]
        assert len(runner.argvs) == 1

    def test_nonzero_exit_returns_false(self) -> None:
        notifier = MacNotifier(runner=_Recorder(code=1))
        assert notifier.send("error", "run failed") is False
        assert notifier.sent == []

    def test_missing_osascript_never_raises(self) -> None:
        notifier = MacNotifier(runner=_Recorder(raises=FileNotFoundError("osascript")))
        assert notifier.send("error", "run failed") is False

    def test_timeout_never_raises(self) -> None:
        expired = subprocess.TimeoutExpired(cmd="osascript", timeout=10)
        notifier = MacNotifier(runner=_Recorder(raises=expired))
        assert notifier.send("error", "run failed") is False

    def test_notify_conforms_to_protocol_and_exposes_result(self) -> None:
        notifier = MacNotifier(runner=_Recorder(code=1))
        assert isinstance(notifier, Notifier)
        assert notifier.last_ok is None
        assert notifier.notify("error", "x") is None
        assert notifier.last_ok is False

    def test_message_is_an_argument_not_script_source(self) -> None:
        runner = _Recorder()
        message = 'crashed: "quoted" \\ and\nnewline'
        MacNotifier(title="Thread Digest", runner=runner).notify("error", message)
        argv = runner.argvs[0]
        assert argv[0] == "osascript"
        separator = argv.index("--")
        assert argv[separator + 1 :] == [message, "Thread Digest", "ERROR"]
        statements = [argv[i + 1] for i, flag in enumerate(argv[:separator]) if flag == "-e"]
        assert all(message not in s for s in statements)
        assert any("display notification" in s for s in statements)

    def test_default_runner_is_the_subprocess_runner(self) -> None:
        assert MacNotifier().runner is run_osascript
