"""``PrawGateway``: the one adapter that speaks HTTP to Reddit, over PRAW.

This module is the only place in the package that may import ``praw`` or ``prawcore``
(``.importlinter``'s ``praw-only-in-the-adapter`` contract, guard G05). Everything it hands
back is a plain value from ``ports.py``: wire-shape dicts, ``Page``, ``TreeResult``,
``Limits``. No PRAW object crosses the boundary, and no PRAW exception does either --
``translate`` is the single site that maps the library's exception hierarchy onto the
port's, so ``services/`` catches ``GatewayError`` and nothing else.

Three things are worth knowing before changing anything here.

**Counting.** ``requests_made`` is what the run budget reads, and the budget is one of the
irreversible rules ("never run an unbounded fetch"). The counter is a ``requests.Session``
subclass handed to PRAW through ``requestor_kwargs``: every data request, every prawcore
retry, and every OAuth token refresh goes through ``Requestor.request`` and therefore
through one ``Session.request`` override. Counting there, before the call rather than after
it, is what makes a failed round-trip count -- which is exactly the port's contract. A
caller that injects its own ``praw.Reddit`` must hand over the counting session with it, or
construction is refused: a gateway that cannot see its own round-trips would report a budget
of zero forever.

**Retries happen below us.** prawcore retries 5xx, 408, 520 and 522 statuses and connection
errors twice before the exception reaches this module, sleeping between attempts, and it
refreshes the token and retries on a 401. So a ``ServerError`` here has already cost three
round-trips, and the counter shows all three. This module adds no retry of its own.

**Raw JSON, not objects.** Every method goes through ``Reddit.request``, which returns the
parsed JSON un-objectified. Walking PRAW's lazy model objects instead would fire a request
on any attribute the object has not loaded (plan § Collector algorithm step 2), which would
be a fetch the budget never authorised.

What is *not* settled offline is marked in place: the quarantine predicate (probe P-07), the
``/comments`` limit clamp and its ``more`` chunking (P-08, P-11, P-20), and the wire shapes
the contract suite will compare against ``adapters.reddit_fake`` (spec AD-04). The checklist
is ``docs/runbook/RUNBOOK.md`` § 9.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from typing import Any, Final

import praw
import prawcore
import requests

from threaddigest.adapters.clock import SystemClock
from threaddigest.ports import (
    AuthFailed,
    Clock,
    GatewayError,
    HtmlBlocked,
    Limits,
    MoreStub,
    Page,
    RateLimited,
    RawItem,
    SubredditForbidden,
    SubredditNotFound,
    SubredditQuarantined,
    SubredditRedirected,
    TransientError,
    TreeResult,
)

# Reddit's own wire constants. ``adapters.reddit_fake`` holds the same three numbers for the
# simulated side; the contract suite (AD-04) is what proves the two agree, on the probe day.
PAGE_SIZE: Final = 100
INFO_CHUNK: Final = 100
MORE_CHUNK: Final = 100

#: ``time_filter`` values ``/search`` accepts; the fake refuses the same set.
SEARCH_WINDOWS: Final = frozenset({"hour", "day", "week", "month", "year", "all"})

UNAUTHORIZED: Final = 401
DEFAULT_TIMEOUT: Final = 30

#: Keys a 403 body carries when the subreddit is quarantined. Provisional: see
#: :func:`_names_a_quarantine`.
QUARANTINE_KEYS: Final = ("quarantine_message", "quarantine_message_html")


@dataclass(frozen=True, slots=True)
class PrawConfig:
    """Everything PRAW needs, as plain values.

    Not a ``Settings`` object on purpose: ``cli`` constructs collaborators and passes values
    (the services rule), and a test builds one of these in a line.
    """

    client_id: str
    client_secret: str
    user_agent: str
    timeout: int = DEFAULT_TIMEOUT


class CountingSession(requests.Session):
    """Counts every HTTP round-trip, success or failure, including retries and token refreshes.

    The count is incremented *before* the call, so a request that dies in the socket counts
    like a 429 does: the port's ``requests_made`` promises attempts, not successes, because
    that is what a budget has to spend.
    """

    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def request(self, method: str, url: Any, *args: Any, **kwargs: Any) -> requests.Response:
        self.count += 1
        return super().request(method, url, *args, **kwargs)


def build_reddit(config: PrawConfig, *, session: requests.Session) -> praw.Reddit:
    """A read-only ``praw.Reddit`` whose HTTP goes through ``session``.

    ``check_for_updates=False`` matters: PRAW ships that setting on, and the update checker
    is installed, so a bare constructor fires an HTTPS request to the package index before
    any Reddit call. Read-only mode is client id and secret with no username, password or
    refresh token (settled negative N-03): PRAW then leaves the read-only authorizer in
    place, which is the only authorisation this project ever wants.
    """
    return praw.Reddit(
        client_id=config.client_id,
        client_secret=config.client_secret,
        user_agent=config.user_agent,
        timeout=config.timeout,
        check_for_updates=False,
        check_for_async=False,
        requestor_kwargs={"session": session},
    )


# ------------------------------------------------------------------- exception translation


def _seconds(raw: str | None, *, now: float) -> float | None:
    """``Retry-After`` as a wait in seconds. prawcore hands over the raw header string or None.

    RFC 9110 allows two forms and Reddit may send either: a number of seconds, or an HTTP date
    naming the instant the ban lifts. The date is turned into a wait against ``now``, the
    adapter's own clock. None means "no usable value", which is what the caller's ladder falls
    back on (``core.retry.plan_rate_limit_wait``'s sixty-second default): an unreadable header,
    or a date already in the past, is a header this adapter will not guess at -- but never a
    reason to call a 429 anything other than rate limited (KI-041).
    """
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        pass
    try:
        deadline = parsedate_to_datetime(raw).timestamp()
    except (TypeError, ValueError):
        return None
    wait = deadline - now
    return wait if wait > 0 else None


def _names_a_quarantine(response: requests.Response) -> bool:
    """Does this 403 body say the subreddit is quarantined?

    **Provisional until probe P-07** (``docs/runbook/RUNBOOK.md`` § 9), which captures a real
    quarantined 403 with a read-only token. Until that capture exists this predicate is a
    reading of Reddit's documented body shape, not an observed one; a quarantined subreddit
    that fails the test here is reported as ``SubredditForbidden``, which is the safe way to
    be wrong (the source is skipped either way, and no content is read).
    """
    try:
        body = response.json()
    except ValueError:
        return False
    if not isinstance(body, dict):
        return False
    if str(body.get("reason", "")).lower() == "quarantined":
        return True
    return any(key in body for key in QUARANTINE_KEYS)


def _from_too_many_requests(
    exc: prawcore.exceptions.TooManyRequests, *, now: float
) -> GatewayError:
    return RateLimited(retry_after=_seconds(exc.retry_after, now=now))


def _from_forbidden(exc: prawcore.exceptions.Forbidden) -> GatewayError:
    """The three shapes a 403 arrives in: an edge block, a quarantine, a private subreddit."""
    if exc.response.headers.get("content-type", "").startswith("text/html"):
        return HtmlBlocked("403 served as text/html: an edge block, not Reddit's API")
    if _names_a_quarantine(exc.response):
        return SubredditQuarantined("403 with a quarantine body")
    return SubredditForbidden("403: private, or not readable with these credentials")


def _from_redirect(exc: prawcore.exceptions.Redirect) -> GatewayError:
    return SubredditRedirected(path=exc.path)


def _from_response(exc: prawcore.exceptions.ResponseException) -> GatewayError:
    """Every ``ResponseException`` the rows above did not claim.

    A 401 is a credentials failure wherever it arrives (the token endpoint raises a bare
    ``ResponseException``, not an OAuth one). The rest -- an insufficient scope, a malformed
    request, a conflict, an over-long URI -- are programming errors: named, never swallowed.
    """
    if exc.response.status_code == UNAUTHORIZED:
        return AuthFailed(f"credentials rejected: {exc}")
    return GatewayError(f"{type(exc).__name__}: {exc}")


def _auth_failed(exc: Exception) -> GatewayError:
    return AuthFailed(f"credentials rejected: {exc}")


#: The one library frame the bare-``KeyError`` handler in :meth:`PrawGateway._get` was written
#: for: ``prawcore/util.py::authorization_error_class`` looks a 401's ``www-authenticate`` error
#: up in a three-entry mapping, so an absent header, or an error outside the table, raises a
#: ``KeyError`` there instead of one of prawcore's own exceptions.
_OAUTH_TABLE_FRAME: Final = ("authorization_error_class", "prawcore/util.py")
#: prawcore's rate limiter decides a response carries rate-limit headers by testing for this
#: one alone, then reads ``x-ratelimit-used`` and ``x-ratelimit-reset`` by subscript, so a
#: half-present set raises a ``KeyError`` naming the missing header on an ordinary 200.
RATE_LIMIT_HEADER_PREFIX: Final = "x-ratelimit"


#: The library frame the ``ValueError`` handler in :meth:`PrawGateway._get` was written for.
#: ``prawcore/exceptions.py::TooManyRequests.__init__`` formats ``Retry-After`` with ``float()``
#: while composing its own message, and it does so *after* binding the response and the header
#: to ``self``. So the HTTP-date form RFC 9110 also allows kills the exception in its own
#: constructor -- ``translate`` never sees a ``TooManyRequests`` at all -- while the half-built
#: instance is still reachable through the raising frame (KI-041).
_TOO_MANY_REQUESTS_FRAME: Final = ("__init__", "prawcore/exceptions.py")


def _half_built_rate_limit(exc: ValueError) -> prawcore.exceptions.TooManyRequests | None:
    """The ``TooManyRequests`` prawcore was building when this ``ValueError`` escaped, or None.

    Identified by the frame it was raised in and by what that frame was building, the way
    :func:`_raised_in_the_oauth_table` identifies its own: a ``ValueError`` from anywhere else
    is still an answer the adapter could not read, and stays a ``GatewayError``.
    """
    name, tail = _TOO_MANY_REQUESTS_FRAME
    trace = exc.__traceback__
    while trace is not None:
        code = trace.tb_frame.f_code
        if code.co_name == name and code.co_filename.replace("\\", "/").endswith(tail):
            building = trace.tb_frame.f_locals.get("self")
            if isinstance(building, prawcore.exceptions.TooManyRequests):
                return building
        trace = trace.tb_next
    return None


def _raised_in_the_oauth_table(exc: KeyError) -> bool:
    """True when this ``KeyError`` came out of prawcore's OAuth error table.

    Identified by the frame it was raised in, not by being the only ``KeyError`` the library
    can produce, which is what KI-030 proved it is not.
    """
    name, tail = _OAUTH_TABLE_FRAME
    trace = exc.__traceback__
    while trace is not None:
        code = trace.tb_frame.f_code
        if code.co_name == name and code.co_filename.replace("\\", "/").endswith(tail):
            return True
        trace = trace.tb_next
    return False


def _from_key_error(exc: KeyError) -> GatewayError:
    """The three shapes a bare ``KeyError`` out of ``Reddit.request`` arrives in (KI-030).

    The OAuth-table miss is a credentials failure and says so. A half-present rate-limit header
    set is a malformed answer to a request that otherwise succeeded, and reporting it as
    rejected credentials would send an operator to fix credentials that work. Anything else is
    named rather than swallowed, because nothing from the library may reach a service
    untranslated.
    """
    if _raised_in_the_oauth_table(exc):
        return AuthFailed(f"unrecognised OAuth error: {exc}")
    key = exc.args[0] if exc.args else ""
    if isinstance(key, str) and key.lower().startswith(RATE_LIMIT_HEADER_PREFIX):
        return GatewayError(f"Reddit's rate-limit headers are malformed: {exc} is missing")
    return GatewayError(f"the library read a key Reddit's answer does not carry: {exc}")


def _not_found(exc: Exception) -> GatewayError:
    return SubredditNotFound(f"404: {exc}")


def _forbidden(exc: Exception) -> GatewayError:
    """451 is per-source, not fatal: the run skips this source and carries on (see DECISIONS)."""
    return SubredditForbidden(f"unavailable for legal reasons: {exc}")


def _transient(exc: Exception) -> GatewayError:
    return TransientError(f"{type(exc).__name__}: {exc}")


def _programming_error(exc: Exception) -> GatewayError:
    return GatewayError(f"{type(exc).__name__}: {exc}")


#: Walked in order, so a subclass row must precede its base. Splitting the table from the
#: dispatch is what keeps ``translate`` itself under the complexity ceilings. ``TooManyRequests``
#: is deliberately not a row: it is the one translation that needs the clock (an HTTP-date
#: ``Retry-After`` is an instant, and the port promises a wait), so ``translate`` takes it first,
#: ahead of its base class ``ResponseException`` exactly as a row here would have.
_TRANSLATIONS: Final[tuple[tuple[type[BaseException], Callable[[Any], GatewayError]], ...]] = (
    (prawcore.exceptions.Forbidden, _from_forbidden),
    (prawcore.exceptions.InvalidToken, _auth_failed),
    (prawcore.exceptions.OAuthException, _auth_failed),
    (prawcore.exceptions.NotFound, _not_found),
    (prawcore.exceptions.Redirect, _from_redirect),
    (prawcore.exceptions.UnavailableForLegalReasons, _forbidden),
    (prawcore.exceptions.ServerError, _transient),
    (prawcore.exceptions.BadJSON, _transient),
    (prawcore.exceptions.RequestException, _transient),
    (praw.exceptions.MissingRequiredAttributeException, _auth_failed),
    (prawcore.exceptions.ResponseException, _from_response),
    (prawcore.exceptions.PrawcoreException, _programming_error),
    (praw.exceptions.PRAWException, _programming_error),
)


def translate(exc: Exception, *, now: float | None = None) -> GatewayError:
    """Map one PRAW or prawcore exception onto the port's vocabulary.

    The table above is the contract; this function is only its dispatch. An exception that
    matches no row still becomes a ``GatewayError`` rather than escaping, because a service
    that catches the port's base class must not be bypassed by a library exception nobody
    anticipated.

    ``now`` is the epoch second an absolute ``Retry-After`` is measured from; the gateway
    passes its injected clock. It defaults to the wall clock so a caller translating an
    exception by hand needs no clock of its own.
    """
    if isinstance(exc, prawcore.exceptions.TooManyRequests):
        return _from_too_many_requests(exc, now=time.time() if now is None else now)
    for kind, build in _TRANSLATIONS:
        if isinstance(exc, kind):
            return build(exc)
    return GatewayError(f"untranslated {type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------- wire helpers


def _bare(fullname: str) -> str:
    """``"t3_1abc2d"`` or ``"1abc2d"`` -> ``"1abc2d"``."""
    return fullname.split("_", 1)[1] if "_" in fullname else fullname


def _data_of(thing: Any) -> RawItem:
    """The ``data`` object of a ``{"kind": ..., "data": {...}}`` envelope, copied."""
    if isinstance(thing, dict):
        data = thing.get("data")
        if isinstance(data, dict):
            return {str(key): value for key, value in data.items()}
    msg = f"expected a Reddit envelope, got {type(thing).__name__}"
    raise GatewayError(msg)


def _listing_children(payload: Any) -> list[Any]:
    """The ``children`` array of a listing; empty for Reddit's ``""`` placeholder."""
    if not isinstance(payload, dict):
        return []
    children = _data_of(payload).get("children")
    return children if isinstance(children, list) else []


def _page_of(payload: Any) -> tuple[list[RawItem], str | None]:
    """One listing as the port sees it: its items and the cursor to continue from."""
    after = _data_of(payload).get("after")
    items = [_data_of(child) for child in _listing_children(payload)]
    return items, after if isinstance(after, str) else None


class _TreeBuilder:
    """A comment tree under construction: comments indexed by parent, plus the unexpanded stubs.

    Both the base ``/comments`` fetch and every ``morechildren`` batch feed the same index,
    so the depth-first order and the depths are computed once, at the end, from the parent
    links -- never from the order things arrived in or from Reddit's own ``depth`` field,
    which is absent from a ``morechildren`` batch.

    Reddit may deliver the same comment twice. ``morechildren`` is asked with
    ``limit_children=0``, so a batch overlapping the base fetch is the expected case, not an
    oddity: the index therefore keeps the first copy of each ``name`` and drops later ones
    (KI-042). A later copy's *replies* are still walked, because the rule is one row per
    comment and a second copy may carry a reply the first did not.
    """

    def __init__(self, link: str) -> None:
        self.link = link
        self.by_parent: dict[str, list[RawItem]] = {}
        self.pending: list[MoreStub] = []
        self.seen: set[str] = set()

    def add(self, thing: Any) -> None:
        """Index one ``t1`` comment (and its nested replies) or queue one ``more`` stub."""
        if not isinstance(thing, dict):
            return
        kind = thing.get("kind")
        if kind == "more":
            self._queue(_data_of(thing))
            return
        if kind != "t1":
            return
        data = _data_of(thing)
        replies = data.pop("replies", "")
        name = str(data.get("name", ""))
        if not name or name not in self.seen:
            self.seen.add(name)
            self.by_parent.setdefault(str(data.get("parent_id", self.link)), []).append(data)
        for child in _listing_children(replies):
            self.add(child)

    def _queue(self, data: RawItem) -> None:
        children = data.get("children")
        self.pending.append(
            MoreStub(
                parent_fullname=str(data.get("parent_id", self.link)),
                count=int(data.get("count", 0)),
                children=[str(child) for child in children] if isinstance(children, list) else [],
            )
        )

    def take_next(self) -> MoreStub | None:
        """The stub to expand next -- largest ``count`` first, earliest queued on ties -- removed.

        A stub holding more than ``MORE_CHUNK`` children is split and the remainder queued
        again, because ``morechildren`` reveals at most a hundred comments per request
        (KI-023). The real chunk size is confirmed on the probe day (P-20).

        The split *divides* the stub's ``count`` and never relabels it (KI-043): the chunk
        fetched now carries one hidden comment per id it holds, the remainder carries
        everything the whole stub claimed beyond that, and the parts sum to the whole. Neither
        part ever claims fewer hidden comments than it holds ids, which only bites on a stub
        whose wire ``count`` is already smaller than its own child list.
        """
        if not self.pending:
            return None
        index = max(range(len(self.pending)), key=lambda i: (self.pending[i].count, -i))
        stub = self.pending.pop(index)
        if len(stub.children) <= MORE_CHUNK:
            return stub
        head, tail = stub.children[:MORE_CHUNK], stub.children[MORE_CHUNK:]
        behind_tail = max(stub.count - len(head), len(tail))
        behind_head = max(stub.count - behind_tail, len(head))
        self.pending.append(MoreStub(stub.parent_fullname, behind_tail, tail))
        return MoreStub(stub.parent_fullname, behind_head, head)

    def ordered(self) -> list[RawItem]:
        """Every comment in depth-first order, parents before children, each stamped ``depth``."""
        out: list[RawItem] = []
        stack = [(item, 0) for item in reversed(self.by_parent.get(self.link, []))]
        while stack:
            item, depth = stack.pop()
            item["depth"] = depth
            out.append(item)
            replies = self.by_parent.get(str(item.get("name", "")), [])
            stack.extend((reply, depth + 1) for reply in reversed(replies))
        return out


# ------------------------------------------------------------------------------- gateway


class PrawGateway:
    """``ports.RedditGateway`` over PRAW: structural, not nominal (the Protocol is runtime
    checkable, and nothing here inherits from it)."""

    def __init__(
        self,
        config: PrawConfig,
        *,
        reddit: praw.Reddit | None = None,
        session: CountingSession | None = None,
        clock: Clock | None = None,
    ) -> None:
        """Build the gateway, or refuse.

        ``reddit`` and ``session`` are one seam, not two: an injected client must arrive with
        the counting session it speaks through, or ``requests_made`` would report zero for
        every round-trip it makes and the budget would never close.

        ``clock`` is read for one thing only: a ``Retry-After`` that arrives as an HTTP date
        names an instant, and the port promises a wait, so the difference is taken against an
        injected clock rather than the wall clock a test cannot fix.
        """
        if reddit is not None and session is None:
            msg = "an injected praw.Reddit must arrive with the CountingSession it speaks through"
            raise GatewayError(msg)
        self._session = session if session is not None else CountingSession()
        self._clock = clock if clock is not None else SystemClock()
        try:
            self._reddit = (
                reddit if reddit is not None else build_reddit(config, session=self._session)
            )
        except (prawcore.exceptions.PrawcoreException, praw.exceptions.PRAWException) as exc:
            raise translate(exc, now=self._clock.now()) from exc
        if not self._reddit.read_only:
            msg = "this gateway is read-only; build it from a client id and secret alone"
            raise GatewayError(msg)

    # ------------------------------------------------------------------ plumbing

    @property
    def requests_made(self) -> int:
        return self._session.count

    def _get(self, path: str, params: dict[str, str | int] | None = None) -> Any:
        """One GET through PRAW, with every library exception translated at this one site."""
        try:
            return self._reddit.request(method="GET", path=path, params=params)
        except (prawcore.exceptions.PrawcoreException, praw.exceptions.PRAWException) as exc:
            raise translate(exc, now=self._clock.now()) from exc
        except KeyError as exc:
            # A bare KeyError arrives here from more than one place in the library, and they
            # are different failures: the OAuth error table on a 401 prawcore cannot name, and
            # the rate limiter on a half-present ``x-ratelimit`` header set (KI-030). Whichever
            # it is, it must reach the CLI's exit 78 rather than a traceback.
            raise _from_key_error(exc) from exc
        except ValueError as exc:
            # The other way prawcore fails while building its own exception: it formats
            # ``Retry-After`` with ``float()``, so a 429 carrying the HTTP-date form the
            # standard also allows dies inside ``TooManyRequests`` before it is ever raised.
            # Reddit refused us, and that is the fact the run has to act on: the half-built
            # exception is recovered from the raising frame and translated like any other 429
            # (KI-041). Anything else is an answer the library could not describe, and is
            # recorded as that rather than as a raw traceback.
            building = _half_built_rate_limit(exc)
            if building is not None:
                raise _from_too_many_requests(building, now=self._clock.now()) from exc
            msg = f"the library could not describe Reddit's answer: {exc}"
            raise GatewayError(msg) from exc

    # ------------------------------------------------------------------- listings

    def about(self, name: str) -> RawItem:
        return _data_of(self._get(f"r/{name}/about/"))

    def iter_new_pages(
        self, name: str, *, max_pages: int, after: str | None = None
    ) -> Iterator[Page]:
        return self._pages(f"r/{name}/new", {}, max_pages=max_pages, after=after)

    def search(
        self, query: str, *, sort: str, time_filter: str, max_pages: int = 3
    ) -> Iterator[Page]:
        if time_filter not in SEARCH_WINDOWS:
            msg = f"unknown time_filter {time_filter!r}"
            raise ValueError(msg)
        params: dict[str, str | int] = {"q": query, "sort": sort, "t": time_filter}
        return self._pages("r/all/search/", params, max_pages=max_pages, after=None)

    def _pages(
        self,
        path: str,
        params: dict[str, str | int],
        *,
        max_pages: int,
        after: str | None,
    ) -> Iterator[Page]:
        """Page a listing forward, one request a page, lazily: a page is fetched when asked for."""
        cursor = after
        for _ in range(max_pages):
            query: dict[str, str | int] = {**params, "limit": PAGE_SIZE}
            if cursor is not None:
                query["after"] = cursor
            items, cursor = _page_of(self._get(path, query))
            complete = cursor is None
            yield Page(items=items, after=cursor, complete=complete)
            if complete:
                return

    def info(self, fullnames: Sequence[str]) -> list[RawItem]:
        names = list(dict.fromkeys(fullnames))
        found: list[RawItem] = []
        for start in range(0, len(names), INFO_CHUNK):
            chunk = names[start : start + INFO_CHUNK]
            items, _ = _page_of(self._get("api/info/", {"id": ",".join(chunk)}))
            found.extend(items)
        return found

    def limits(self) -> Limits:
        """Reddit's last-seen view of us. Costs nothing: PRAW reads its own rate limiter."""
        seen = self._reddit.auth.limits
        return Limits(remaining=_as_int(seen.get("remaining")), used=_as_int(seen.get("used")))

    # ----------------------------------------------------------------------- trees

    def fetch_tree(self, post_id: str, *, more_limit: int) -> TreeResult:
        """One base fetch plus one request per expanded ``more`` stub, largest stub first."""
        pid = _bare(post_id)
        link = f"t3_{pid}"
        post, builder = _read_tree(self._get(f"comments/{pid}/"), link=link)
        expansions = self._expand(builder, pid=pid, more_limit=more_limit)
        return TreeResult(
            post=post,
            comments=builder.ordered(),
            more=list(builder.pending),
            requests_used=1 + expansions,
            complete=not builder.pending,
        )

    def _expand(self, builder: _TreeBuilder, *, pid: str, more_limit: int) -> int:
        expansions = 0
        while expansions < more_limit:
            stub = builder.take_next()
            if stub is None:
                break
            expansions += 1
            for thing in self._fetch_more(stub, pid=pid):
                builder.add(thing)
        return expansions

    def _fetch_more(self, stub: MoreStub, *, pid: str) -> list[Any]:
        """Reveal one stub. A ``count == 0`` stub is Reddit's "continue this thread" link: it
        carries no children and is served by re-fetching the thread from that parent, which
        costs the same single request. Both shapes are captured on the probe day (P-11)."""
        if stub.children:
            payload = self._get(
                "api/morechildren/",
                {
                    "link_id": f"t3_{pid}",
                    "children": ",".join(stub.children),
                    "api_type": "json",
                    "limit_children": 0,
                },
            )
            return _more_things(payload)
        payload = self._get(f"comments/{pid}/", {"comment": _bare(stub.parent_fullname)})
        return _listing_children(_tree_listings(payload)[1])


def _as_int(value: object) -> int | None:
    return value if isinstance(value, int) else None


def _tree_listings(payload: Any) -> list[Any]:
    """``/comments`` answers with exactly two listings: the post, then its comments."""
    if not isinstance(payload, list) or len(payload) != 2:
        msg = "a comment fetch answers with a post listing and a comment listing"
        raise GatewayError(msg)
    return payload


def _more_things(payload: Any) -> list[Any]:
    """The flat ``things`` array a ``morechildren`` batch answers with."""
    if isinstance(payload, dict):
        data = payload.get("json", {})
        things = data.get("data", {}).get("things") if isinstance(data, dict) else None
        if isinstance(things, list):
            return things
    msg = "a morechildren batch answers with a things array"
    raise GatewayError(msg)


def _read_tree(payload: Any, *, link: str) -> tuple[RawItem, _TreeBuilder]:
    """Split a ``/comments`` answer into the post and an indexed comment tree."""
    listings = _tree_listings(payload)
    posts, _ = _page_of(listings[0])
    if not posts:
        msg = "the comment fetch returned no post"
        raise GatewayError(msg)
    builder = _TreeBuilder(link)
    for thing in _listing_children(listings[1]):
        builder.add(thing)
    return posts[0], builder


__all__ = [
    "CountingSession",
    "PrawConfig",
    "PrawGateway",
    "build_reddit",
    "translate",
]
