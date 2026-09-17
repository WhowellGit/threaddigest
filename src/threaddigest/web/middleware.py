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

**Response headers (spec row UI-05, half of it).** ``Content-Security-Policy: default-src
'self'`` is the cheap defence in depth behind the markdown surface: no external script,
style, image or connection, so a string that survives sanitizing still has nowhere to send
what it reads. ``X-Content-Type-Options: nosniff`` stops a browser from deciding that a
stored body is really HTML, and ``Referrer-Policy: no-referrer`` keeps local URLs out of the
``Referer`` of every deep link into reddit.com. The other half of UI-05 -- the scan that
every ``|safe`` operand is a sanitized ``*_html`` column -- arrives with the first template
that renders stored content; nothing here renders any.

**What is deliberately NOT here yet.** The same-origin check on state-changing requests
(``Sec-Fetch-Site`` with the ``Origin``/``Referer`` fallback on plain HTTP, UI-21) and basic
auth behind ``THREADDIGEST_UI_PASSWORD`` (UI-24) land with the first POST. This slice has no
POST and no route that writes, so the loopback bind plus this Host check is the whole
perimeter. A CSRF check written now would guard nothing, and could not be tested against a
real mutation, which is the kind of mechanism that rots.
"""

from __future__ import annotations

from typing import Final

from starlette.datastructures import Headers, MutableHeaders
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

__all__ = [
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

#: Applied to every response, including a refusal and a static file. ``setdefault`` leaves a
#: header a route set for itself alone.
SECURITY_HEADERS: Final[tuple[tuple[str, str], ...]] = (
    ("content-security-policy", "default-src 'self'"),
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
