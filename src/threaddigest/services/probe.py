"""The `probe` command's five capture modes, and `save`: the credentialed probe day's tool
(runbook § 9, plan § CLI).

Every ``capture_*`` calls exactly one :class:`~threaddigest.ports.RedditGateway` method,
scrubs the result with :func:`threaddigest.core.fixture_scrub.scrub` before it is ever printed
or returned, and reports ``requests_used`` from the gateway's own ``requests_made`` counter --
never a hand count, so a retry or a chunked ``info()`` batch is costed exactly as the gateway
saw it. Irreversible rule 1 ("never write outside the resolved data directory") is why
:func:`save` writes under ``<data_dir>/probe/`` and nowhere else: a fixture worth keeping is
promoted into ``tests/fixtures/json/captures/`` as a second, deliberate step (the ``cp`` line
:func:`save` returns via :func:`promotion_command`), never written there directly.

``save`` re-runs the scrub unconditionally, even though every ``capture_*`` already ran it: it
is the last gate before disk, and a caller that builds a ``Capture`` by hand (a test, a future
composed capture) must not be able to skip the one rule that keeps a real Reddit username out of
committed history. It also refuses to overwrite an existing file -- a silent clobber is the
expensive failure on a one-shot credentialed day, so a repeated ``--save-fixture NAME`` is a
:class:`FixtureExistsError`, not a quiet rewrite.

``--blank-bodies`` (runbook § 9 rows P-03, P-08, P-13, P-19, P-20: "structure only, bodies
blanked") is the probe's job, not the scrub's: :func:`fixture_scrub.scrub` never touches text,
because the probe records against a personal restricted test subreddit and a public capture is
the one that needs its body emptied before it can be committed.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final, Literal

from threaddigest.core import fixture_scrub
from threaddigest.ports import RawItem, RedditGateway

__all__ = [
    "FIXTURE_PROMOTION_ROOT",
    "PROBE_SUBDIR",
    "Capture",
    "FixtureExistsError",
    "Mode",
    "capture_about",
    "capture_info",
    "capture_listing",
    "capture_search",
    "capture_tree",
    "promotion_command",
    "save",
]

type Mode = Literal["about", "listing", "tree", "info", "search"]

#: Where a saved capture lands, relative to the resolved data directory (irreversible rule 1).
PROBE_SUBDIR: Final = Path("probe")

#: Where a promoted capture lands once someone deliberately commits it (CONTRACT item 3: never
#: written there directly by ``save``, only printed as the next step).
FIXTURE_PROMOTION_ROOT: Final = Path("tests/fixtures/json/captures")

#: The wire fields a body blank empties; every other field (ids, scores, timestamps, flags)
#: is left alone.
_BLANKED_KEYS: Final = frozenset({"selftext", "body", "selftext_html", "body_html"})


class FixtureExistsError(RuntimeError):
    """``save`` refuses to overwrite an existing capture.

    A silent clobber is the expensive failure on a one-shot credentialed day: the file that
    would have been overwritten is unrecoverable, while a refusal costs only a rename.
    """

    def __init__(self, path: Path) -> None:
        super().__init__(f"{path} already exists; choose a different --save-fixture name")
        self.path = path


@dataclass(frozen=True, slots=True)
class Capture:
    """One probe capture: the mode, what it targeted, the scrubbed payload, and its cost."""

    mode: Mode
    target: str
    payload: Any
    requests_used: int


def capture_about(gateway: RedditGateway, name: str) -> Capture:
    """``about``: the subreddit object, one request."""
    before = gateway.requests_made
    payload = fixture_scrub.scrub(gateway.about(name))
    return Capture(
        mode="about", target=name, payload=payload, requests_used=gateway.requests_made - before
    )


def capture_listing(gateway: RedditGateway, name: str, *, limit: int) -> Capture:
    """``listing``: up to ``limit`` items of ``/new``, paging forward as needed.

    Each page is fetched one at a time (``max_pages=1``, the previous page's cursor passed
    back as ``after``) so the loop can stop the moment ``limit`` is reached rather than paying
    for a page nothing will use; the last page's items are trimmed so the saved count is exactly
    ``limit`` (or fewer, once the listing itself is exhausted). Every page's cursor and
    completeness is recorded under ``"pages"`` (runbook § 9 P-21: "the cursors recorded").
    """
    before = gateway.requests_made
    items: list[RawItem] = []
    pages: list[dict[str, Any]] = []
    after: str | None = None
    while len(items) < limit:
        page = next(gateway.iter_new_pages(name, max_pages=1, after=after))
        pages.append({"after": page.after, "complete": page.complete, "count": len(page.items)})
        items.extend(page.items)
        after = page.after
        if page.complete:
            break
    payload = fixture_scrub.scrub({"items": items[:limit], "pages": pages})
    return Capture(
        mode="listing", target=name, payload=payload, requests_used=gateway.requests_made - before
    )


def capture_tree(gateway: RedditGateway, post_id: str, *, more_limit: int) -> Capture:
    """``tree``: the post, its flattened comments, and the unexpanded ``more`` stubs."""
    before = gateway.requests_made
    tree = gateway.fetch_tree(post_id, more_limit=more_limit)
    payload = fixture_scrub.scrub(
        {
            "post": tree.post,
            "comments": tree.comments,
            "more": [
                {
                    "parent_fullname": stub.parent_fullname,
                    "count": stub.count,
                    "children": list(stub.children),
                }
                for stub in tree.more
            ],
            "complete": tree.complete,
        }
    )
    return Capture(
        mode="tree", target=post_id, payload=payload, requests_used=gateway.requests_made - before
    )


def capture_info(gateway: RedditGateway, fullnames: Sequence[str]) -> Capture:
    """``info``: one ``/api/info`` batch, found items only, in whatever order the gateway gives."""
    before = gateway.requests_made
    payload = fixture_scrub.scrub(gateway.info(fullnames))
    return Capture(
        mode="info",
        target=",".join(fullnames),
        payload=payload,
        requests_used=gateway.requests_made - before,
    )


def capture_search(gateway: RedditGateway, query: str, *, sort: str, time_filter: str) -> Capture:
    """``search``: every page the gateway's own default cap yields, cursors recorded like
    ``listing`` -- search is incomplete by nature (the port's own docstring), so there is no
    ``--limit`` to bound it further."""
    before = gateway.requests_made
    items: list[RawItem] = []
    pages: list[dict[str, Any]] = []
    for page in gateway.search(query, sort=sort, time_filter=time_filter):
        pages.append({"after": page.after, "complete": page.complete, "count": len(page.items)})
        items.extend(page.items)
    payload = fixture_scrub.scrub({"items": items, "pages": pages})
    return Capture(
        mode="search",
        target=query,
        payload=payload,
        requests_used=gateway.requests_made - before,
    )


def _blank(node: Any) -> Any:
    if isinstance(node, list):
        return [_blank(item) for item in node]
    if not isinstance(node, dict):
        return node
    return {
        key: ("" if key in _BLANKED_KEYS and isinstance(value, str) else _blank(value))
        for key, value in node.items()
    }


def promotion_command(path: Path, name: str) -> str:
    """The ``cp`` line that promotes a saved capture into the committed fixture set.

    A separate, repeatable step on the probe day (CONTRACT item 3): irreversible rule 1
    forbids `save` from writing under ``tests/fixtures/`` itself, so this is printed instead,
    naming the exact command, so the probe day does not have to remember the destination.
    """
    return f"cp {path} {FIXTURE_PROMOTION_ROOT / f'{name}.json'}"


def save(capture: Capture, *, data_dir: Path, name: str, blank_bodies: bool = False) -> Path:
    """Write ``capture``'s payload, scrubbed again and optionally body-blanked, to
    ``<data_dir>/probe/<name>.json``. Refuses to overwrite an existing file.

    The scrub runs here unconditionally -- not "only if ``capture`` was not already scrubbed"
    -- because ``save`` is the last gate before disk and must be safe on its own, the same
    reasoning ``core.fixture_scrub``'s own docstring gives for why the identifier gate exists
    at all.
    """
    probe_dir = data_dir / PROBE_SUBDIR
    probe_dir.mkdir(parents=True, exist_ok=True)
    target = probe_dir / f"{name}.json"
    if target.exists():
        raise FixtureExistsError(target)
    payload = fixture_scrub.scrub(capture.payload)
    if blank_bodies:
        payload = _blank(payload)
    target.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return target
