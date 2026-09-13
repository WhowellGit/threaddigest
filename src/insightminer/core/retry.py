"""Retry ladder, exception classification, terminal run statuses with their exit codes,
and the two decisions the collector takes when Reddit is rate-limiting or unreachable.

Pure: no I/O, no clock, and no import of adapters, praw, prawcore or requests (the
layering contract forbids it). Exceptions are classified by the names in their class
hierarchy and by duck-typed attributes, so the domain exceptions in
``insightminer.ports``, prawcore's, requests', urllib3's and the standard library's all
classify here without ``core`` knowing any of them.

Sources: docs/PLAN.md "Resilience to outages" (the 30 s / 2 min / 5 min outer ladder,
the ``network`` status retried at two later intervals the same day, the ``Retry-After``
pause capped by the wall-clock ceiling), the failure-mode matrix (429: sleep
``min(retry_after, 300)``), the ingest panel's D-6 (exit codes) and D-7 (a heartbeat
stage such as ``rate_wait:37s`` is written before every sleep so a pause is never
mistaken for a hang).
"""

from __future__ import annotations

import contextlib
import errno
import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import IntEnum, StrEnum
from types import MappingProxyType
from typing import Final

__all__ = [
    "DEFAULT_LADDER_SECONDS",
    "DEFAULT_RATE_LIMIT_WAIT_SECONDS",
    "EXIT_CODES",
    "INTERVALS_PER_DAY",
    "MAX_RATE_LIMIT_WAIT_SECONDS",
    "ExitCode",
    "Outcome",
    "RetryPolicy",
    "RunStatus",
    "WaitDecision",
    "classify",
    "exit_code",
    "plan_rate_limit_wait",
    "should_defer_run",
]

# ----------------------------------------------------------------- retry ladder

#: Seconds to wait after the first, second and third failure of one page, tree or
#: info batch, on top of prawcore's own short retries (docs/PLAN.md, Resilience).
DEFAULT_LADDER_SECONDS: Final[tuple[float, ...]] = (30.0, 120.0, 300.0)


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    """The outer retry ladder around one unit of work.

    ``ladder_seconds[k]`` is the pause after failed attempt ``k + 1``; once the ladder is
    walked the unit of work is given up (``len(ladder) + 1`` attempts in total). The
    ladder must be finite, non-negative and non-decreasing; an empty ladder means the
    first failure is final.
    """

    ladder_seconds: Sequence[float] = DEFAULT_LADDER_SECONDS

    def __post_init__(self) -> None:
        ladder = tuple(float(step) for step in self.ladder_seconds)
        for step in ladder:
            if not math.isfinite(step) or step < 0:
                msg = f"ladder_seconds must be finite and >= 0, got {list(ladder)}"
                raise ValueError(msg)
        for earlier, later in zip(ladder, ladder[1:], strict=False):
            if later < earlier:
                msg = f"ladder_seconds must be non-decreasing, got {list(ladder)}"
                raise ValueError(msg)
        object.__setattr__(self, "ladder_seconds", ladder)

    @property
    def max_attempts(self) -> int:
        """Attempts before the unit of work is given up: one per rung plus the first try."""
        return len(self.ladder_seconds) + 1

    @property
    def total_delay_seconds(self) -> float:
        """Worst-case time spent waiting on this ladder for one unit of work."""
        return float(sum(self.ladder_seconds))

    def next_delay(self, attempt: int) -> float | None:
        """Seconds to pause after failed attempt number ``attempt`` (1-based).

        Returns None once the ladder is exhausted, i.e. when ``attempt`` is at least
        ``max_attempts``: the caller stops retrying and propagates the failure.
        """
        if attempt < 1:
            msg = f"attempt is 1-based, got {attempt}"
            raise ValueError(msg)
        if attempt > len(self.ladder_seconds):
            return None
        return float(self.ladder_seconds[attempt - 1])


# --------------------------------------------------------------- classification


class Outcome(StrEnum):
    """What the collector does with a failure of one unit of work."""

    #: Retry on the ladder: 5xx, timeouts, dropped connections, the adapter's TransientError.
    TRANSIENT = "transient"
    #: Pause for ``Retry-After`` (see ``plan_rate_limit_wait``), then retry once.
    RATE_LIMITED = "rate_limited"
    #: Credentials rejected at the token level: exit 78, nothing is retried.
    AUTH = "auth"
    #: Reddit cannot be reached at all (DNS, connection refused, no route): ladder, then
    #: defer to a later interval (see ``should_defer_run``) with status ``network``.
    NETWORK_DOWN = "network_down"
    #: Never retry; the caller decides the blast radius (one subreddit, one post, the run).
    FATAL = "fatal"


_RATE_LIMIT_NAMES: Final = ("RateLimit", "TooManyRequests")
_AUTH_NAMES: Final = ("AuthFailed", "OAuth", "InvalidToken", "Unauthorized", "InsufficientScope")
#: A bare ``Forbidden`` is prawcore's token-level 403. A 403 scoped to a source
#: (``SubredditForbidden``, ``SubredditQuarantined``) is that source's status, never a
#: credential failure, so those names are excluded from the auth rule.
_FORBIDDEN_SOURCE_SCOPED: Final = ("Subreddit",)
_NETWORK_DOWN_NAMES: Final = (
    "gaierror",
    "NameResolution",
    "NewConnectionError",
    "ConnectionRefused",
    "NetworkUnreachable",
)
_NETWORK_DOWN_ERRNOS: Final = frozenset(
    {errno.ECONNREFUSED, errno.ENETDOWN, errno.ENETUNREACH, errno.EHOSTUNREACH, errno.EHOSTDOWN}
)
_TRANSIENT_NAMES: Final = (
    "Transient",
    "ServerError",
    "ConnectionError",
    "ConnectionReset",
    "ConnectionAborted",
    "BrokenPipe",
    "ReadTimeout",
    "ConnectTimeout",
    "Timeout",
    "RemoteDisconnected",
    "IncompleteRead",
    "ChunkedEncoding",
    "ProtocolError",
    "BadStatusLine",
    "ServiceUnavailable",
    "BadGateway",
)
_CHAIN_DEPTH_LIMIT: Final = 16


def classify(exc: BaseException) -> Outcome:
    """Map any exception to an :class:`Outcome`; never raises.

    Rules, most specific first, over the names in the exception's class hierarchy and
    its duck-typed attributes (``retry_after``, ``status_code`` / ``response.status_code``,
    ``errno``):

    1. ``rate_limited``: a ``retry_after`` attribute, a name containing ``RateLimit`` or
       ``TooManyRequests``, or HTTP 429.
    2. ``auth``: names containing ``AuthFailed``, ``OAuth``, ``InvalidToken``,
       ``Unauthorized``, ``InsufficientScope``; a bare ``Forbidden`` (token level, not the
       ``Subreddit``-scoped 403s); or HTTP 401.
    3. ``network_down``: DNS failure (``gaierror``, ``NameResolution``), connection refused,
       no route or network down (by name or ``errno``).
    4. ``transient``: connection errors, timeouts, dropped connections, 5xx, and names
       containing ``Transient``, ``ServerError``, ``ConnectionError``, ``ReadTimeout``.
    5. ``fatal``: everything else, including ``KeyboardInterrupt`` and ``SystemExit``.

    A ``transient`` wrapper (``requests.ConnectionError``, the adapter's ``TransientError``)
    is walked down its ``__cause__`` / ``__context__`` / ``args`` / ``reason`` chain, and a
    ``network_down`` root cause wins: an outage looks like a connection error one layer up.
    No other outcome inherits from its cause, so a ``SubredditForbidden`` raised *from*
    prawcore's ``Forbidden`` stays a per-source ``fatal``.
    """
    outcome = _classify_one(exc)
    if outcome is Outcome.TRANSIENT and any(
        _classify_one(link) is Outcome.NETWORK_DOWN for link in _chain(exc)
    ):
        return Outcome.NETWORK_DOWN
    return outcome


def _classify_one(exc: BaseException) -> Outcome:
    names = _type_names(exc)
    status = _http_status(exc)
    if _has_attribute(exc, "retry_after") or _matches(names, _RATE_LIMIT_NAMES) or status == 429:
        return Outcome.RATE_LIMITED
    if _matches(names, _AUTH_NAMES) or status == 401 or _token_level_forbidden(names):
        return Outcome.AUTH
    if _matches(names, _NETWORK_DOWN_NAMES) or _errno_of(exc) in _NETWORK_DOWN_ERRNOS:
        return Outcome.NETWORK_DOWN
    if _matches(names, _TRANSIENT_NAMES) or (status is not None and 500 <= status <= 599):
        return Outcome.TRANSIENT
    return Outcome.FATAL


def _type_names(exc: BaseException) -> tuple[str, ...]:
    return tuple(cls.__name__ for cls in type(exc).__mro__ if cls is not object)


def _matches(names: Sequence[str], needles: Sequence[str]) -> bool:
    return any(needle in name for name in names for needle in needles)


def _token_level_forbidden(names: Sequence[str]) -> bool:
    return any(
        "Forbidden" in name and not any(scope in name for scope in _FORBIDDEN_SOURCE_SCOPED)
        for name in names
    )


_MISSING: Final = object()


def _safe_getattr(obj: object, name: str) -> object:
    """``getattr`` that cannot raise: a property that blows up counts as absent.

    The classifier must never raise for any exception object, so the one place it runs
    foreign code (attribute access on an unknown type) is fenced off completely.
    """
    value: object = _MISSING
    with contextlib.suppress(Exception):
        value = getattr(obj, name, _MISSING)
    return value


def _has_attribute(exc: BaseException, name: str) -> bool:
    return _safe_getattr(exc, name) is not _MISSING


def _http_status(exc: BaseException) -> int | None:
    for candidate in (
        _safe_getattr(exc, "status_code"),
        _safe_getattr(exc, "status"),
        _safe_getattr(_safe_getattr(exc, "response"), "status_code"),
        _safe_getattr(_safe_getattr(exc, "response"), "status"),
    ):
        if (
            isinstance(candidate, int)
            and not isinstance(candidate, bool)
            and 100 <= candidate < 600
        ):
            return candidate
    return None


def _errno_of(exc: BaseException) -> int | None:
    value = _safe_getattr(exc, "errno")
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


def _chain(exc: BaseException) -> Iterator[BaseException]:
    """Every exception reachable from ``exc`` (excluded) through the usual wrapping links.

    Bounded and cycle-safe: ``__cause__``, ``__context__``, exception-typed ``args`` and a
    urllib3-style ``reason`` attribute, breadth-first, at most ``_CHAIN_DEPTH_LIMIT`` hops.
    """
    seen = {id(exc)}
    frontier: list[BaseException] = [exc]
    for _ in range(_CHAIN_DEPTH_LIMIT):
        if not frontier:
            return
        next_frontier: list[BaseException] = []
        for current in frontier:
            for link in _links(current):
                if id(link) in seen:
                    continue
                seen.add(id(link))
                next_frontier.append(link)
                yield link
        frontier = next_frontier


def _links(exc: BaseException) -> list[BaseException]:
    candidates: list[object] = [
        _safe_getattr(exc, "__cause__"),
        _safe_getattr(exc, "__context__"),
        _safe_getattr(exc, "reason"),
    ]
    args = _safe_getattr(exc, "args")
    if isinstance(args, tuple):
        candidates.extend(args)
    return [candidate for candidate in candidates if isinstance(candidate, BaseException)]


# ------------------------------------------------------- statuses and exit codes


class RunStatus(StrEnum):
    """Terminal values of ``runs.status`` (``queued`` and ``running`` are not terminal)."""

    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    NETWORK = "network"
    CANCELLED = "cancelled"
    CRASHED = "crashed"
    SKIPPED_LOCKED = "skipped_locked"


class ExitCode(IntEnum):
    """Process exit codes (docs/decisions/DECISIONS.md section 6, ingest panel D-6).

    ``CONFIG`` (78, ``EX_CONFIG``) is raised before a run row exists, for settings and
    credential failures, so it has no :class:`RunStatus`; ``SKIPPED_LOCKED`` is 75
    (``EX_TEMPFAIL``) and ``CANCELLED`` is 130 (SIGINT convention).
    """

    OK = 0
    FAILED = 1
    PARTIAL = 3
    RATE_LIMITED = 4
    NETWORK = 5
    SKIPPED_LOCKED = 75
    CONFIG = 78
    CANCELLED = 130


#: Total over :class:`RunStatus` (tested); ``crashed`` shares 1 with ``failed`` because a
#: crashed process already exited with a generic failure and the status is stamped later.
EXIT_CODES: Final[Mapping[RunStatus, ExitCode]] = MappingProxyType(
    {
        RunStatus.OK: ExitCode.OK,
        RunStatus.PARTIAL: ExitCode.PARTIAL,
        RunStatus.FAILED: ExitCode.FAILED,
        RunStatus.RATE_LIMITED: ExitCode.RATE_LIMITED,
        RunStatus.NETWORK: ExitCode.NETWORK,
        RunStatus.CANCELLED: ExitCode.CANCELLED,
        RunStatus.CRASHED: ExitCode.FAILED,
        RunStatus.SKIPPED_LOCKED: ExitCode.SKIPPED_LOCKED,
    }
)


def exit_code(status: RunStatus) -> int:
    """The process exit code for a run that ended with ``status``."""
    return int(EXIT_CODES[status])


# -------------------------------------------------------------- rate-limit waits

#: Pause when a 429 carries no usable ``Retry-After``.
DEFAULT_RATE_LIMIT_WAIT_SECONDS: Final = 60.0
#: Longest in-process pause for a 429 (failure matrix: sleep ``min(retry_after, 300)``).
MAX_RATE_LIMIT_WAIT_SECONDS: Final = 300.0


@dataclass(frozen=True, slots=True)
class WaitDecision:
    """Pause in this process, or end the run.

    When ``should_wait`` is True the caller writes ``stage`` to the run row's heartbeat
    (``rate_wait:37s``: the stale-run detector treats it as alive), sleeps ``seconds`` on
    the injected clock, and retries once. Otherwise the run ends with ``exit_status`` and
    the next scheduled interval resumes from the watermark and revisit queue.
    """

    should_wait: bool
    seconds: float
    stage: str | None
    exit_status: RunStatus | None


def plan_rate_limit_wait(
    retry_after: float | None, remaining_ceiling_seconds: float
) -> WaitDecision:
    """Decide how to honour a 429.

    The pause is ``min(retry_after or 60, 300)`` seconds; a missing, zero, negative or NaN
    ``retry_after`` counts as absent. If the pause fits within the run's remaining
    wall-clock ceiling the run waits and resumes in the same process; otherwise it ends
    as ``rate_limited`` (exit 4) rather than sleeping into the ceiling.
    """
    if retry_after is None or math.isnan(retry_after) or retry_after <= 0:
        wait = DEFAULT_RATE_LIMIT_WAIT_SECONDS
    else:
        wait = float(retry_after)
    wait = min(wait, MAX_RATE_LIMIT_WAIT_SECONDS)
    if wait <= remaining_ceiling_seconds:
        return WaitDecision(
            should_wait=True,
            seconds=wait,
            stage=f"rate_wait:{math.ceil(wait)}s",
            exit_status=None,
        )
    return WaitDecision(
        should_wait=False, seconds=0.0, stage=None, exit_status=RunStatus.RATE_LIMITED
    )


# ------------------------------------------------------------- deferring a run

#: launchd runs the collector at 06:30, 12:30 and 18:30 (docs/PLAN.md, Resilience).
INTERVALS_PER_DAY: Final = 3


def should_defer_run(consecutive_network_failures: int, attempts_today: int) -> bool:
    """True when a run that cannot reach Reddit should end now as ``network`` and leave the
    work to a later interval today, instead of hammering the ladder in this process.

    ``consecutive_network_failures`` counts the network-down failures in a row *including*
    this one (0 means nothing to defer). ``attempts_today`` counts today's scheduled runs
    including this one (1 at 06:30, 2 at 12:30, 3 at 18:30).

    Deferral is quiet by design (the later interval makes the earlier one a near no-op),
    so it is only the right call while a later interval remains today and the outage is
    younger than a day's worth of intervals. On the day's last interval, or once
    ``INTERVALS_PER_DAY`` failures have accumulated, the run still ends ``network`` but
    the caller escalates (notification, digest line) rather than waiting for a scheduler
    that has already run out of chances.
    """
    if consecutive_network_failures < 0:
        msg = f"consecutive_network_failures must be >= 0, got {consecutive_network_failures}"
        raise ValueError(msg)
    if attempts_today < 1:
        msg = f"attempts_today includes the current run and must be >= 1, got {attempts_today}"
        raise ValueError(msg)
    return (
        1 <= consecutive_network_failures < INTERVALS_PER_DAY and attempts_today < INTERVALS_PER_DAY
    )
