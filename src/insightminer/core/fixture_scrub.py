"""Replace every author name and author id in a captured Reddit payload before it becomes a fixture.

Ruled 2026-09-16 (the plan-version-two deep review, readiness seat F2): a fixture committed under
``tests/fixtures/`` is permanent history, the repository has had its history rewritten three times
for identifiers that should never have entered it, and the policy facts require an author's
identifying references to be removable when the account is deleted. So the probe never saves a
payload as Reddit returned it: it saves what :func:`scrub` returns, and the identifier gate refuses
any fixture outside the hand-written synthetic set that still carries a real name or id.

What is replaced: every string under a key named ``author`` or ending in ``_author``, and every
string that is a Reddit account id (``t2_`` followed by base-36 digits), wherever it sits in the
payload. Replacements are stable within one payload: the same author becomes the same
``fx_user_<n>``, and an id found beside a name in the same object takes that name's number, so
the relationships the tests rely on (this comment's author is that post's author) survive.

What is kept: ``[deleted]`` and ``[removed]`` (the wire markers the content-state machine reads),
``AutoModerator`` (a bot, not a person), and every other field, because scores, timestamps,
bodies and flags are what the fixtures exist to preserve. Text bodies are not scrubbed here: the
probe records against a personal restricted test subreddit, so no third-party text is captured
(runbook § 9); a public capture is saved with its body blanked by the probe, not by this module.

Pure and total: no I/O, no randomness, a new object is returned and the input is not mutated, and
scrubbing an already scrubbed payload changes nothing.
"""

from __future__ import annotations

import re
from typing import Any, Final

__all__ = [
    "AUTHOR_ID",
    "KEPT_AUTHORS",
    "SYNTHETIC_ID",
    "SYNTHETIC_NAME",
    "offending_values",
    "scrub",
]

#: A key whose string value names an account: ``author``, ``link_author``, ``crosspost_author``.
AUTHOR_KEY: Final = re.compile(r"^(?:author|.+_author)$")
#: A Reddit account id on the wire.
AUTHOR_ID: Final = re.compile(r"^t2_[0-9a-z]+$")
#: The synthetic forms the scrub writes and the gate accepts.
SYNTHETIC_NAME: Final = re.compile(r"^fx_user_\d+$")
SYNTHETIC_ID: Final = re.compile(r"^t2_fx\d+$")
#: Wire markers and the one account that is a bot, never a person.
KEPT_AUTHORS: Final = frozenset({"[deleted]", "[removed]", "AutoModerator"})


class _Numbering:
    """Stable numbers for the names and ids seen in one payload, in order of first sight."""

    def __init__(self) -> None:
        self.names: dict[str, int] = {}
        self.ids: dict[str, int] = {}
        self.next = 1

    def _fresh(self) -> int:
        number, self.next = self.next, self.next + 1
        return number

    def for_name(self, name: str) -> int:
        if name not in self.names:
            self.names[name] = self._fresh()
        return self.names[name]

    def for_id(self, account_id: str, beside: int | None) -> int:
        if account_id not in self.ids:
            self.ids[account_id] = beside if beside is not None else self._fresh()
        return self.ids[account_id]


def _needs_name(value: object) -> bool:
    return isinstance(value, str) and value not in KEPT_AUTHORS and not SYNTHETIC_NAME.match(value)


def _needs_id(value: object) -> bool:
    return isinstance(value, str) and bool(AUTHOR_ID.match(value)) and not SYNTHETIC_ID.match(value)


def _scrub(node: Any, numbers: _Numbering, beside: int | None = None) -> Any:
    if _needs_id(node):
        return f"t2_fx{numbers.for_id(node, beside)}"
    if isinstance(node, list):
        return [_scrub(item, numbers) for item in node]
    if not isinstance(node, dict):
        return node
    # An id beside a name in the same object takes the name's number, so the pair stays a pair.
    author = node.get("author")
    beside = numbers.for_name(author) if isinstance(author, str) and _needs_name(author) else None
    out: dict[str, Any] = {}
    for key, value in node.items():
        if isinstance(key, str) and AUTHOR_KEY.match(key) and _needs_name(value):
            out[key] = f"fx_user_{numbers.for_name(value)}"
        else:
            out[key] = _scrub(value, numbers, beside)
    return out


def scrub(payload: Any) -> Any:
    """The payload with every author name and account id replaced by a synthetic one."""
    return _scrub(payload, _Numbering())


def offending_values(payload: Any) -> list[str]:
    """Every author name or account id in ``payload`` that is neither kept nor synthetic, in
    document order; empty for a scrubbed payload. The gate reads this."""
    found: list[str] = []
    _collect(payload, found)
    return found


def _collect(node: Any, found: list[str]) -> None:
    if _needs_id(node):
        found.append(str(node))
        return
    if isinstance(node, list):
        for item in node:
            _collect(item, found)
        return
    if not isinstance(node, dict):
        return
    for key, value in node.items():
        if isinstance(key, str) and AUTHOR_KEY.match(key) and _needs_name(value):
            found.append(str(value))
        else:
            _collect(value, found)
