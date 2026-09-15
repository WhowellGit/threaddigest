"""Tests for the retry ladder, exception classification, exit codes and wait/defer decisions."""

from __future__ import annotations

import errno
import math
import socket
from collections.abc import Callable

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from insightminer.core.retry import (
    DEFAULT_LADDER_SECONDS,
    DEFAULT_RATE_LIMIT_WAIT_SECONDS,
    EXIT_CODES,
    MAX_RATE_LIMIT_WAIT_SECONDS,
    ExitCode,
    Outcome,
    RetryPolicy,
    RunStatus,
    WaitDecision,
    classify,
    exit_code,
    plan_rate_limit_wait,
)

# ------------------------------------------------------------------ retry ladder


def test_default_ladder_matches_plan() -> None:
    assert DEFAULT_LADDER_SECONDS == (30, 120, 300)
    policy = RetryPolicy()
    assert policy.ladder_seconds == (30, 120, 300)
    assert policy.max_attempts == 4
    assert policy.total_delay_seconds == 450


def test_next_delay_walks_the_ladder_then_exhausts() -> None:
    policy = RetryPolicy(ladder_seconds=(30, 120, 300))
    assert policy.next_delay(1) == 30
    assert policy.next_delay(2) == 120
    assert policy.next_delay(3) == 300
    assert policy.next_delay(4) is None
    assert policy.next_delay(99) is None


def test_te01_two_failures_then_success_sleeps_thirty_and_one_twenty() -> None:
    # Ingest panel TE-01: page 2 fails twice then succeeds -> sleeps [30, 120].
    policy = RetryPolicy()
    sleeps = [policy.next_delay(attempt) for attempt in (1, 2)]
    assert sleeps == [30, 120]
    # Variant: four failures -> sleeps [30, 120, 300], then the sub is given up.
    sleeps = []
    for attempt in (1, 2, 3, 4):
        delay = policy.next_delay(attempt)
        if delay is None:
            break
        sleeps.append(delay)
    assert sleeps == [30, 120, 300]
    assert policy.next_delay(4) is None


def test_delays_are_floats() -> None:
    delay = RetryPolicy(ladder_seconds=(30, 120, 300)).next_delay(1)
    assert isinstance(delay, float)


def test_empty_ladder_means_no_retries() -> None:
    policy = RetryPolicy(ladder_seconds=())
    assert policy.max_attempts == 1
    assert policy.next_delay(1) is None


def test_ladder_accepts_any_sequence_and_stores_a_tuple() -> None:
    assert RetryPolicy(ladder_seconds=[5, 10]).ladder_seconds == (5.0, 10.0)


@pytest.mark.parametrize("attempt", [0, -1])
def test_attempt_below_one_rejected(attempt: int) -> None:
    with pytest.raises(ValueError, match="attempt"):
        RetryPolicy().next_delay(attempt)


@pytest.mark.parametrize(
    "ladder",
    [(-1, 30), (120, 30), (30, math.inf), (math.nan,), (30, 120, 60)],
)
def test_bad_ladders_rejected(ladder: tuple[float, ...]) -> None:
    with pytest.raises(ValueError, match="ladder"):
        RetryPolicy(ladder_seconds=ladder)


def test_policy_is_immutable() -> None:
    policy = RetryPolicy()
    field = "ladder_seconds"
    with pytest.raises(AttributeError):
        setattr(policy, field, (1,))


# -------------------------------------------------------------- classification


def named(name: str, base: type[BaseException] = Exception, **attrs: object) -> type[BaseException]:
    """An exception class with exactly this name and these class attributes.

    core classifies by name and duck-typed attributes without importing praw, prawcore or
    requests, so the tests build stand-ins carrying the real libraries' names.
    """
    return type(name, (base,), attrs)


class _Response:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


def _with_cause(exc: BaseException, cause: BaseException) -> BaseException:
    exc.__cause__ = cause
    return exc


CLASSIFY_CASES: list[tuple[BaseException, Outcome]] = [
    # ports.py domain exceptions, by name
    (named("TransientError")("503"), Outcome.TRANSIENT),
    (named("RateLimited", retry_after=3)(), Outcome.RATE_LIMITED),
    (named("RateLimited", retry_after=None)(), Outcome.RATE_LIMITED),
    (named("AuthFailed")("401"), Outcome.AUTH),
    (named("SubredditForbidden")("private"), Outcome.FATAL),
    (named("SubredditQuarantined")(), Outcome.FATAL),
    (named("SubredditNotFound")(), Outcome.FATAL),
    (named("SubredditRedirected")(), Outcome.FATAL),
    (named("HtmlBlocked")("cloudflare"), Outcome.FATAL),
    (named("GatewayError")(), Outcome.FATAL),
    # prawcore, by name and response status
    (named("ServerError")("502"), Outcome.TRANSIENT),
    (named("RequestException")(), Outcome.FATAL),
    (named("ResponseException", response=_Response(500))(), Outcome.TRANSIENT),
    (named("ResponseException", response=_Response(503))(), Outcome.TRANSIENT),
    (named("ResponseException", response=_Response(429))(), Outcome.RATE_LIMITED),
    (named("ResponseException", response=_Response(401))(), Outcome.AUTH),
    (named("ResponseException", response=_Response(403))(), Outcome.FATAL),
    (named("ResponseException", response=_Response(404))(), Outcome.FATAL),
    (named("TooManyRequests", response=_Response(429))(), Outcome.RATE_LIMITED),
    (named("Forbidden")("403"), Outcome.AUTH),
    (named("OAuthException")("invalid_grant"), Outcome.AUTH),
    (named("InvalidToken")(), Outcome.AUTH),
    (named("InsufficientScope")(), Outcome.AUTH),
    # requests / urllib3, by name
    (named("ReadTimeout")(), Outcome.TRANSIENT),
    (named("ConnectTimeout")(), Outcome.TRANSIENT),
    (named("ConnectionError")("reset"), Outcome.TRANSIENT),
    (named("ChunkedEncodingError")(), Outcome.TRANSIENT),
    (named("ProtocolError")(), Outcome.TRANSIENT),
    (named("NameResolutionError")(), Outcome.NETWORK_DOWN),
    (named("NewConnectionError")(), Outcome.NETWORK_DOWN),
    (named("HTTPError", response=_Response(400))(), Outcome.FATAL),
    # standard library
    (TimeoutError(), Outcome.TRANSIENT),
    (ConnectionResetError(), Outcome.TRANSIENT),
    (ConnectionAbortedError(), Outcome.TRANSIENT),
    (BrokenPipeError(), Outcome.TRANSIENT),
    (ConnectionRefusedError(), Outcome.NETWORK_DOWN),
    (socket.gaierror(8, "nodename nor servname provided"), Outcome.NETWORK_DOWN),
    (OSError(errno.ECONNREFUSED, "Connection refused"), Outcome.NETWORK_DOWN),
    (OSError(errno.ENETUNREACH, "Network is unreachable"), Outcome.NETWORK_DOWN),
    (OSError(errno.EHOSTUNREACH, "No route to host"), Outcome.NETWORK_DOWN),
    (OSError(errno.ENETDOWN, "Network is down"), Outcome.NETWORK_DOWN),
    (OSError(errno.ENOSPC, "No space left on device"), Outcome.FATAL),
    (ValueError("bad"), Outcome.FATAL),
    (KeyboardInterrupt(), Outcome.FATAL),
    (SystemExit(1), Outcome.FATAL),
]


@pytest.mark.parametrize(
    ("exc", "expected"),
    CLASSIFY_CASES,
    ids=[f"{type(exc).__name__}-{expected}" for exc, expected in CLASSIFY_CASES],
)
def test_classify_table(exc: BaseException, expected: Outcome) -> None:
    assert classify(exc) == expected


def test_subclass_of_a_known_name_classifies_by_the_parent_name() -> None:
    special_timeout = named("SpecialThing", base=named("ReadTimeout"))
    scoped_auth = named("ScopedThing", base=named("AuthFailed"))
    assert classify(special_timeout()) == Outcome.TRANSIENT
    assert classify(scoped_auth()) == Outcome.AUTH


def test_transient_wrapper_around_a_dns_failure_is_network_down() -> None:
    # requests.ConnectionError wraps urllib3's NameResolutionError; the adapter's
    # TransientError may in turn be raised from that. The root cause wins.
    dns = named("NameResolutionError")("[Errno 8] nodename nor servname provided")
    wrapped = _with_cause(named("ConnectionError")("wrapped"), dns)
    outer = _with_cause(named("TransientError")("after 3 short retries"), wrapped)
    assert classify(wrapped) == Outcome.NETWORK_DOWN
    assert classify(outer) == Outcome.NETWORK_DOWN


def test_transient_wrapper_with_refused_connection_in_args_or_reason_is_network_down() -> None:
    # urllib3 stores the reason on the exception object rather than in __cause__, and
    # requests passes it as the ConnectionError's argument.
    max_retry = named("MaxRetryError", reason=ConnectionRefusedError())("max retries")
    wrapper = named("ConnectionError")(max_retry)
    assert classify(max_retry) == Outcome.FATAL  # not a transient name on its own
    assert classify(wrapper) == Outcome.NETWORK_DOWN
    context_only = named("ConnectionError")("via context")
    context_only.__context__ = named("NewConnectionError")("refused")
    assert classify(context_only) == Outcome.NETWORK_DOWN


def test_fatal_wrapper_does_not_inherit_its_cause() -> None:
    # The adapter translates prawcore.Forbidden on /r/x/about into SubredditForbidden
    # `from` the original; that is a per-source status, never a credential failure.
    translated = _with_cause(named("SubredditForbidden")("private"), named("Forbidden")("403"))
    assert classify(translated) == Outcome.FATAL


def test_transient_wrapper_does_not_inherit_a_non_network_cause() -> None:
    assert classify(_with_cause(named("TransientError")(), named("ServerError")())) == (
        Outcome.TRANSIENT
    )
    assert classify(_with_cause(named("TransientError")(), named("AuthFailed")())) == (
        Outcome.TRANSIENT
    )


def test_retry_after_attribute_beats_every_name() -> None:
    assert classify(named("WeirdlyNamedServerError", retry_after=12)()) == Outcome.RATE_LIMITED


def test_status_must_be_a_real_http_status() -> None:
    assert classify(named("Thing", status_code="503")()) == Outcome.FATAL
    assert classify(named("Thing", status_code=True)()) == Outcome.FATAL
    assert classify(named("Thing", status_code=999)()) == Outcome.FATAL
    assert classify(named("Thing", status=502)()) == Outcome.TRANSIENT


def test_classify_survives_a_raising_property_and_a_cyclic_cause() -> None:
    def boom(_self: object) -> object:
        msg = "no"
        raise RuntimeError(msg)

    nasty = named("Nasty", retry_after=property(boom), response=property(boom))()
    assert classify(nasty) == Outcome.FATAL
    loop = named("TransientError")("loop")
    loop.__cause__ = loop
    loop.__context__ = loop
    assert classify(loop) == Outcome.TRANSIENT


def test_retry_module_imports_only_the_standard_library() -> None:
    # The layering contract is enforced by import-linter; this pins the stronger promise
    # in the module docstring: classification works without praw, prawcore or requests.
    import ast
    import sys
    from pathlib import Path

    import insightminer.core.retry as retry_module

    tree = ast.parse(Path(retry_module.__file__).read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imported.add(node.module.split(".")[0])
    assert imported <= set(sys.stdlib_module_names), imported - set(sys.stdlib_module_names)


# ------------------------------------------------------- statuses and exit codes


def test_run_status_values_match_the_runs_table_enum() -> None:
    assert {status.value for status in RunStatus} == {
        "ok",
        "partial",
        "failed",
        "rate_limited",
        "network",
        "cancelled",
        "crashed",
        "skipped_locked",
    }


def test_exit_code_mapping_is_total_over_run_status() -> None:
    assert set(EXIT_CODES) == set(RunStatus)
    for status in RunStatus:
        assert isinstance(EXIT_CODES[status], ExitCode)
        assert exit_code(status) == int(EXIT_CODES[status])


def test_exit_codes_match_the_plan() -> None:
    assert EXIT_CODES[RunStatus.OK] == 0
    assert EXIT_CODES[RunStatus.FAILED] == 1
    assert EXIT_CODES[RunStatus.PARTIAL] == 3
    assert EXIT_CODES[RunStatus.RATE_LIMITED] == 4
    assert EXIT_CODES[RunStatus.NETWORK] == 5
    assert EXIT_CODES[RunStatus.CRASHED] == 1
    assert EXIT_CODES[RunStatus.CANCELLED] == 130
    assert EXIT_CODES[RunStatus.SKIPPED_LOCKED] == 75
    # Config/auth failures happen before a run row exists, so they have a code but no status.
    assert ExitCode.CONFIG == 78
    assert ExitCode.CONFIG not in EXIT_CODES.values()


def test_exit_codes_are_distinct_except_failed_and_crashed() -> None:
    codes = sorted(int(code) for code in ExitCode)
    assert codes == [0, 1, 3, 4, 5, 75, 78, 130]
    by_code: dict[int, list[RunStatus]] = {}
    for status, code in EXIT_CODES.items():
        by_code.setdefault(int(code), []).append(status)
    shared = {code: statuses for code, statuses in by_code.items() if len(statuses) > 1}
    assert shared == {1: [RunStatus.FAILED, RunStatus.CRASHED]}


def test_exit_code_mapping_is_read_only() -> None:
    mapping: dict[RunStatus, ExitCode] = EXIT_CODES  # a read-only proxy typed as a Mapping
    with pytest.raises(TypeError):
        mapping[RunStatus.OK] = ExitCode.FAILED


# ------------------------------------------------------------ rate-limit waits


def test_rate_limit_constants_match_the_plan() -> None:
    assert DEFAULT_RATE_LIMIT_WAIT_SECONDS == 60
    assert MAX_RATE_LIMIT_WAIT_SECONDS == 300


def test_te02a_short_retry_after_waits_exactly_that_long_with_a_stage() -> None:
    decision = plan_rate_limit_wait(3, remaining_ceiling_seconds=10_000)
    assert decision == WaitDecision(
        should_wait=True, seconds=3.0, stage="rate_wait:3s", exit_status=None
    )


def test_te02b_long_retry_after_is_capped_at_five_minutes() -> None:
    decision = plan_rate_limit_wait(400, remaining_ceiling_seconds=10_000)
    assert decision.should_wait is True
    assert decision.seconds == 300
    assert decision.stage == "rate_wait:300s"


def test_missing_retry_after_waits_the_default_minute() -> None:
    decision = plan_rate_limit_wait(None, remaining_ceiling_seconds=10_000)
    assert decision.should_wait is True
    assert decision.seconds == 60
    assert decision.stage == "rate_wait:60s"


@pytest.mark.parametrize("retry_after", [0, -5, math.nan])
def test_unusable_retry_after_falls_back_to_the_default(retry_after: float) -> None:
    assert plan_rate_limit_wait(retry_after, remaining_ceiling_seconds=10_000).seconds == 60


def test_infinite_retry_after_is_capped() -> None:
    assert plan_rate_limit_wait(math.inf, remaining_ceiling_seconds=10_000).seconds == 300


def test_fractional_wait_rounds_the_stage_up() -> None:
    decision = plan_rate_limit_wait(36.2, remaining_ceiling_seconds=10_000)
    assert decision.seconds == 36.2
    assert decision.stage == "rate_wait:37s"


def test_wait_that_would_cross_the_ceiling_exits_rate_limited() -> None:
    decision = plan_rate_limit_wait(120, remaining_ceiling_seconds=90)
    assert decision == WaitDecision(
        should_wait=False, seconds=0.0, stage=None, exit_status=RunStatus.RATE_LIMITED
    )
    assert exit_code(RunStatus.RATE_LIMITED) == 4


def test_wait_equal_to_the_ceiling_still_fits() -> None:
    assert plan_rate_limit_wait(90, remaining_ceiling_seconds=90).should_wait is True


@pytest.mark.parametrize("ceiling", [0, -1, math.nan])
def test_no_ceiling_left_means_exit(ceiling: float) -> None:
    decision = plan_rate_limit_wait(1, remaining_ceiling_seconds=ceiling)
    assert decision.should_wait is False
    assert decision.exit_status == RunStatus.RATE_LIMITED


# The same-day deferral rule of the daily era (three slots a day) was removed with D-30 and
# KI-025: a ``network`` run is retried at the next scheduled slot, and the schedule lives only
# in the launchd templates (``tests/deploy/test_schedule_contract.py``).


# ---------------------------------------------------------------- hypothesis

ladders = st.lists(
    st.floats(min_value=0, max_value=1e6, allow_nan=False, allow_infinity=False),
    max_size=10,
).map(sorted)


@settings(max_examples=300)
@given(ladders)
def test_ladder_is_monotonic_and_finite(ladder: list[float]) -> None:
    policy = RetryPolicy(ladder_seconds=ladder)
    delays = []
    attempt = 1
    while (delay := policy.next_delay(attempt)) is not None:
        assert math.isfinite(delay)
        assert delay >= 0
        delays.append(delay)
        attempt += 1
        assert attempt <= len(ladder) + 1, "the ladder must end"
    assert delays == [float(step) for step in ladder]
    assert all(a <= b for a, b in zip(delays, delays[1:], strict=False))
    assert policy.max_attempts == len(ladder) + 1
    for beyond in range(len(ladder) + 1, len(ladder) + 5):
        assert policy.next_delay(beyond) is None


_BUILTIN_EXCEPTION_FACTORIES: list[Callable[[], BaseException]] = [
    lambda: ValueError("v"),
    lambda: TypeError("t"),
    lambda: KeyError("k"),
    lambda: RuntimeError("r"),
    lambda: OSError(errno.ECONNREFUSED, "refused"),
    lambda: OSError(errno.ENETUNREACH, "unreachable"),
    lambda: OSError("no errno"),
    ConnectionRefusedError,
    ConnectionResetError,
    TimeoutError,
    lambda: socket.gaierror(8, "dns"),
    MemoryError,
    RecursionError,
    KeyboardInterrupt,
    lambda: SystemExit(2),
    GeneratorExit,
    StopIteration,
    NotImplementedError,
    lambda: UnicodeDecodeError("utf-8", b"\xff", 0, 1, "bad"),
    lambda: ExceptionGroup("group", [ValueError("inner")]),
]

_identifier_chars = st.characters(whitelist_categories=("Lu", "Ll", "Nd"), whitelist_characters="_")
_class_names = st.text(alphabet=_identifier_chars, min_size=1, max_size=40).filter(
    lambda name: name.isidentifier()
)
_attribute_values = st.one_of(
    st.none(),
    st.booleans(),
    st.integers(),
    st.floats(),
    st.text(max_size=8),
    st.binary(max_size=4),
    st.lists(st.integers(), max_size=3),
)


@st.composite
def synthetic_exceptions(draw: st.DrawFn) -> BaseException:
    name = draw(_class_names)
    base = draw(st.sampled_from([Exception, OSError, RuntimeError, BaseException]))
    attrs: dict[str, object] = {}
    for attribute in ("retry_after", "status_code", "status", "errno", "reason", "response"):
        if draw(st.booleans()):
            attrs[attribute] = draw(_attribute_values)
    cls = type(name, (base,), attrs)
    exc: BaseException = cls(*draw(st.lists(_attribute_values, max_size=2)))
    return exc


exceptions = st.one_of(
    st.sampled_from(_BUILTIN_EXCEPTION_FACTORIES).map(lambda factory: factory()),
    synthetic_exceptions(),
)


@settings(max_examples=400)
@given(exceptions, st.lists(exceptions, max_size=3), st.booleans())
def test_classify_never_raises(
    exc: BaseException, chain: list[BaseException], as_context: bool
) -> None:
    current = exc
    for link in chain:
        if as_context:
            current.__context__ = link
        else:
            current.__cause__ = link
        current = link
    current.__cause__ = exc  # close the loop: classification must still terminate
    outcome = classify(exc)
    assert isinstance(outcome, Outcome)


@settings(max_examples=300)
@given(
    st.one_of(st.none(), st.floats(), st.integers(min_value=-(10**6), max_value=10**6)),
    st.floats(),
)
def test_rate_limit_wait_is_bounded_or_exits(retry_after: float | None, ceiling: float) -> None:
    decision = plan_rate_limit_wait(retry_after, remaining_ceiling_seconds=ceiling)
    if decision.should_wait:
        assert 0 < decision.seconds <= MAX_RATE_LIMIT_WAIT_SECONDS
        assert decision.seconds <= ceiling
        assert decision.stage is not None
        assert decision.stage.startswith("rate_wait:")
        assert decision.stage.endswith("s")
        assert decision.exit_status is None
    else:
        assert decision.seconds == 0
        assert decision.stage is None
        assert decision.exit_status == RunStatus.RATE_LIMITED
