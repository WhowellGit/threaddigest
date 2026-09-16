"""Arming the failures, crashes, blocks and hooks the request path then consumes.

Every injection is a queue: planted here, taken in order by ``_Requests``, and checked
at teardown by ``assert_no_unconsumed_injections`` so a scenario that never reached its
planted failure is a red test rather than a silent pass.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from threaddigest.adapters.reddit_fake.items import _Items
from threaddigest.adapters.reddit_fake.records import (
    CRASH_KINDS,
    STATUSES,
    ExcSpec,
    _as_failure,
    _bare,
    _Block,
    _Failure,
    _Hook,
)
from threaddigest.ports import AuthFailed, HtmlBlocked, RateLimited


class _Injection(_Items):
    """The ``fail_*`` / ``crash_after`` / ``block_on`` / ``on_call`` builder surface."""

    def fail_page(self, sub: str, page_no: int, exc: ExcSpec, times: int | None = 1) -> None:
        """Raise ``exc`` when page ``page_no`` (1-based) of ``sub``'s ``/new`` is requested."""
        label = f"fail_page({sub!r}, {page_no})"
        self._page_failures.setdefault((sub.lower(), page_no), []).append(
            _as_failure(exc, times, label)
        )

    def fail_tree(
        self,
        post: str,
        exc: ExcSpec,
        after_comments: int | None = None,
        times: int | None = 1,
    ) -> None:
        """Raise ``exc`` from ``fetch_tree(post)``.

        With ``after_comments=N`` (N > 0) the fake first performs, and counts, the expansions
        needed to reveal N comments, then raises, so ``requests_made`` reads as a mid-tree
        crash; None or 0 raises right after the base request.
        """
        pid = _bare(post)
        self._tree_failures[pid] = (_as_failure(exc, times, f"fail_tree({post!r})"), after_comments)

    def fail_info(self, batch_index: int, exc: ExcSpec, times: int | None = 1) -> None:
        """Raise ``exc`` on the ``batch_index``-th (0-based) 100-item batch of ``info()``."""
        label = f"fail_info({batch_index})"
        self._info_failures.setdefault(batch_index, []).append(_as_failure(exc, times, label))

    def fail_next(self, exc: ExcSpec, times: int | None = 1) -> None:
        """Raise ``exc`` on the next ``times`` requests of any kind."""
        self._next_failures.append(_as_failure(exc, times, "fail_next"))

    def rate_limit_next(self, retry_after: float | None = 60.0, times: int | None = 1) -> None:
        """Answer the next ``times`` requests with ``RateLimited(retry_after)``."""
        self._next_failures.append(
            _Failure(lambda: RateLimited(retry_after), times, "rate_limit_next")
        )

    def set_status(self, sub: str, status: str, path: str | None = None) -> None:
        """Make every request touching ``sub`` raise the matching subreddit error.

        ``status`` is one of ``STATUSES``; ``'ok'`` clears. Unknown subreddits are created.
        """
        if status not in STATUSES:
            msg = f"unknown status {status!r}; expected one of {STATUSES}"
            raise ValueError(msg)
        row = self._sub_row(sub)
        row.status = status
        row.redirect_path = path
        if status == "ok":
            row.info_returns = True

    def set_html_403(self, times: int | None = 1) -> None:
        """Answer the next ``times`` requests with ``HtmlBlocked`` (a Cloudflare page).

        ``times=None`` is forever; ``times <= 0`` clears.
        """
        if times is not None and times <= 0:
            self._html_403 = None
        else:
            self._html_403 = _as_failure(HtmlBlocked, times, "set_html_403")

    def set_auth_failed(self, times: int | None = None) -> None:
        """Every request (``times=None``) or the next ``times`` raise ``AuthFailed``."""
        self._next_failures.append(_as_failure(AuthFailed, times, "set_auth_failed"))

    def crash_after(self, kind: str, n: int) -> None:
        """Raise ``CrashInjected`` when operation ``n+1`` of ``kind`` begins.

        ``kind`` is one of ``CRASH_KINDS``; one-shot (see the module docstring).
        """
        self._check_kind(kind)
        self._crash[kind] = n
        self._completed[kind] = 0

    def block_on(
        self, kind: str, n: int, event: threading.Event, *, timeout: float | None = 30.0
    ) -> None:
        """Park the ``n``-th operation of ``kind`` until ``event`` is set (SIGTERM tests).

        Raises ``TimeoutError`` if the event is not set within ``timeout`` seconds.
        """
        self._check_kind(kind)
        self._blocks.setdefault(kind, []).append(_Block(n, event, timeout))

    def on_call(self, kind: str, n: int, callback: Callable[[], None]) -> None:
        """Run ``callback`` when the ``n``-th operation of ``kind`` begins (to advance a clock)."""
        self._check_kind(kind)
        self._hooks.setdefault(kind, []).append(_Hook(n, callback))

    def assert_no_unconsumed_injections(self) -> None:
        """Fail when a planted failure, crash, block or hook was never reached (panel rule 4)."""
        pending: list[str] = []
        pending += [f.label for f in self._next_failures if f.unconsumed]
        if self._html_403 is not None and self._html_403.unconsumed:
            pending.append(self._html_403.label)
        for queue in self._page_failures.values():
            pending += [f.label for f in queue if f.unconsumed]
        for failure, _ in self._tree_failures.values():
            if failure.unconsumed:
                pending.append(failure.label)
        for queue in self._info_failures.values():
            pending += [f.label for f in queue if f.unconsumed]
        pending += [f"crash_after({kind!r}, {n})" for kind, n in self._crash.items()]
        for kind, blocks in self._blocks.items():
            pending += [f"block_on({kind!r}, {b.n})" for b in blocks if not b.fired]
        for kind, hooks in self._hooks.items():
            pending += [f"on_call({kind!r}, {h.n})" for h in hooks if not h.fired]
        if pending:
            msg = "unconsumed failure injections: " + ", ".join(pending)
            raise AssertionError(msg)

    def _take_tree_failure(self, pid: str) -> tuple[BaseException | None, int | None]:
        entry = self._tree_failures.get(pid)
        if entry is None:
            return None, None
        failure, after_n = entry
        exc = failure.take()
        if exc is None:
            del self._tree_failures[pid]
            return None, None
        return exc, after_n

    @staticmethod
    def _check_kind(kind: str) -> None:
        if kind not in CRASH_KINDS:
            msg = f"unknown operation kind {kind!r}; expected one of {CRASH_KINDS}"
            raise ValueError(msg)
