"""AD-02: the PRAW adapter's failure paths, with the exact request count each one costs.

No cassettes and no network: ``responses`` answers at the transport, so ``--block-network``
never sees a socket and every byte in this file is synthetic. The counts are the point.
``requests_made`` is what the run budget spends (the irreversible rule against an unbounded
fetch), and the interesting thing about PRAW is that a single gateway call is rarely a single
round-trip: the first call of a run buys an OAuth token, a 401 buys another one, and prawcore
retries a 5xx or a dropped connection twice before the adapter ever sees it. Each test below
therefore asserts the translated exception *and* the number of round-trips, and the two
numbers -- ``responses``' own tally and the adapter's counter -- are asserted to agree, so a
counter that stopped counting cannot pass.

What this file does **not** cover, and why: the wire shapes themselves. Every payload here is
hand-built from Reddit's documented structure, not captured, so a field Reddit spells
differently would satisfy these tests and fail in production. That is AD-01, AD-03, AD-04 and
PA-01, each of which needs a real capture from the probe day (``docs/runbook/RUNBOOK.md``
§ 9).
"""

from __future__ import annotations

import dataclasses
import time
from collections.abc import Iterator
from datetime import UTC, datetime
from email.utils import format_datetime
from typing import Any

import praw
import prawcore
import pytest
import requests
import responses

from threaddigest.adapters.clock import FakeClock
from threaddigest.adapters.reddit_fake import FakeRedditGateway
from threaddigest.adapters.reddit_praw import (
    MORE_CHUNK,
    CountingSession,
    PrawConfig,
    PrawGateway,
    _half_built_rate_limit,
    _TreeBuilder,
    translate,
)
from threaddigest.core.retry import Outcome, classify
from threaddigest.ports import (
    AuthFailed,
    GatewayError,
    HtmlBlocked,
    Limits,
    RateLimited,
    RedditGateway,
    SubredditForbidden,
    SubredditNotFound,
    SubredditQuarantined,
    SubredditRedirected,
    TransientError,
)
from threaddigest.services import doctor

OAUTH = "https://oauth.reddit.com"
TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
TOKEN_BODY = {
    "access_token": "fake-token",
    "token_type": "bearer",
    "expires_in": 3600,
    "scope": "*",
}

#: Obviously fake, and never a real account: the identifier gate refuses a real author name
#: anywhere under tests, and the credentials here are strings no Reddit app would accept.
CONFIG = PrawConfig(
    client_id="fake-id",
    client_secret="fake-secret",
    user_agent="python:threaddigest-tests:v0 (by /u/synthetic-operator)",
)

NEW_URL = f"{OAUTH}/r/premiere/new"
ABOUT_URL = f"{OAUTH}/r/premiere/about/"
INFO_URL = f"{OAUTH}/api/info/"
SEARCH_URL = f"{OAUTH}/r/all/search/"
TREE_URL = f"{OAUTH}/comments/p1/"
MORE_URL = f"{OAUTH}/api/morechildren/"

INVALID_TOKEN_HEADER = {"www-authenticate": 'Bearer realm="reddit", error="invalid_token"'}

#: The adapter's clock in every test here, so an absolute ``Retry-After`` has a fixed answer.
CLOCK_START = 1_761_000_000


def _http_date(epoch: float) -> str:
    """``epoch`` as the HTTP-date form of ``Retry-After`` (RFC 9110 allows either form)."""
    return format_datetime(datetime.fromtimestamp(epoch, UTC), usegmt=True)


# --------------------------------------------------------------------------- fixtures


@pytest.fixture
def http() -> Iterator[responses.RequestsMock]:
    """Every outbound request answered at the transport; nothing is registered by default."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


@pytest.fixture
def clock() -> FakeClock:
    """The adapter's clock, fixed: an HTTP-date ``Retry-After`` is read against it."""
    return FakeClock(CLOCK_START)


@pytest.fixture
def gateway(clock: FakeClock) -> PrawGateway:
    """A gateway that has issued nothing yet: constructing one costs no round-trip."""
    return PrawGateway(CONFIG, clock=clock)


class _ValueErrorReddit:
    """A client whose ``request`` raises a ``ValueError`` from nowhere near prawcore's 429.

    Injected rather than patched: the point of the case is a ``ValueError`` that carries no
    half-built ``TooManyRequests`` in its traceback, and the cheapest honest way to raise one
    is a client that raises it.
    """

    read_only = True

    def request(self, **_kwargs: Any) -> Any:
        msg = "could not convert string to float: 'nonsense'"
        raise ValueError(msg)


@pytest.fixture
def gateway_over(clock: FakeClock) -> PrawGateway:
    """A gateway over :class:`_ValueErrorReddit`; it opens no socket and costs no round-trip."""
    return PrawGateway(CONFIG, reddit=_ValueErrorReddit(), session=CountingSession(), clock=clock)


@pytest.fixture
def retry_sleeps(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record prawcore's retry waits instead of serving them.

    prawcore's retry strategy sleeps zero-to-two seconds and then two-to-four before its two
    retries. That is real wall time, and this project's rule is that a test never sleeps.
    Recording the waits is also the stronger assertion: the length of this list *is* the
    number of retries prawcore performed, which a wall-clock test could only infer.
    """
    waits: list[float] = []
    monkeypatch.setattr(time, "sleep", waits.append)
    return waits


# ---------------------------------------------------------------------------- helpers


def _token(http: responses.RequestsMock, *, status: int = 200, body: Any = None) -> None:
    http.post(TOKEN_URL, json=TOKEN_BODY if body is None else body, status=status)


def _post(pid: str, **extra: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": pid,
        "name": f"t3_{pid}",
        "title": f"post {pid}",
        "selftext": f"body {pid}",
        "author": "synthetic-author",
        "created_utc": 1_757_700_000.0,
        "stickied": False,
        "subreddit": "premiere",
    }
    data.update(extra)
    return {"kind": "t3", "data": data}


def _listing(children: list[Any], after: str | None = None) -> dict[str, Any]:
    return {"kind": "Listing", "data": {"after": after, "before": None, "children": children}}


def _comment(
    cid: str, parent: str, replies: list[Any] | None = None, **extra: Any
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": cid,
        "name": f"t1_{cid}",
        "parent_id": parent,
        "link_id": "t3_p1",
        "body": f"comment {cid}",
        "author": "synthetic-author",
        "replies": _listing(replies) if replies else "",
    }
    data.update(extra)
    return {"kind": "t1", "data": data}


def _more_node(parent: str, count: int, children: list[str]) -> dict[str, Any]:
    return {
        "kind": "more",
        "data": {
            "count": count,
            "name": f"t1_{children[0]}" if children else f"{parent}_more",
            "id": children[0] if children else "_",
            "parent_id": parent,
            "children": children,
        },
    }


def _tree(comments: list[Any], post: dict[str, Any] | None = None) -> list[Any]:
    return [_listing([post or _post("p1")]), _listing(comments)]


def _things(children: list[Any]) -> dict[str, Any]:
    return {"json": {"errors": [], "data": {"things": children}}}


def _round_trips(http: responses.RequestsMock, gateway: PrawGateway, expected: int) -> None:
    """The transport's tally and the adapter's counter, which must never disagree."""
    assert len(http.calls) == expected
    assert gateway.requests_made == expected


# ------------------------------------------------------------------ construction, shape


def test_the_gateway_satisfies_the_port(gateway: PrawGateway) -> None:
    assert isinstance(gateway, RedditGateway)


def test_construction_issues_no_request_and_opens_no_socket(gateway: PrawGateway) -> None:
    """Nothing is registered and the network is blocked, so a request here would be an error.

    This is the test that keeps ``check_for_updates=False`` honest: PRAW ships that setting
    on and the update checker is installed, so a bare constructor would reach the package
    index before any Reddit call.
    """
    assert gateway.requests_made == 0


def test_an_unset_client_id_is_an_auth_failure_at_construction() -> None:
    """A credential PRAW considers unset, which is what a fresh install without ``.env`` has.

    ``None`` is the shape PRAW tests for, so the config is built that way deliberately; the
    point is that the library's ``MissingRequiredAttributeException`` reaches the caller as
    the port's ``AuthFailed`` and therefore as the CLI's exit 78, not as a traceback out of a
    third-party constructor.
    """
    unset = dataclasses.replace(CONFIG, client_id=None)
    with pytest.raises(AuthFailed):
        PrawGateway(unset)


def test_an_injected_client_without_its_counting_session_is_refused() -> None:
    """The seam cannot be used to smuggle in a client whose round-trips nothing counts."""
    session = CountingSession()
    reddit = praw.Reddit(
        client_id="fake-id",
        client_secret="fake-secret",
        user_agent=CONFIG.user_agent,
        check_for_updates=False,
        check_for_async=False,
        requestor_kwargs={"session": session},
    )
    with pytest.raises(GatewayError):
        PrawGateway(CONFIG, reddit=reddit)


def test_a_client_that_is_not_read_only_is_refused() -> None:
    """Read-only is the whole authorisation model (settled negative N-03), so it is checked."""
    session = CountingSession()
    reddit = praw.Reddit(
        client_id="fake-id",
        client_secret="fake-secret",
        user_agent=CONFIG.user_agent,
        refresh_token="fake-refresh-token",
        check_for_updates=False,
        check_for_async=False,
        requestor_kwargs={"session": session},
    )
    assert reddit.read_only is False
    with pytest.raises(GatewayError):
        PrawGateway(CONFIG, reddit=reddit, session=session)


# ------------------------------------------------------------------ the failure paths


def test_a_401_at_the_token_endpoint_costs_one_request(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """The credentials are rejected before anything is asked of Reddit: one round-trip, no more."""
    _token(http, status=401, body={"message": "Unauthorized", "error": 401})

    with pytest.raises(AuthFailed):
        gateway.about("premiere")

    _round_trips(http, gateway, 1)


def test_an_invalid_token_midrun_buys_a_fresh_token_for_every_retry(
    http: responses.RequestsMock, gateway: PrawGateway, retry_sleeps: list[float]
) -> None:
    """prawcore clears the token on a 401 and retries twice, refreshing each time.

    Six round-trips for one ``about()`` -- three tokens and three listings -- which is the
    reason the counter lives in the session and not in the gateway's own methods.
    """
    _token(http)
    http.get(ABOUT_URL, status=401, json={"message": "Unauthorized"}, headers=INVALID_TOKEN_HEADER)

    with pytest.raises(AuthFailed):
        gateway.about("premiere")

    assert len(retry_sleeps) == 2
    _round_trips(http, gateway, 6)


def test_a_private_subreddit_is_forbidden(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    body = {"message": "Forbidden", "error": 403, "reason": "private"}
    http.get(ABOUT_URL, status=403, json=body)

    with pytest.raises(SubredditForbidden):
        gateway.about("premiere")

    _round_trips(http, gateway, 2)


def test_an_html_403_is_an_edge_block_and_not_a_private_subreddit(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """A ``text/html`` 403 is the edge refusing us, which must abort the run, not skip a source."""
    _token(http)
    http.get(
        ABOUT_URL,
        status=403,
        body="<html><body>Blocked</body></html>",
        content_type="text/html; charset=utf-8",
    )

    with pytest.raises(HtmlBlocked):
        gateway.about("premiere")

    _round_trips(http, gateway, 2)


def test_a_quarantine_body_is_named_as_such(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """Provisional until probe P-07 captures a real one; this is the documented shape."""
    _token(http)
    http.get(
        ABOUT_URL,
        status=403,
        json={
            "reason": "quarantined",
            "quarantine_message": "This community is quarantined.",
            "message": "Forbidden",
            "error": 403,
        },
    )

    with pytest.raises(SubredditQuarantined):
        gateway.about("premiere")

    _round_trips(http, gateway, 2)


def test_a_404_is_a_missing_subreddit(http: responses.RequestsMock, gateway: PrawGateway) -> None:
    _token(http)
    http.get(ABOUT_URL, status=404, json={"message": "Not Found", "error": 404})

    with pytest.raises(SubredditNotFound):
        gateway.about("premiere")

    _round_trips(http, gateway, 2)


def test_a_302_carries_the_path_it_redirected_to(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """Reddit answers a name that does not exist with a redirect to its search page (P-14)."""
    _token(http)
    http.get(
        ABOUT_URL,
        status=302,
        body="",
        headers={"Location": "https://www.reddit.com/subreddits/search.json?q=premiere"},
    )

    with pytest.raises(SubredditRedirected) as caught:
        gateway.about("premiere")

    assert caught.value.path == "/subreddits/search"
    _round_trips(http, gateway, 2)


def test_a_429_carries_its_retry_after_as_a_number(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """prawcore hands the header over as a string; the port promises seconds as a number."""
    _token(http)
    http.get(
        ABOUT_URL,
        status=429,
        json={"message": "Too Many Requests", "error": 429},
        headers={"Retry-After": "120"},
    )

    with pytest.raises(RateLimited) as caught:
        gateway.about("premiere")

    assert caught.value.retry_after == 120.0
    _round_trips(http, gateway, 2)


def test_a_429_without_the_header_has_no_retry_after(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(ABOUT_URL, status=429, json={"message": "Too Many Requests", "error": 429})

    with pytest.raises(RateLimited) as caught:
        gateway.about("premiere")

    assert caught.value.retry_after is None
    _round_trips(http, gateway, 2)


def test_a_429_whose_retry_after_is_an_http_date_is_rate_limited_with_the_wait_it_names(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """``Retry-After`` is legally either seconds or an HTTP date (RFC 9110); Reddit may send both.

    The date form never reaches the translation table: prawcore formats the header with
    ``float()`` while *building* its own ``TooManyRequests``, so the exception dies in its own
    constructor and a ``ValueError`` comes out of ``Reddit.request`` instead. Until 2026-09-17
    the adapter reported that as a bare ``GatewayError``, which ``core.retry.classify`` calls
    ``fatal``: the source was stamped errored and the run carried on requesting while Reddit
    was rate-limiting it (panel finding C-1, KI-041). The adapter now recovers the half-built
    exception from the raising frame and reads the date against its own clock, so the run
    backs off for exactly the wait Reddit named.
    """
    _token(http)
    http.get(
        ABOUT_URL,
        status=429,
        json={"message": "Too Many Requests"},
        headers={"Retry-After": _http_date(CLOCK_START + 120)},
    )

    with pytest.raises(RateLimited) as caught:
        gateway.about("premiere")

    assert caught.value.retry_after == 120.0
    assert classify(caught.value) is Outcome.RATE_LIMITED
    _round_trips(http, gateway, 2)


def test_a_retry_after_date_that_has_already_passed_waits_the_ladders_default(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """A stale or skewed date is still a 429: rate limited, with no wait of its own.

    ``retry_after is None`` is what the port spells "no usable value"; the caller's
    ``core.retry.plan_rate_limit_wait`` then falls back to its own sixty-second default. The
    one outcome this must never be is fatal.
    """
    _token(http)
    http.get(
        ABOUT_URL,
        status=429,
        json={"message": "Too Many Requests"},
        headers={"Retry-After": _http_date(CLOCK_START - 60)},
    )

    with pytest.raises(RateLimited) as caught:
        gateway.about("premiere")

    assert caught.value.retry_after is None
    assert classify(caught.value) is Outcome.RATE_LIMITED
    _round_trips(http, gateway, 2)


def test_a_retry_after_that_is_neither_seconds_nor_a_date_is_still_a_rate_limit(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """The third shape: a header the adapter cannot read at all. Reddit still refused us."""
    _token(http)
    http.get(
        ABOUT_URL,
        status=429,
        json={"message": "Too Many Requests"},
        headers={"Retry-After": "soon"},
    )

    with pytest.raises(RateLimited) as caught:
        gateway.about("premiere")

    assert caught.value.retry_after is None
    _round_trips(http, gateway, 2)


def test_a_value_error_that_is_not_the_rate_limit_constructor_is_still_a_gateway_error(
    gateway_over: PrawGateway,
) -> None:
    """The arm C-1 narrowed, kept honest: only the 429 frame becomes ``RateLimited``.

    Anything else the library raises as a ``ValueError`` is still an answer the run could not
    read, and it reaches the CLI as a ``GatewayError`` rather than as a traceback.
    """
    with pytest.raises(GatewayError, match="could not describe"):
        gateway_over.about("premiere")


def test_a_value_error_from_another_constructor_in_that_file_is_not_mistaken_for_a_429() -> None:
    """The narrowing's own control: the frame is identified by what it was building, too.

    ``prawcore/exceptions.py`` holds exactly one constructor that can raise a ``ValueError``
    today. If it grows a second, the handler must not hand that exception to the 429
    translation, which would read a ``retry_after`` the object does not carry. The library
    offers no such constructor to test against, so the frame is faked the only way that
    produces a real one: compiling a function under that filename.
    """
    namespace: dict[str, Any] = {}
    source = "def __init__(self):\n    raise ValueError('not a rate limit at all')\n"
    exec(compile(source, "/somewhere/prawcore/exceptions.py", "exec"), namespace)

    with pytest.raises(ValueError, match="not a rate limit") as caught:
        namespace["__init__"](object())

    assert _half_built_rate_limit(caught.value) is None


def test_a_retry_after_is_read_the_same_way_whichever_form_it_arrives_in(
    clock: FakeClock,
) -> None:
    """The adapter's own half of the question, asserted on the translation directly.

    prawcore hands ``retry_after`` over as the raw header string, so reading it belongs to the
    adapter: seconds as a number, an HTTP date as the wait from the adapter's clock to that
    instant, and anything else as ``None`` -- never an exception, because the caller's fallback
    is its own wait ladder.
    """
    response = requests.Response()
    response.status_code = 429
    response.headers["Retry-After"] = "600"
    response._content = b""
    exc = prawcore.exceptions.TooManyRequests(response)

    assert _retry_after_of(translate(exc, now=clock.now())) == 600.0

    exc.retry_after = _http_date(CLOCK_START + 45)
    assert _retry_after_of(translate(exc, now=clock.now())) == 45.0

    exc.retry_after = "half past four"
    assert _retry_after_of(translate(exc, now=clock.now())) is None


def _retry_after_of(translated: GatewayError) -> float | None:
    assert isinstance(translated, RateLimited)
    return translated.retry_after


def test_a_451_is_that_source_forbidden_and_not_a_fatal_run_error(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """451 withholds one community, so the run skips the source and carries on (see DECISIONS)."""
    _token(http)
    http.get(ABOUT_URL, status=451, json={"message": "Unavailable For Legal Reasons"})

    with pytest.raises(SubredditForbidden):
        gateway.about("premiere")

    _round_trips(http, gateway, 2)


def test_a_403_whose_body_is_not_json_is_an_ordinary_forbidden(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """The quarantine predicate reads the body, so a body it cannot read must not crash it."""
    _token(http)
    http.get(ABOUT_URL, status=403, body="forbidden", content_type="application/json")

    with pytest.raises(SubredditForbidden):
        gateway.about("premiere")


def test_a_403_whose_body_is_not_an_object_is_an_ordinary_forbidden(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(ABOUT_URL, status=403, json=["forbidden"])

    with pytest.raises(SubredditForbidden):
        gateway.about("premiere")


def test_a_400_is_a_programming_error_named_and_never_swallowed(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """A malformed request is ours, not Reddit's: it must not look like a skippable source."""
    _token(http)
    http.get(ABOUT_URL, status=400, json={"error": 400, "message": "Bad Request"})

    with pytest.raises(GatewayError) as caught:
        gateway.about("premiere")

    assert not isinstance(caught.value, SubredditForbidden | TransientError | RateLimited)
    _round_trips(http, gateway, 2)


def test_a_401_the_library_cannot_name_is_still_an_auth_failure(
    http: responses.RequestsMock, gateway: PrawGateway, retry_sleeps: list[float]
) -> None:
    """prawcore looks a 401 up in a three-entry table and raises a bare ``KeyError`` on a miss.

    A 401 without a ``www-authenticate`` header hits that miss. Left alone it would reach the
    operator as a traceback out of a third-party library instead of exit 78, so the adapter
    catches that one named exception at the same site as the rest.
    """
    _token(http)
    http.get(ABOUT_URL, status=401, json={"message": "Unauthorized"})

    with pytest.raises(AuthFailed):
        gateway.about("premiere")

    assert len(retry_sleeps) == 2
    _round_trips(http, gateway, 6)


def test_a_half_present_rate_limit_header_set_is_not_reported_as_bad_credentials(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """KI-030: the ``KeyError`` handler was written for one library path and caught two.

    prawcore's rate limiter (``prawcore/rate_limit.py``) decides whether a response carries
    rate-limit headers by testing for ``x-ratelimit-remaining`` alone, then reads
    ``x-ratelimit-used`` and ``x-ratelimit-reset`` by subscript. A response with the first
    header and not the third -- a proxy that rewrites headers, an edge that serves a cached
    copy, a future change at Reddit -- therefore raises a bare ``KeyError`` from inside the
    library, on an ordinary 200 that carried the data we asked for.

    The adapter mapped every ``KeyError`` out of ``request`` to ``AuthFailed``, so this one
    reached the operator as "credentials rejected", and ``doctor``'s auth-ping row would send
    them to ``/setup`` to fix credentials that are working. It is a malformed answer, not a
    refused one, and it says so.
    """
    _token(http)
    http.get(
        ABOUT_URL,
        json={"kind": "t5", "data": {"display_name": "premiere"}},
        headers={"x-ratelimit-remaining": "993.0", "x-ratelimit-used": "7"},
    )

    with pytest.raises(GatewayError) as caught:
        gateway.about("premiere")

    assert not isinstance(caught.value, AuthFailed)
    assert "rate-limit" in str(caught.value)
    assert "x-ratelimit-reset" in str(caught.value)
    _round_trips(http, gateway, 2)


def test_a_401_the_library_cannot_name_is_still_an_auth_failure_after_the_narrowing(
    http: responses.RequestsMock, gateway: PrawGateway, retry_sleeps: list[float]
) -> None:
    """KI-030's other direction: narrowing the handler must not lose the case it was for.

    The OAuth-table miss (``prawcore/util.py::authorization_error_class``) is still an
    ``AuthFailed``, and it is identified by the frame it was raised in rather than by being
    the only ``KeyError`` the library can produce.
    """
    _token(http)
    http.get(ABOUT_URL, status=401, json={"message": "Unauthorized"})

    with pytest.raises(AuthFailed) as caught:
        gateway.about("premiere")

    assert "unrecognised OAuth error" in str(caught.value)
    assert len(retry_sleeps) == 2
    _round_trips(http, gateway, 6)


def test_a_key_error_from_anywhere_else_in_the_library_is_named_and_never_swallowed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The third shape: neither the OAuth table nor the rate-limit headers.

    Nothing from the library may reach a service untranslated, named row or not, so a
    ``KeyError`` from a path this adapter has not met is still a plain ``GatewayError`` -- not
    an ``AuthFailed``, and not a traceback. Driven through the injection seam, so no request
    is made and no socket is opened.
    """
    session = CountingSession()
    reddit = praw.Reddit(
        client_id="fake-id",
        client_secret="fake-secret",
        user_agent=CONFIG.user_agent,
        check_for_updates=False,
        check_for_async=False,
        requestor_kwargs={"session": session},
    )
    gateway = PrawGateway(CONFIG, reddit=reddit, session=session)

    def _raise(**kwargs: Any) -> Any:
        raise KeyError("data")

    monkeypatch.setattr(reddit, "request", _raise)

    with pytest.raises(GatewayError) as caught:
        gateway.about("premiere")

    assert not isinstance(caught.value, AuthFailed)
    assert "data" in str(caught.value)


def test_a_503_is_transient_only_after_prawcores_two_retries(
    http: responses.RequestsMock, gateway: PrawGateway, retry_sleeps: list[float]
) -> None:
    """One gateway call, four round-trips: the token and three attempts at the listing."""
    _token(http)
    http.get(ABOUT_URL, status=503, body="")

    with pytest.raises(TransientError):
        gateway.about("premiere")

    assert len(retry_sleeps) == 2
    _round_trips(http, gateway, 4)


def test_a_dropped_connection_is_transient_and_still_counted(
    http: responses.RequestsMock, gateway: PrawGateway, retry_sleeps: list[float]
) -> None:
    """A request that never reached Reddit is still a request the budget spent."""
    _token(http)
    http.get(ABOUT_URL, body=requests.exceptions.ConnectionError("no route to host"))

    with pytest.raises(TransientError):
        gateway.about("premiere")

    assert len(retry_sleeps) == 2
    assert gateway.requests_made == 4


def test_an_unexpected_library_exception_still_becomes_a_gateway_error() -> None:
    """Nothing from the library may reach a service untranslated, named row or not."""
    assert type(translate(prawcore.exceptions.InvalidInvocation("bad call"))) is GatewayError
    assert type(translate(praw.exceptions.ClientException("odd"))) is GatewayError
    assert type(translate(ValueError("not a library exception at all"))) is GatewayError


def test_a_missing_required_attribute_is_an_auth_failure() -> None:
    """The row that keeps a missing credential out of a traceback (the table's last line)."""
    exc = praw.exceptions.MissingRequiredAttributeException("client_secret missing")
    assert isinstance(translate(exc), AuthFailed)


def test_a_malformed_envelope_is_a_gateway_error(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """A wire shape the port cannot read is an error, never a silently empty result."""
    _token(http)
    http.get(ABOUT_URL, json=["not", "an", "envelope"])

    with pytest.raises(GatewayError):
        gateway.about("premiere")


# ------------------------------------------------------------------- the happy paths


def test_about_returns_the_subreddit_in_wire_shape(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(ABOUT_URL, json={"kind": "t5", "data": {"display_name": "premiere", "name": "t5_1"}})

    assert gateway.about("premiere") == {"display_name": "premiere", "name": "t5_1"}
    _round_trips(http, gateway, 2)


def test_limits_reads_the_last_response_and_costs_nothing(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(
        ABOUT_URL,
        json={"kind": "t5", "data": {"display_name": "premiere"}},
        headers={
            "x-ratelimit-remaining": "993.0",
            "x-ratelimit-used": "7",
            "x-ratelimit-reset": "300",
        },
    )

    assert gateway.limits().remaining is None  # nothing has been seen yet
    gateway.about("premiere")
    before = gateway.requests_made

    seen = gateway.limits()

    assert (seen.remaining, seen.used) == (993, 7)
    assert gateway.requests_made == before


def test_the_auth_ping_costs_exactly_two_http_calls(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """The plan's "exactly two HTTP calls (token + about)" claim, proven offline.

    This is ``services.doctor.check_auth_ping`` itself, driven against the real adapter, not
    a hand-rolled equivalent: the claim the plan and the runbook make is about what
    ``doctor --network`` costs, so the thing under test has to be the function ``doctor``
    calls. The two round-trips are the OAuth token from ``www.reddit.com`` and the subreddit
    read from ``oauth.reddit.com`` -- two different hosts, registered separately here, so a
    third request of any kind to either of them shows up as a third call.

    ``limits()`` adds nothing, which is the half of the claim a count alone would not
    separate: the count is taken before and after the whole check, and the check reads
    ``limits()`` after ``about``. AD-01 owns the cassette version of this (probe P-15); a
    ``responses`` test is not a cassette test, and it cannot prove the wire *shapes* -- the
    payload below is hand-built. What it does prove is the cost, which is what the
    irreversible budget rule is about.
    """
    _token(http)
    http.get(
        ABOUT_URL,
        json={"kind": "t5", "data": {"display_name": "premiere", "name": "t5_1"}},
        headers={
            "x-ratelimit-remaining": "993.0",
            "x-ratelimit-used": "7",
            "x-ratelimit-reset": "300",
        },
    )

    check = doctor.check_auth_ping(gateway, subreddit="premiere")

    assert check.ok is True, check.detail
    assert len(http.calls) == 2, [call.request.url for call in http.calls]
    assert gateway.requests_made == 2
    # PRAW appends ``?raw_json=1`` to every data request; the two ORIGINS and paths are
    # the claim, and they are two different hosts (token vs. oauth).
    assert [call.request.url.split("?")[0] for call in http.calls] == [TOKEN_URL, ABOUT_URL]
    # The free read really is free: asking again after the check moves neither counter.
    assert gateway.limits() == Limits(remaining=993, used=7)
    assert len(http.calls) == 2
    assert gateway.requests_made == 2


def test_paging_is_lazy_until_the_first_page_is_asked_for(gateway: PrawGateway) -> None:
    """A listing that is never consumed costs nothing, which is what makes a resume cheap."""
    gateway.iter_new_pages("premiere", max_pages=3)

    assert gateway.requests_made == 0


def test_new_pages_follow_the_cursor_and_stop_when_the_listing_runs_out(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(NEW_URL, json=_listing([_post("a"), _post("b")], after="t3_b"))
    http.get(NEW_URL, json=_listing([_post("c")]))

    pages = list(gateway.iter_new_pages("premiere", max_pages=5))

    assert [page.after for page in pages] == ["t3_b", None]
    assert [page.complete for page in pages] == [False, True]
    assert [item["id"] for page in pages for item in page.items] == ["a", "b", "c"]
    _round_trips(http, gateway, 3)


def test_new_pages_stop_at_max_pages_with_a_resumable_cursor(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(NEW_URL, json=_listing([_post("a")], after="t3_a"))

    pages = list(gateway.iter_new_pages("premiere", max_pages=1, after="t3_z"))

    assert pages[-1].after == "t3_a"
    assert pages[-1].complete is False
    assert "after=t3_z" in http.calls[1].request.url
    _round_trips(http, gateway, 2)


def test_info_asks_for_a_hundred_fullnames_per_request(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(INFO_URL, json=_listing([_post(f"x{i}") for i in range(100)]))
    http.get(INFO_URL, json=_listing([_post("x100")]))

    found = gateway.info([f"t3_x{i}" for i in range(101)])

    assert len(found) == 101
    _round_trips(http, gateway, 3)


def test_info_over_no_fullnames_asks_nothing(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    assert gateway.info([]) == []
    _round_trips(http, gateway, 0)


def test_search_pages_and_refuses_a_window_reddit_does_not_have(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(SEARCH_URL, json=_listing([_post("a")]))

    pages = list(gateway.search("premiere pro", sort="new", time_filter="week"))

    assert [item["id"] for page in pages for item in page.items] == ["a"]
    with pytest.raises(ValueError, match="time_filter"):
        gateway.search("x", sort="new", time_filter="fortnight")


# ------------------------------------------------------------------------ the tree


def test_fetch_tree_flattens_depth_first_with_depths_and_reports_its_leftovers(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """Parents before children, depth counted from the walk rather than trusted from the wire."""
    _token(http)
    http.get(
        TREE_URL,
        json=_tree(
            [
                _comment("c1", "t3_p1", replies=[_comment("c2", "t1_c1")]),
                _comment("c3", "t3_p1"),
                _more_node("t3_p1", 4, ["c4", "c5"]),
            ]
        ),
    )

    result = gateway.fetch_tree("t3_p1", more_limit=0)

    assert [(c["id"], c["depth"]) for c in result.comments] == [("c1", 0), ("c2", 1), ("c3", 0)]
    assert [(stub.parent_fullname, stub.count) for stub in result.more] == [("t3_p1", 4)]
    assert result.post["id"] == "p1"
    assert result.requests_used == 1
    assert result.complete is False
    assert "replies" not in result.comments[0]


def test_fetch_tree_ignores_a_node_that_is_neither_a_comment_nor_a_stub(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """Reddit puts the post's own kind and the occasional oddity in a tree listing.

    Skipping what the port has no place for is the honest reading: a comment tree promises
    comments and ``more`` stubs, and anything else belongs to a caller that asked for it.
    """
    _token(http)
    http.get(TREE_URL, json=_tree(["not a node at all", _post("p1"), _comment("c1", "t3_p1")]))

    result = gateway.fetch_tree("p1", more_limit=0)

    assert [c["id"] for c in result.comments] == ["c1"]
    assert result.complete is True


def test_fetch_tree_expands_the_largest_stub_first_one_request_each(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(
        TREE_URL,
        json=_tree(
            [
                _comment("c1", "t3_p1"),
                _more_node("t1_c1", 1, ["small"]),
                _more_node("t3_p1", 9, ["big"]),
            ]
        ),
    )
    http.get(MORE_URL, json=_things([_comment("big", "t3_p1")]))

    result = gateway.fetch_tree("p1", more_limit=1)

    assert [c["id"] for c in result.comments] == ["c1", "big"]
    assert [stub.count for stub in result.more] == [1]
    assert result.requests_used == 2
    assert result.complete is False
    assert "children=big" in http.calls[2].request.url


def test_fetch_tree_is_complete_only_when_no_stub_is_left(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(TREE_URL, json=_tree([_comment("c1", "t3_p1")]))

    result = gateway.fetch_tree("p1", more_limit=3)

    assert result.complete is True
    assert result.more == []
    assert result.requests_used == 1


def test_a_stub_over_a_hundred_children_is_split_across_requests(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """``morechildren`` reveals at most a hundred comments per request (KI-023)."""
    children = [f"c{i}" for i in range(MORE_CHUNK + 5)]
    _token(http)
    http.get(TREE_URL, json=_tree([_more_node("t3_p1", len(children), children)]))
    http.get(MORE_URL, json=_things([_comment(cid, "t3_p1") for cid in children[:MORE_CHUNK]]))

    result = gateway.fetch_tree("p1", more_limit=1)

    assert len(result.comments) == MORE_CHUNK
    assert [stub.count for stub in result.more] == [5]
    assert result.requests_used == 2


def test_a_comment_an_expansion_returns_again_is_indexed_once(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """``morechildren`` is asked with ``limit_children=0``, so overlap is the expected case.

    Panel finding C-5 (KI-042): the builder indexed by ``parent_id`` with no de-duplication,
    so a comment the base fetch had already delivered was delivered a second time. The port
    promises *every comment in depth-first order*, which the collector reads as one row per
    comment: at M1b ``comments_captured`` would over-count, and the planned invariant
    "comments_captured equals the actual count per fetched post" would fire against the
    collector for the adapter's fault.
    """
    _token(http)
    http.get(TREE_URL, json=_tree([_comment("c1", "t3_p1"), _more_node("t3_p1", 1, ["c2"])]))
    http.get(MORE_URL, json=_things([_comment("c2", "t3_p1"), _comment("c1", "t3_p1")]))

    result = gateway.fetch_tree("p1", more_limit=1)

    assert [c["id"] for c in result.comments] == ["c1", "c2"]
    assert result.complete is True
    _round_trips(http, gateway, 3)


def test_a_parent_an_expansion_returns_again_does_not_re_emit_its_subtree(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """The same defect at its worst: a repeated *parent* re-emitted everything under it.

    The later copy's replies are still walked -- de-duplication is per item, and a second copy
    may carry a reply the first did not -- so the count is the number of distinct comments,
    never the number of times Reddit mentioned one.
    """
    _token(http)
    http.get(
        TREE_URL,
        json=_tree(
            [
                _comment("c1", "t3_p1", replies=[_comment("c11", "t1_c1")]),
                _more_node("t3_p1", 1, ["c2"]),
            ]
        ),
    )
    http.get(
        MORE_URL,
        json=_things(
            [
                _comment("c2", "t3_p1"),
                _comment("c1", "t3_p1", replies=[_comment("c11", "t1_c1")]),
            ]
        ),
    )

    result = gateway.fetch_tree("p1", more_limit=1)

    assert [(c["id"], c["depth"]) for c in result.comments] == [("c1", 0), ("c11", 1), ("c2", 0)]


def test_a_reply_only_the_second_copy_of_a_parent_carries_is_still_indexed(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """The reason the duplicate's replies are walked rather than skipped with it."""
    _token(http)
    http.get(TREE_URL, json=_tree([_comment("c1", "t3_p1"), _more_node("t3_p1", 1, ["c2"])]))
    http.get(
        MORE_URL,
        json=_things(
            [_comment("c2", "t3_p1"), _comment("c1", "t3_p1", replies=[_comment("late", "t1_c1")])]
        ),
    )

    result = gateway.fetch_tree("p1", more_limit=1)

    assert [c["id"] for c in result.comments] == ["c1", "late", "c2"]


def test_splitting_a_stub_divides_its_count_rather_than_relabelling_it() -> None:
    """``MoreStub.count`` is Reddit's count of hidden comments, not the size of a chunk.

    Panel finding C-6 (KI-043): a stub whose wire ``count`` was 400 across 150 child ids was
    split into stubs carrying 100 and 50, so the adapter quietly replaced Reddit's number with
    its own id count and the tree lost 250 hidden comments on the way. The UI renders this as
    "N replies not captured", and the fake computes the true instance count, so the two
    disagreed by construction and a contract test written against the fake asserted a number
    the adapter could not produce.

    Asserted on the builder rather than through ``fetch_tree`` because only one of the two
    parts survives a fetch: the head is consumed by the expansion it was cut for.
    """
    children = [f"c{i}" for i in range(MORE_CHUNK + 50)]
    builder = _TreeBuilder("t3_p1")
    builder.add(_more_node("t3_p1", 400, children))

    head = builder.take_next()

    assert head is not None
    assert len(head.children) == MORE_CHUNK
    assert head.count == MORE_CHUNK
    assert [stub.count for stub in builder.pending] == [300]
    assert head.count + sum(stub.count for stub in builder.pending) == 400


def test_a_stub_whose_count_undercounts_its_own_children_never_goes_negative() -> None:
    """The one shape the rule cannot honour exactly, and what it does instead.

    "The parts sum to the whole" needs a whole at least as large as the child list, which
    Reddit's own data always is. A malformed stub claiming fewer hidden comments than it
    carries ids gets the floor instead: neither part ever claims fewer than it holds.
    """
    children = [f"c{i}" for i in range(MORE_CHUNK + 50)]
    builder = _TreeBuilder("t3_p1")
    builder.add(_more_node("t3_p1", 10, children))

    head = builder.take_next()

    assert head is not None
    assert head.count == MORE_CHUNK
    assert [stub.count for stub in builder.pending] == [50]


def test_the_remainder_of_a_split_stub_is_what_the_reader_is_told_is_missing(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """The same rule where it is visible: the leftover stub is the one that reaches the UI."""
    children = [f"c{i}" for i in range(MORE_CHUNK + 50)]
    _token(http)
    http.get(TREE_URL, json=_tree([_more_node("t3_p1", 400, children)]))
    http.get(MORE_URL, json=_things([_comment(cid, "t3_p1") for cid in children[:MORE_CHUNK]]))

    result = gateway.fetch_tree("p1", more_limit=1)

    assert [stub.count for stub in result.more] == [300]
    assert len(result.comments) == MORE_CHUNK
    assert result.requests_used == 2


def test_both_gateways_agree_on_the_remainder_of_a_split_stub(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """The contract row C-6 asks for, on the shape where the two can agree exactly.

    The fake knows each hidden comment's subtree and the adapter knows only ids, so the two
    can only produce the same number where every hidden comment is a leaf -- which is exactly
    the shape that caught the defect, because there the wire ``count`` equals the id count and
    the remainder is the whole minus the chunk on both sides.
    """
    children = [f"c{i}" for i in range(MORE_CHUNK + 50)]
    _token(http)
    http.get(TREE_URL, json=_tree([_more_node("t3_p1", len(children), children)]))
    http.get(MORE_URL, json=_things([_comment(cid, "t3_p1") for cid in children[:MORE_CHUNK]]))
    real = gateway.fetch_tree("p1", more_limit=1)

    fake = FakeRedditGateway()
    post = fake.add_post("premiere", title="one flat thread", created_utc=1_757_800_000.0)
    hidden = [
        fake.add_comment(post, body=f"c{i}", author="u", created_utc=1_757_800_000.0 + i)
        for i in range(len(children))
    ]
    fake.add_more(post, None, len(hidden), hidden)
    simulated = fake.fetch_tree(post, more_limit=1)

    assert [stub.count for stub in real.more] == [stub.count for stub in simulated.more] == [50]
    assert len(real.comments) == len(simulated.comments) == MORE_CHUNK
    assert real.requests_used == simulated.requests_used == 2


def test_a_continue_this_thread_stub_is_expanded_by_refetching_the_thread(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    """A ``count == 0`` stub carries no children; Reddit serves it from the parent (P-11)."""
    _token(http)
    http.get(TREE_URL, json=_tree([_comment("c1", "t3_p1"), _more_node("t1_c1", 0, [])]))
    http.get(TREE_URL, json=_tree([_comment("deep", "t1_c1")]))

    result = gateway.fetch_tree("p1", more_limit=1)

    assert [(c["id"], c["depth"]) for c in result.comments] == [("c1", 0), ("deep", 1)]
    assert result.requests_used == 2
    assert "comment=c1" in http.calls[2].request.url


def test_a_malformed_tree_answer_is_a_gateway_error(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(TREE_URL, json={"kind": "Listing", "data": {"children": []}})

    with pytest.raises(GatewayError):
        gateway.fetch_tree("p1", more_limit=0)


def test_a_malformed_morechildren_answer_is_a_gateway_error(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(TREE_URL, json=_tree([_more_node("t3_p1", 1, ["c9"])]))
    http.get(MORE_URL, json={"json": {"errors": []}})

    with pytest.raises(GatewayError):
        gateway.fetch_tree("p1", more_limit=1)


def test_a_tree_answer_without_a_post_is_a_gateway_error(
    http: responses.RequestsMock, gateway: PrawGateway
) -> None:
    _token(http)
    http.get(TREE_URL, json=[_listing([]), _listing([])])

    with pytest.raises(GatewayError):
        gateway.fetch_tree("p1", more_limit=0)


# --------------------------------------------------------------- the cassette filters


def test_the_cassette_filters_are_the_ones_the_probe_day_needs(
    vcr_config: dict[str, Any],
) -> None:
    """A filter nobody has seen working is a hypothesis (runbook § 9 precondition 4)."""
    assert vcr_config["record_mode"] == "none"
    assert vcr_config["cassette_library_dir"].endswith("tests/adapters/cassettes")
    assert {"authorization", "Authorization"} <= set(vcr_config["filter_headers"])
    assert {"set-cookie", "Set-Cookie"} <= set(vcr_config["filter_headers"])
    assert set(vcr_config["filter_post_data_parameters"]) == {"code", "password", "refresh_token"}


def test_the_response_filter_blanks_the_token_and_the_cookie(
    vcr_config: dict[str, Any],
) -> None:
    recorded = {
        "status": {"code": 200, "message": "OK"},
        "headers": {"Set-Cookie": ["session=abc; Path=/"], "Content-Type": ["application/json"]},
        "body": {"string": b'{"access_token": "a-real-looking-token", "expires_in": 3600}'},
    }

    scrubbed = vcr_config["before_record_response"](recorded)

    assert b"a-real-looking-token" not in scrubbed["body"]["string"]
    assert scrubbed["headers"]["Set-Cookie"] == ["FILTERED"]
    assert scrubbed["headers"]["Content-Type"] == ["application/json"]
    assert b"a-real-looking-token" in recorded["body"]["string"]  # the input is not mutated


def test_the_response_filter_leaves_a_body_it_cannot_read_alone(
    vcr_config: dict[str, Any],
) -> None:
    recorded = {"headers": {}, "body": {"string": b"<html>not json</html>"}}

    scrubbed = vcr_config["before_record_response"](recorded)

    assert scrubbed["body"]["string"] == b"<html>not json</html>"
