"""The perimeter a read-only page still needs: the ``Host`` check and the response headers.

Two pure-ASGI middlewares, both on **every** request, reads included.

**Host check (UI D7, spec row UI-22).** DNS rebinding is a *read* attack. A page on another
origin points a name it controls at ``127.0.0.1``, waits for the browser's DNS cache to
flip, and then reads this application from script, because as far as the browser is
concerned both fetches went to the same origin. Nothing about the request looks unusual
except its ``Host`` header, which still carries the attacker's name -- so the header is
checked on every request rather than only on the state-changing ones, which is exactly the
finding the UI panel raised against the first design (§ D finding 7). A request whose host
is not one this server answers to is refused with 421 (Misdirected Request), the code
``docs/reference/reviews/2026-09-13-panel-ui.md`` § A row UI-22 names, and the refusal says
nothing back about the host it was given: reflecting an attacker's string into a response
buys nothing and costs an escaping question.

Any port passes. The attack is on the *name*: a browser that has been talked into resolving
``evil.example`` to the loopback address sends ``Host: evil.example``, and a port cannot
launder that. Refusing ``127.0.0.1:9999`` would only break an operator who put the server on
another port.

**Response headers (spec row UI-05, half of it).** ``Content-Security-Policy`` is the cheap
defence in depth behind the markdown surface: ``default-src 'self'`` means no external
script, style, image or connection, so a string that survives sanitizing still has nowhere to
send what it reads. ``default-src`` is only the *fetch* fallback, though, and four directives
do not fall back to it at all, so they are stated as well (KI-050, the 2026-09-17 code panel's
seat B finding B7): ``frame-ancestors 'none'``, without which the pages were frameable by any
origin; ``base-uri 'none'``; ``form-action 'self'``; and ``object-src 'none'``. The whole
policy is :data:`CONTENT_SECURITY_POLICY`, which says why each is there.
``X-Content-Type-Options: nosniff`` stops a browser from deciding that a stored body is
really HTML, and ``Referrer-Policy: no-referrer`` keeps local URLs out of the ``Referer`` of
every deep link into reddit.com. The other half of UI-05 -- the scan that every ``|safe``
operand is a sanitized ``*_html`` column -- arrives with the first template that renders
stored content; nothing here renders any.

**What is deliberately NOT here yet.** The same-origin check on state-changing requests
(``Sec-Fetch-Site`` with the ``Origin``/``Referer`` fallback on plain HTTP, UI-21) and basic
auth behind ``THREADDIGEST_UI_PASSWORD`` (UI-24) land with the first POST. A CSRF check
written now would guard nothing, and could not be tested against a real mutation, which is
the kind of mechanism that rots. So this module is **not** the whole perimeter, and the
docstring used to say it was: the loopback bind, the Host check and these headers are what
holds while every route is a read (proven, not assumed: seat B drove hand-made scopes and
found no state-changing route). The missing pieces are named above because M2's "Run now" and
"Cancel" arrive inside this same header, and that is when the sentence has to change again.
"""

from __future__ import annotations

from typing import Final

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = [
    "CONTENT_SECURITY_POLICY",
    "HOST_REFUSED_MESSAGE",
    "HOST_REFUSED_STATUS",
    "LOOPBACK_HOSTS",
    "SECURITY_HEADERS",
    "HostCheck",
    "SecurityHeaders",
    "hostname_of",
]

#: The names this server answers to. ``serve`` binds ``127.0.0.1``, so the bind address is
#: already in the set; the LAN address D-20 allows at M4 is added here, with the settings key
#: that carries it, rather than by a second mechanism.
LOOPBACK_HOSTS: Final = frozenset({"127.0.0.1", "localhost", "::1", "[::1]"})

#: 421 Misdirected Request: "the request was directed at a server that is not able to produce
#: a response for the combination of scheme and authority" -- which is precisely the case.
HOST_REFUSED_STATUS: Final = 421

HOST_REFUSED_MESSAGE: Final = (
    "This server answers only to its own loopback names "
    f"({', '.join(sorted(LOOPBACK_HOSTS))}). The Host header of this request named "
    "something else, so it was refused without being served.\n"
)

#: The policy, one directive per line, joined below. ``default-src`` is the fetch-directive
#: fallback and covers script, style, image, font, media and connection; the other four are
#: **not** fetch directives and do not fall back to it, so a policy of ``default-src 'self'``
#: alone left every page frameable by any origin (KI-050): ``frame-ancestors`` is the header
#: half of clickjacking defence (and the successor to ``X-Frame-Options``), ``base-uri`` stops
#: an injected ``<base>`` from re-pointing every relative URL on the page, ``form-action``
#: bounds where a form may post -- M2's "Run now" and "Cancel" land inside this header -- and
#: ``object-src 'none'`` retires plugin content, which ``default-src`` would otherwise allow
#: from this origin. Each appears exactly once: in CSP the first occurrence of a directive
#: wins and a later one is ignored, so a duplicate is a quiet way to believe a policy that is
#: not in force (``tests/web/test_app.py`` asserts both the set and the absence of repeats).
CONTENT_SECURITY_POLICY: Final = "; ".join((
    "default-src 'self'",
    "frame-ancestors 'none'",
    "base-uri 'none'",
    "form-action 'self'",
    "object-src 'none'",
))  # fmt: skip

#: Applied to every response, including a refusal and a static file. ``setdefault`` leaves a
#: header a route set for itself alone.
SECURITY_HEADERS: Final[tuple[tuple[str, str], ...]] = (
    ("content-security-policy", CONTENT_SECURITY_POLICY),
    ("x-content-type-options", "nosniff"),
    ("referrer-policy", "no-referrer"),
)


def hostname_of(host_header: str) -> str:
    """The name out of a ``Host`` header, lowercased, with any port dropped.

    ``[::1]:8765`` keeps its brackets, because that is how an IPv6 literal is written in an
    authority and how it is matched here.
    """
    value = host_header.strip().lower()
    if value.startswith("["):
        closing = value.find("]")
        return value if closing == -1 else value[: closing + 1]
    return value.split(":", 1)[0]


class HostCheck:
    """Refuse any request whose ``Host`` is not a name this server answers to."""

    def __init__(self, app: ASGIApp, allowed: frozenset[str] = LOOPBACK_HOSTS) -> None:
        self.app = app
        self.allowed = allowed

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        # A missing Host is refused with the rest: HTTP/1.1 requires the header, so its
        # absence is either a broken client or a handmade request, and this fails closed.
        if hostname_of(Headers(scope=scope).get("host", "")) not in self.allowed:
            refusal = PlainTextResponse(HOST_REFUSED_MESSAGE, status_code=HOST_REFUSED_STATUS)
            await refusal(scope, receive, send)
            return
        await self.app(scope, receive, send)


class SecurityHeaders:
    """Add :data:`SECURITY_HEADERS` to every HTTP response this application sends."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in SECURITY_HEADERS:
                    headers.setdefault(name, value)
            await send(message)

        await self.app(scope, receive, send_with_headers)
