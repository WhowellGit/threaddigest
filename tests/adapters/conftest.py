"""Cassette policy for the adapter suite, shipped before the first cassette exists.

Runbook § 9 precondition (4): the filters that keep a credential out of a recorded exchange
must be in the tree *before* the probe day, because a cassette is committed history and a
filter added afterwards cannot unrecord a token. ``vcr_config`` is the fixture
``pytest-recording`` reads; overriding it here applies to every test under
``tests/adapters/``.

What is filtered, and why each one:

* ``Authorization`` on the request -- the bearer token every Reddit call carries.
* ``Set-Cookie`` on the response -- Reddit sets a session cookie on the token endpoint.
  ``filter_headers`` only reaches requests, so the response side is done by
  :func:`scrub_response`.
* ``code``, ``password`` and ``refresh_token`` in a posted form -- none of them is used by
  this project's read-only flow (settled negative N-03), which is exactly why a recording
  that somehow carried one would go unnoticed.
* ``access_token`` and ``refresh_token`` in a JSON body -- the token endpoint's answer, the
  one secret a cassette of this project is actually likely to hold.

Header names are listed in both cases because a VCR filter matches the name it is given and
HTTP header names are case-insensitive on the wire.

``record_mode`` is ``none``: replay only. Recording is an explicit
``--record-mode=once`` on the probe day, never a default that could re-record in CI.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import pytest

CASSETTE_DIR = Path(__file__).parent / "cassettes"

FILTERED_HEADERS = (
    "authorization",
    "Authorization",
    "set-cookie",
    "Set-Cookie",
)
FILTERED_POST_DATA = ("code", "password", "refresh_token")
TOKEN_KEYS = ("access_token", "refresh_token")
REDACTED = "FILTERED"


def _redact_body(raw: object) -> object | None:
    """A JSON body with every token key blanked, or None when there is nothing to change."""
    text = raw.decode("utf-8", "replace") if isinstance(raw, bytes) else raw
    if not isinstance(text, str):
        return None
    try:
        payload = json.loads(text)
    except ValueError:
        return None
    if not isinstance(payload, dict) or not any(key in payload for key in TOKEN_KEYS):
        return None
    for key in TOKEN_KEYS:
        if key in payload:
            payload[key] = REDACTED
    replaced = json.dumps(payload)
    return replaced.encode("utf-8") if isinstance(raw, bytes) else replaced


def scrub_response(response: dict[str, Any]) -> dict[str, Any]:
    """Blank the OAuth token in a response body and drop the cookies it sets."""
    scrubbed = copy.deepcopy(response)
    headers = scrubbed.get("headers")
    if isinstance(headers, dict):
        for name in [n for n in headers if n.lower() == "set-cookie"]:
            headers[name] = [REDACTED]
    body = scrubbed.get("body")
    if isinstance(body, dict) and "string" in body:
        redacted = _redact_body(body["string"])
        if redacted is not None:
            body["string"] = redacted
    return scrubbed


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    """The recording contract every cassette in this package is written under."""
    return {
        "cassette_library_dir": str(CASSETTE_DIR),
        "record_mode": "none",
        "filter_headers": list(FILTERED_HEADERS),
        "filter_post_data_parameters": list(FILTERED_POST_DATA),
        "before_record_response": scrub_response,
    }
