"""Ports: the Protocols and value types spoken across the services/adapters boundary.

Every payload that crosses a port is a plain ``dict`` in Reddit *wire* shape, i.e. the
``data`` object of a listing child (``{"kind": "t3", "data": {...}}`` minus the envelope).
No PRAW objects ever cross a port, so ``core/`` and ``services/`` never import ``praw``.

Conventions shared by every ``RedditGateway`` implementation:

* ``id`` is the bare base36 id (``"1abc2d"``); ``name`` is the fullname (``"t3_1abc2d"``).
  ``fetch_tree`` accepts either form for ``post_id``; ``info`` takes fullnames only.
* Deleted/removed items keep Reddit's wire markers (``author == "[deleted]"``,
  ``body``/``selftext`` ``"[deleted]"`` or ``"[removed]"``, ``removed_by_category``,
  ``author_fullname`` absent). Interpretation belongs to ``core.deletion``.
* ``requests_made`` counts simulated or real HTTP round-trips, including failed ones
  (a 429 or 5xx is still a request); ``limits()`` never costs a request.
* Iterators are lazy: a page is fetched when the consumer asks for it, so a failure raised
  mid-iteration leaves already-yielded pages intact.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol, runtime_checkable

type RawItem = dict[str, Any]
"""One Reddit object in wire shape (the ``data`` object of a listing child)."""


# --------------------------------------------------------------------------- exceptions
# The exception names are the contract fixed by docs/PLAN.md and the collector design review
# (they read as outcomes: RateLimited, AuthFailed, ...). N818 wants an "Error" suffix; renaming
# would change every caller's spelling for no safety gain, so it is silenced per class.


class GatewayError(Exception):
    """Base class for every error a gateway raises; services catch this, never PRAW's."""


class RateLimited(GatewayError):  # noqa: N818
    """HTTP 429. ``retry_after`` is the header value in seconds, or None when absent."""

    def __init__(self, retry_after: float | None = None, message: str = "rate limited") -> None:
        super().__init__(message)
        self.retry_after = retry_after


class AuthFailed(GatewayError):  # noqa: N818
    """Credentials rejected at the token endpoint (401); nothing else was requested."""


class SubredditForbidden(GatewayError):  # noqa: N818
    """HTTP 403 on a subreddit: private, or otherwise not readable with these credentials."""


class SubredditNotFound(GatewayError):  # noqa: N818
    """HTTP 404 on a subreddit: banned."""


class SubredditRedirected(GatewayError):  # noqa: N818
    """HTTP 3xx on a subreddit: it does not exist (Reddit redirects to ``/subreddits/search``)."""

    def __init__(self, path: str, message: str | None = None) -> None:
        super().__init__(message or f"redirected to {path}")
        self.path = path


class SubredditQuarantined(GatewayError):  # noqa: N818
    """HTTP 403 with the quarantine JSON body; reading requires an opt-in we never give."""


class HtmlBlocked(GatewayError):  # noqa: N818
    """A ``text/html`` 403 (Cloudflare or similar): abort the run, do not retry in a loop."""


class TransientError(GatewayError):
    """5xx, timeout or connection failure after the adapter's own short retries."""


# ------------------------------------------------------------------------ value types


@dataclass(frozen=True, slots=True)
class Page:
    """One page of a listing.

    ``after`` is the cursor to continue from (None once the listing is exhausted);
    ``complete`` is True when nothing remains after this page, False when iteration stopped
    early (``max_pages`` reached) and ``after`` can resume it. A page may hold fewer than
    100 items with a non-None ``after``: Reddit drops removed items after pagination.
    """

    items: list[RawItem]
    after: str | None
    complete: bool


@dataclass(frozen=True, slots=True)
class MoreStub:
    """A ``more`` node left unexpanded in a comment tree.

    ``count == 0`` marks a "continue this thread" link (Reddit's depth limit), which still
    costs one request to expand.
    """

    parent_fullname: str
    count: int
    children: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TreeResult:
    """A comment tree fetch: the (refreshed) post, the flattened comments, and the leftovers.

    ``comments`` is in depth-first order, parents before children, each carrying ``depth``
    (top level is 0), ``parent_id`` and ``link_id``. ``more`` lists the stubs not expanded
    within ``more_limit``; ``complete`` is True only when the fetch succeeded and ``more``
    is empty. ``requests_used`` is 1 for the base fetch plus one per expansion.
    """

    post: RawItem
    comments: list[RawItem]
    more: list[MoreStub]
    requests_used: int
    complete: bool


@dataclass(frozen=True, slots=True)
class Limits:
    """Reddit's rate-limit view of us; both None until the first response has been seen."""

    remaining: int | None
    used: int | None


# --------------------------------------------------------------------------- protocols


@runtime_checkable
class RedditGateway(Protocol):
    """Read-only access to Reddit. One implementation does HTTP; the fake is in-memory."""

    @property
    def requests_made(self) -> int:
        """Total requests issued by this gateway instance (successful and failed)."""
        ...

    def about(self, name: str) -> RawItem:
        """``/r/{name}/about``: the subreddit object. One request. Raises the status errors."""
        ...

    def iter_new_pages(
        self, name: str, *, max_pages: int, after: str | None = None
    ) -> Iterator[Page]:
        """Page ``/r/{name}/new`` forward (never ``before``), 100 items a page, one request each.

        Yields at most ``max_pages`` pages; pass a previous ``Page.after`` as ``after`` to
        resume after a failure. Always yields at least one page (possibly empty) when the
        listing can be read at all.
        """
        ...

    def new_head(self, name: str) -> RawItem | None:
        """The newest non-stickied post in ``/r/{name}/new`` fetching at most 3 items (one request).

        Returns None when the listing is empty or its head is all stickies.
        """
        ...

    def fetch_tree(self, post_id: str, *, more_limit: int) -> TreeResult:
        """Fetch the comment tree of a post, expanding up to ``more_limit`` ``more`` stubs.

        Stubs are expanded largest ``count`` first, one request each, after the base request
        that also refreshes the post.
        """
        ...

    def info(self, fullnames: Sequence[str]) -> list[RawItem]:
        """``/api/info`` for ``t1_``/``t3_``/``t5_`` fullnames, one request per 100.

        Returns only the items Reddit knows, in no guaranteed order: match by ``name``, and
        treat absence as unconfirmed, never as deletion.
        """
        ...

    def search(
        self, query: str, *, sort: str, time_filter: str, max_pages: int = 3
    ) -> Iterator[Page]:
        """``/r/all/search`` pages for a saved search; incomplete by nature, one request a page.

        Reddit caps search at roughly 250 results, hence the default of three pages.
        """
        ...

    def limits(self) -> Limits:
        """Last-seen rate-limit headers; costs nothing; for logging only, not for budgeting."""
        ...


@runtime_checkable
class Clock(Protocol):
    """Time source injected everywhere, so tests control time and never sleep."""

    def now(self) -> int:
        """Current epoch seconds."""
        ...

    def sleep(self, seconds: float) -> None:
        """Block for ``seconds`` (the fake only advances its clock)."""
        ...


@runtime_checkable
class Notifier(Protocol):
    """Best-effort human alerting; implementations never raise."""

    def notify(self, level: str, message: str) -> None:
        """Deliver ``message`` at ``level`` (``"info"``, ``"warning"``, ``"error"``)."""
        ...


@runtime_checkable
class ProcessRunner(Protocol):
    """Spawns the collector from the web UI; injected so tests never start a real child."""

    def spawn(self, argv: Sequence[str], *, env: Mapping[str, str], log_path: Path) -> int:
        """Start ``argv`` detached with exactly ``env`` and stdout/stderr appended to ``log_path``.

        Returns the child's pid.
        """
        ...


__all__ = [
    "AuthFailed",
    "Clock",
    "GatewayError",
    "HtmlBlocked",
    "Limits",
    "MoreStub",
    "Notifier",
    "Page",
    "ProcessRunner",
    "RateLimited",
    "RawItem",
    "RedditGateway",
    "SubredditForbidden",
    "SubredditNotFound",
    "SubredditQuarantined",
    "SubredditRedirected",
    "TransientError",
    "TreeResult",
]
