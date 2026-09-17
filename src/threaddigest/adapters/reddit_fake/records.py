"""Value records, constants and pure helpers the rest of the package is built from.

Nothing here holds gateway state. These are the wire-shape constants, the small records
the store keeps (subreddit rows, ``more`` stubs, armed failures, blocks and hooks), the
one test-only exception, and the pure functions that build ids and payload fragments.
"""

from __future__ import annotations

import threading
import zlib
from collections.abc import Callable
from dataclasses import dataclass, field
from html import escape
from typing import Any, NamedTuple

from threaddigest.ports import RawItem

PAGE_SIZE = 100
LISTING_CAP = 1000
INFO_CHUNK = 100
RATE_WINDOW = 1000
SEARCH_CAP = 250
SEARCH_WINDOWS: dict[str, int | None] = {
    "hour": 3600,
    "day": 86_400,
    "week": 7 * 86_400,
    "month": 31 * 86_400,
    "year": 366 * 86_400,
    "all": None,
}
STATUSES = ("ok", "forbidden", "not_found", "redirect", "quarantined")
CRASH_KINDS = ("request", "page", "tree", "info", "about", "search")
SHAPE_KINDS = ("post", "comment", "subreddit")

type ExcSpec = BaseException | type[BaseException]
type Transform = Callable[[RawItem], RawItem]


class CrashInjected(Exception):  # noqa: N818 - reads as an event, like the ports exceptions
    """The simulated process died here. Deliberately not a ``GatewayError``: nothing catches it."""


class Call(NamedTuple):
    """One recorded gateway call; a plain tuple ``(method, args, kwargs, cost, seq)``."""

    method: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    cost: int
    seq: int


@dataclass
class _Failure:
    make: Callable[[], BaseException]
    times: int | None  # None = every time
    label: str
    fired: int = 0

    def take(self) -> BaseException | None:
        """Return the exception to raise, or None once this failure is used up."""
        if self.times is not None:
            if self.times <= 0:
                return None
            self.times -= 1
        self.fired += 1
        return self.make()

    @property
    def unconsumed(self) -> bool:
        """Armed but never fired: the scenario did not reach it."""
        return self.fired == 0 and (self.times is None or self.times > 0)


@dataclass
class _Sub:
    key: str
    display_name: str
    fullname: str
    subscribers: int
    subreddit_type: str
    over18: bool
    seq: int
    status: str = "ok"
    redirect_path: str | None = None
    frozen: list[str] | None = None
    sticky_first: bool = False
    page_sizes: list[int] = field(default_factory=list)
    overlap: int = 0
    info_returns: bool = True
    about_extra: dict[str, Any] = field(default_factory=dict)


@dataclass(eq=False)  # identity semantics: two look-alike stubs are still two stubs
class _More:
    parent_fullname: str
    count: int
    children: list[str] = field(default_factory=list)
    #: Comment ids this stub's expansion returns *again* although they are already visible.
    #: Reddit's ``morechildren`` is asked with ``limit_children=0``, so a batch overlapping the
    #: base fetch is ordinary; the ids here are not hidden and reveal nothing (KI-042).
    redelivers: list[str] = field(default_factory=list)


@dataclass
class _Block:
    n: int
    event: threading.Event
    timeout: float | None
    fired: bool = False


@dataclass
class _Hook:
    n: int
    callback: Callable[[], None]
    fired: bool = False


def _base36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    out = []
    while n:
        n, r = divmod(n, 36)
        out.append(digits[r])
    return "".join(reversed(out))


def _author_fullname(author: str) -> str:
    return "t2_" + _base36(zlib.crc32(author.encode("utf-8")))


def _html(text: str) -> str | None:
    if not text:
        return None
    return f'<!-- SC_OFF --><div class="md"><p>{escape(text)}</p></div><!-- SC_ON -->'


def _as_failure(exc: ExcSpec, times: int | None, label: str) -> _Failure:
    if isinstance(exc, BaseException):
        return _Failure(lambda: exc, times, label)
    return _Failure(exc, times, label)


def _pop_failure(queue: list[_Failure]) -> BaseException | None:
    """Take from the head of ``queue``, discarding exhausted entries."""
    while queue:
        exc = queue[0].take()
        if exc is not None:
            return exc
        queue.pop(0)
    return None


def _bare(item: str) -> str:
    return item[3:] if item[:3] in {"t1_", "t3_", "t5_"} else item


def _sub_dict(sub: _Sub) -> RawItem:
    about: RawItem = {
        "id": sub.fullname[3:],
        "name": sub.fullname,
        "display_name": sub.display_name,
        "display_name_prefixed": f"r/{sub.display_name}",
        "title": sub.display_name,
        "public_description": "",
        "description": "",
        "subscribers": sub.subscribers,
        "subreddit_type": sub.subreddit_type,
        "over18": sub.over18,
        "quarantine": sub.status == "quarantined",
        "url": f"/r/{sub.display_name}/",
        "created_utc": 1_400_000_000.0,
        "lang": "en",
    }
    about.update(sub.about_extra)
    return about
