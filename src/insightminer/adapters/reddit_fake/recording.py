"""Simulated round-trips: counting them, recording them, and consuming injections.

``_record`` opens a gateway call, ``_begin``/``_done`` bracket one operation of a crash
kind, and ``_request`` is the single place a simulated HTTP round-trip is counted and
charged to the call that caused it. The global injections (HTML 403, the ``fail_next``
queue, crashes, blocks and hooks) are taken here, in the order the module docstring
lists.
"""

from __future__ import annotations

from typing import Any

from insightminer.adapters.reddit_fake.injection import _Injection
from insightminer.adapters.reddit_fake.records import Call, CrashInjected, _bare, _pop_failure


class _Requests(_Injection):
    """Request accounting and the consumption side of every injection."""

    @property
    def requests_made(self) -> int:
        return self._requests_made

    def count(self, method: str) -> int:
        """Number of recorded calls of ``method``."""
        return sum(1 for c in self.calls if c.method == method)

    def fullnames_requested(self, method: str) -> list[str]:
        """Items asked of ``method``: flattened fullnames for ``info``, ``t3_`` ids for
        ``fetch_tree``, the first argument for everything else."""
        out: list[str] = []
        for call in self.calls:
            if call.method != method:
                continue
            if method == "info":
                out.extend(str(fn) for fn in call.args[0])
            elif method == "fetch_tree":
                out.append(f"t3_{_bare(str(call.args[0]))}")
            elif call.args:
                out.append(str(call.args[0]))
        return out

    def _record(self, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> int:
        index = len(self.calls)
        self.calls.append(Call(method, args, kwargs, 0, index + 1))
        self._current_call = index
        return index

    def _request(self, label: str) -> None:
        """One simulated HTTP round-trip: count it, then apply global failure injections."""
        self._begin("request")
        self._requests_made += 1
        self.requests.append(label)
        if self._current_call is not None:
            call = self.calls[self._current_call]
            self.calls[self._current_call] = call._replace(cost=call.cost + 1)
        if self._html_403 is not None:
            exc = self._html_403.take()
            if exc is not None:
                raise exc
            self._html_403 = None
        exc = _pop_failure(self._next_failures)
        if exc is not None:
            raise exc
        self._done("request")

    def _begin(self, kind: str) -> None:
        n = self._crash.get(kind)
        if n is not None and self._completed.get(kind, 0) >= n:
            del self._crash[kind]
            msg = f"crash injected after {n} {kind} operation(s)"
            raise CrashInjected(msg)
        started = self._started.get(kind, 0) + 1
        self._started[kind] = started
        for hook in self._hooks.get(kind, []):
            if hook.n == started and not hook.fired:
                hook.fired = True
                hook.callback()
        for block in self._blocks.get(kind, []):
            if block.n == started and not block.fired:
                block.fired = True
                if not block.event.wait(block.timeout):
                    msg = f"block_on({kind!r}, {block.n}) waited {block.timeout}s"
                    raise TimeoutError(msg)

    def _done(self, kind: str) -> None:
        self._completed[kind] = self._completed.get(kind, 0) + 1
