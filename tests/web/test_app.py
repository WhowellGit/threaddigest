"""The application itself: every route renders, every response is safe, the perimeter holds.

Spec rows UI-01 (every page route on a seeded and an empty database), UI-03 (query parameters
never 500), UI-05 (the content-safety headers), UI-22 (the ``Host`` check on every request,
reads included) and UI-51 (the accessibility basics).

The route list is **discovered** from ``app.routes``, never typed here: a hand-maintained
list of routes is a list to forget to update, and the guard design rule is to scan a
structural shape rather than police a list. A route taking a path parameter this file cannot
fill is a failure, not a skip, so a new route cannot slip past by being unfillable.

DOM assertions are made with ``selectolax`` against structure -- a count of ``h1``, the
presence of a landmark, a label for an input -- never against a whole-page snapshot, which
would break on every wording change while proving nothing about the page.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.routing import APIRoute
from hypothesis import given
from hypothesis import settings as hypothesis_settings
from hypothesis import strategies as st
from jinja2 import StrictUndefined
from selectolax.parser import HTMLParser, Node
from sqlalchemy import Engine
from starlette.responses import PlainTextResponse
from starlette.testclient import TestClient
from starlette.types import Receive, Scope, Send

from tests.web.conftest import LOOPBACK_ORIGIN, REPORT_DATE, History, database_at_head
from threaddigest.settings import Settings
from threaddigest.web.app import build_templates, create_app
from threaddigest.web.filters import count
from threaddigest.web.middleware import HOST_REFUSED_STATUS, SECURITY_HEADERS, HostCheck

PATH_PARAMETER = re.compile(r"{(\w+)}")


def _children(node: object) -> list[object]:
    """The routes inside a node of the tree, whatever kind of node it is.

    FastAPI 0.141 keeps an included router as a single ``_IncludedRouter`` node holding the
    original ``APIRouter``, and a ``Mount`` holds whatever it was mounted with; a flat scan
    of ``app.routes`` therefore finds no page route at all, which is why :func:`page_urls`
    refuses an empty result rather than passing vacuously.
    """
    return list(getattr(getattr(node, "original_router", node), "routes", []))


def page_routes(app: FastAPI) -> list[APIRoute]:
    """Every GET route a browser can reach, read off the application."""
    found: list[APIRoute] = []
    pending: list[object] = list(app.routes)
    while pending:
        node = pending.pop()
        if isinstance(node, APIRoute):
            if "GET" in node.methods:
                found.append(node)
        else:
            pending.extend(_children(node))
    return found


def page_urls(app: FastAPI, values: Mapping[str, object]) -> list[str]:
    """Each discovered route as a concrete URL; an unfillable parameter fails the test."""
    urls: list[str] = []
    for route in page_routes(app):
        missing = set(PATH_PARAMETER.findall(route.path)) - set(values)
        assert not missing, (
            f"{route.path} takes path parameters this file cannot fill ({sorted(missing)}); "
            "add a value to the mapping rather than leaving the route untested"
        )
        urls.append(route.path.format(**values))
    assert urls, "no page route was discovered; the scan found nothing to check"
    return urls


# ----------------------------------------------------------------- accessibility (UI-51)


def _labelled(field: Node, tree: HTMLParser) -> bool:
    if field.attributes.get("aria-label") or field.attributes.get("aria-labelledby"):
        return True
    field_id = field.attributes.get("id")
    if field_id and tree.css(f'label[for="{field_id}"]'):
        return True
    parent = field.parent
    while parent is not None:
        if parent.tag == "label":
            return True
        parent = parent.parent
    return False


def accessibility_problems(html: str) -> list[str]:
    """Every clause of UI-51 this page breaks, as sentences.

    Written over whatever the page contains rather than over the controls these two pages
    happen to have, so the same function keeps biting as inputs, collapse toggles and sort
    links arrive with the M2 pages.
    """
    tree = HTMLParser(html)
    problems: list[str] = []
    headings = tree.css("h1")
    if len(headings) != 1:
        problems.append(f"{len(headings)} <h1> elements; a page has exactly one")
    problems += [
        f"no <{mark}> landmark"
        for mark in ("header", "nav", "main", "footer")
        if not tree.css(mark)
    ]
    links = tree.css("a[href]")
    if not links or "skip" not in (links[0].attributes.get("class") or ""):
        problems.append("the first link in the DOM is not the skip link")
    elif not tree.css("#" + (links[0].attributes.get("href") or "#").lstrip("#")):
        problems.append("the skip link points at no element on the page")
    problems += [
        f'a link with href="#": {link.html}' for link in links if link.attributes.get("href") == "#"
    ]
    problems += [
        f"an unlabelled {field.tag}: {field.html}"
        for field in tree.css("input, select, textarea")
        if not _labelled(field, tree)
    ]
    problems += [
        f"aria-expanded on a {node.tag}, which is not a button: {node.html}"
        for node in tree.css("[aria-expanded]")
        if node.tag != "button"
    ]
    if not tree.css('[aria-current="page"]'):
        problems.append("no navigation link marked aria-current")
    return problems


# ----------------------------------------------------------------- UI-01


def test_every_page_route_renders_on_a_seeded_database(
    client: TestClient, seeded_app: FastAPI, history: History
) -> None:
    for url in page_urls(seeded_app, {"run_id": history.ok_pk, "report_date": REPORT_DATE}):
        response = client.get(url)
        assert response.status_code == 200, f"{url}: {response.status_code}"
        assert "Undefined" not in response.text, f"{url} rendered an undefined value"
        assert len(HTMLParser(response.text).css("h1")) == 1, f"{url} has no single heading"


def test_every_page_route_renders_on_an_empty_database(
    empty_client: TestClient, empty_app: FastAPI
) -> None:
    """The empty-state branch of every template is exercised, not only the populated one."""
    for url in page_urls(empty_app, {"run_id": 1, "report_date": REPORT_DATE}):
        response = empty_client.get(url)
        # `/runs/1` has nothing to show on an empty database; 404 is the declared answer.
        assert response.status_code in {200, 404}, f"{url}: {response.status_code}"
        if response.status_code == 200:
            assert "Undefined" not in response.text
            assert len(HTMLParser(response.text).css("h1")) == 1, f"{url} has no single heading"


# ----------------------------------------------------------------- UI-51


def test_every_page_keeps_the_accessibility_basics(
    client: TestClient, seeded_app: FastAPI, history: History
) -> None:
    for url in page_urls(seeded_app, {"run_id": history.ok_pk, "report_date": REPORT_DATE}):
        problems = accessibility_problems(client.get(url).text)
        assert not problems, f"{url}: {problems}"


def test_an_empty_page_keeps_the_accessibility_basics(
    empty_client: TestClient, empty_app: FastAPI
) -> None:
    """An empty state is a page too, and loses landmarks most easily."""
    for url in page_urls(empty_app, {"run_id": 1, "report_date": REPORT_DATE}):
        response = empty_client.get(url)
        if response.status_code == 200:
            problems = accessibility_problems(response.text)
            assert not problems, f"{url}: {problems}"


def test_the_history_page_says_so_when_there_are_no_runs(empty_client: TestClient) -> None:
    body = HTMLParser(empty_client.get("/runs").text)
    assert body.css(".empty"), "an empty history renders no empty state"
    assert not body.css("table.runs"), "an empty history renders a table with no rows"


# ----------------------------------------------------------------- UI-03


@hypothesis_settings(max_examples=50, deadline=None)
@given(value=st.one_of(st.integers(min_value=-(10**9), max_value=10**9), st.text(max_size=24)))
def test_query_parameters_never_500(client: TestClient, value: int | str) -> None:
    """Anything in ``before`` is a 422 or a page, never a traceback.

    ``client`` is module-scoped, which is what lets this test name a fixture at all: a
    function-scoped fixture is not reset between generated inputs and hypothesis refuses it.
    Nothing here writes, so one client across the examples is honest.
    """
    response = client.get("/runs", params={"before": value})
    assert response.status_code in {200, 422}, f"{value!r} -> {response.status_code}"


@pytest.mark.parametrize("raw", ["0", "-1", "abc", "1e9", "1 OR 1=1", "9" * 40, "١٢٣"])
def test_an_unusable_run_id_is_refused_rather_than_raised(client: TestClient, raw: str) -> None:
    assert client.get(f"/runs/{raw}").status_code < 500


def test_an_unknown_query_parameter_is_ignored(client: TestClient) -> None:
    assert client.get("/runs", params={"sort": "new", "page": "2"}).status_code == 200


# ----------------------------------------------------------------- UI-05


def test_every_response_carries_the_content_safety_headers(
    client: TestClient, seeded_app: FastAPI, history: History
) -> None:
    """Pages, the stylesheet, a 404 and a refusal: every response, not only the happy ones."""
    urls = [
        *page_urls(seeded_app, {"run_id": history.ok_pk, "report_date": REPORT_DATE}),
        "/static/app.css",
        f"/runs/{history.total_runs + 10_000}",
    ]
    for url in urls:
        response = client.get(url)
        for name, value in SECURITY_HEADERS:
            assert response.headers.get(name) == value, f"{url} is missing {name}"
    refused = client.get("/runs", headers={"host": "evil.example"})
    assert refused.status_code == HOST_REFUSED_STATUS
    for name, value in SECURITY_HEADERS:
        assert refused.headers.get(name) == value, f"a refusal is missing {name}"


#: Every directive the policy must carry, and its value. ``frame-ancestors``, ``base-uri``,
#: ``form-action`` and ``object-src`` do **not** fall back to ``default-src``: a policy of
#: ``default-src 'self'`` alone leaves the pages frameable by any origin, which is what the
#: 2026-09-17 code panel found (seat B, finding B7; KI-050). Written out here rather than read
#: from ``SECURITY_HEADERS``, so this test states the contract instead of echoing the code.
REQUIRED_CSP_DIRECTIVES: Mapping[str, str] = {
    "default-src": "'self'",
    "frame-ancestors": "'none'",
    "base-uri": "'none'",
    "form-action": "'self'",
    "object-src": "'none'",
}


def _policy(header: str) -> dict[str, str]:
    """A ``Content-Security-Policy`` header as ``{directive: value}``."""
    parsed: dict[str, str] = {}
    for part in header.split(";"):
        name, _, value = part.strip().partition(" ")
        if name:
            parsed[name.lower()] = value.strip()
    return parsed


def test_the_policy_carries_every_directive_default_src_does_not_cover(
    client: TestClient, history: History
) -> None:
    """A page, a static file and a refusal: the policy is the same on all three.

    The directives are asserted by name and value, so a policy that lost one of them -- or
    that was never given one -- is red here even though the header is still sent.
    """
    responses = [
        client.get("/runs"),
        client.get(f"/runs/{history.ok_pk}"),
        client.get("/static/app.css"),
        client.get("/runs", headers={"host": "evil.example"}),
    ]
    for response in responses:
        header = response.headers.get("content-security-policy")
        assert header is not None, response.request.url
        assert _policy(header) == dict(REQUIRED_CSP_DIRECTIVES), header


def test_the_policy_is_one_definition_with_no_duplicate_directive() -> None:
    """The constant the middleware sends is the contract above, spelled once each.

    A repeated directive is not an error in CSP -- the first occurrence wins and the second is
    ignored -- so a duplicate would be a silent way to believe a policy that is not in force.
    """
    policy = dict(SECURITY_HEADERS)["content-security-policy"]
    assert _policy(policy) == dict(REQUIRED_CSP_DIRECTIVES)
    names = [part.strip().split(" ")[0] for part in policy.split(";") if part.strip()]
    assert len(names) == len(set(names)), policy


def test_the_pages_load_no_external_asset_and_run_no_inline_script(
    client: TestClient, history: History
) -> None:
    """`default-src 'self'` is only a promise if the page keeps it: nothing here is remote."""
    for url in ("/runs", f"/runs/{history.ok_pk}"):
        tree = HTMLParser(client.get(url).text)
        assert not tree.css("script"), f"{url} carries a script element"
        for node in tree.css("link[href], img[src], iframe[src]"):
            target = node.attributes.get("href") or node.attributes.get("src") or ""
            assert target.startswith("/"), f"{url} loads {target}, which is not same-origin"


# ----------------------------------------------------------------- UI-22


@pytest.mark.parametrize("host", ["127.0.0.1:8765", "localhost:8765", "127.0.0.1", "[::1]:8765"])
def test_a_loopback_host_is_served_on_any_port(client: TestClient, host: str) -> None:
    assert client.get("/runs", headers={"host": host}).status_code == 200


@pytest.mark.parametrize(
    "host", ["evil.example", "threaddigest.example.com", "127.0.0.1.evil.example"]
)
def test_a_foreign_host_header_is_refused_on_a_read(client: TestClient, host: str) -> None:
    """A read, not a mutation: DNS rebinding is a read attack (UI panel § D finding 7)."""
    response = client.get("/runs", headers={"host": host})
    assert response.status_code == HOST_REFUSED_STATUS
    assert host not in response.text, "the refusal echoed the host it was given"


def test_a_request_without_a_host_header_is_refused(client: TestClient) -> None:
    assert client.get("/runs", headers={"host": ""}).status_code == HOST_REFUSED_STATUS


def test_the_default_test_client_host_is_refused(seeded_app: FastAPI) -> None:
    """`testserver` is not a name this server answers to, and is refused like any other."""
    with TestClient(seeded_app) as default_host:
        assert default_host.get("/runs").status_code == HOST_REFUSED_STATUS


async def _always_served(scope: Scope, receive: Receive, send: Send) -> None:
    await PlainTextResponse("served")(scope, receive, send)


def test_positive_control_without_the_host_check_a_foreign_host_is_served() -> None:
    """The refusal comes from the middleware, not from the router or a template.

    The same request against the same inner application is served when ``HostCheck`` is not
    in front of it, so a Host check that silently stopped running would turn this pair from
    (200, 421) into (200, 200) and fail here.
    """
    # No `with`: a bare ASGI function answers no lifespan message, and neither side of this
    # control needs one.
    bare = TestClient(_always_served, base_url="http://evil.example")
    assert bare.get("/runs").status_code == 200
    guarded = TestClient(HostCheck(_always_served), base_url="http://evil.example")
    assert guarded.get("/runs").status_code == HOST_REFUSED_STATUS


# ----------------------------------------------------------------- the environment and the engine


def test_the_template_environment_is_strict_and_escapes_everywhere() -> None:
    env = build_templates().env
    assert env.undefined is StrictUndefined, "a missing variable would render as nothing"
    assert env.autoescape, "autoescape is off"
    assert set(env.filters) >= {"when", "duration", "count"}


def test_the_count_filter_refuses_a_number_without_its_population() -> None:
    with pytest.raises(TypeError, match="core.digest.Count"):
        count(12)


def test_the_application_opens_and_disposes_an_engine_it_was_not_given(tmp_path: Path) -> None:
    """One engine per process, opened from the data directory and closed at shutdown."""
    data_dir = tmp_path / "own"
    database_at_head(data_dir).dispose()
    app = create_app(settings=Settings(data_dir=data_dir))
    with TestClient(app, base_url=LOOPBACK_ORIGIN) as started:
        assert started.get("/runs").status_code == 200
        pool = app.state.engine.pool
    # `Engine.dispose()` replaces the pool, so a new pool object is the observable proof that
    # shutdown ran; the engine object itself is the same either way.
    assert app.state.engine.pool is not pool, "the lifespan did not dispose the engine it opened"


def test_an_injected_engine_is_left_to_whoever_made_it(
    seeded_app: FastAPI, seeded_engine: Engine
) -> None:
    """A caller that hands in an engine keeps its lifetime; shutdown does not touch it."""
    with TestClient(seeded_app, base_url=LOOPBACK_ORIGIN) as started:
        assert started.get("/runs").status_code == 200
        pool = seeded_app.state.engine.pool
    assert seeded_app.state.engine.pool is pool, "shutdown disposed an engine it does not own"
    assert seeded_app.state.engine is seeded_engine
