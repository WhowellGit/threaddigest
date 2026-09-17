"""In-memory ``RedditGateway`` that tests and demos build scenarios on.

``FakeRedditGateway`` is deterministic, needs no network, and mimics the *shape* of what
PRAW/Reddit return (wire-shape dicts, ``more`` stubs, ``info()`` omissions and reordering,
the domain exceptions from ``ports``) so that services tested against it also work against
the real adapter. It ships in ``src/`` so ``threaddigest run --gateway fake`` works for demos.
The builder API follows section A of ``docs/reference/reviews/2026-09-13-panel-ingest.md``.

Identity conventions
--------------------
``add_post``/``add_comment``/``add_crosspost`` return **fullnames** (``t3_…``/``t1_…``);
``add_subreddit`` returns the lower-cased name. Every method that takes an item accepts a
fullname or a bare id; subreddit names are case-insensitive. ``MoreStub.children`` are bare
ids, as on the wire. ``created_utc`` may be omitted when a ``Clock`` was injected (it defaults
to ``clock.now()``); without a clock it is required.

Behaviour summary
-----------------
* **One world.** Listing, tree, ``info()`` and search all read the same store,
  so ``delete``/``remove``/``restore``/``edit`` show on every path at once, unless a listing
  is explicitly frozen (``freeze_listing``) or an item hidden (``hidden=True``/``unhide``,
  ``vanish``, ``drop_from_tree``).
* **Listings** (``iter_new_pages``): posts of a subreddit newest-first by ``created_utc``
  (ties: latest inserted first; ``set_listing_order(sticky_first=True)`` pins stickies), cut
  into pages over the *underlying* set (100 items, or ``set_page_size``) and then filtered
  for listed items, so deleted/removed/hidden/vanished posts drop out of ``/new`` and a page
  may be short with a non-None ``after`` (as on Reddit). Capped at 1,000 items. ``after`` is
  the fullname of the page's last underlying item; passing it back resumes exactly there.
  ``set_overlap`` makes each following page repeat the previous page's last ``n`` items.
* **Trees** (``fetch_tree``): 1 request for the post plus its visible comments, then ``more``
  stubs expanded largest ``count`` first (ties: earliest added), one request each, up to
  ``more_limit``; a stub is only known (and reported) once its parent is visible, like PRAW's
  discovery. ``count == 0`` stubs are "continue this thread" links. ``set_tree_clamp(n)``
  turns everything after the first ``n`` comments into synthetic stubs (the ``?limit`` clamp).
  ``add_more(..., redelivers=[…])`` makes an expansion return comments that are already
  visible, the shape a real ``morechildren`` produces when asked with ``limit_children=0``;
  each comment still comes back once, which is the port's promise (KI-042).
  Deleted *leaf* comments vanish from trees; deleted comments with children stay as
  ``[deleted]`` placeholders; removed comments stay as ``[removed]``. Each comment carries
  ``depth``.
* **info()**: found items only, chunked by 100 (one request per chunk, zero for an empty
  call), in insertion order unless ``set_info_order(shuffle=True)``; comments come back
  without ``depth``; deleted/removed items come back as tombstones; ``vanish``ed items and
  items of a ``ban_subreddit(info_returns=False)`` subreddit are omitted.
* **Failures**: ``rate_limit_next`` / ``fail_next`` / ``set_html_403`` / ``set_auth_failed``
  apply to the next request(s) of any kind; ``set_status``/``ban_subreddit`` to every request
  touching that subreddit; ``fail_page`` / ``fail_tree`` / ``fail_info`` to one page, tree or
  ``info`` batch. Order of checks on a request: crash injection, HTML 403, the ``fail_next``
  queue (rate limit, auth), subreddit status, targeted failure. A failed request still counts
  in ``requests_made`` (it was a round-trip). Every injection is a queue consumed in order;
  ``assert_no_unconsumed_injections()`` (called by the test fixture at teardown) fails when a
  planted failure was never reached.
* **Crashes and hooks**: ``crash_after(kind, n)`` raises ``CrashInjected`` (not a
  ``GatewayError``, so gateway handlers do not swallow it) when operation ``n+1`` of ``kind``
  begins, i.e. after ``n`` completed; one-shot, so a rerun completes. ``block_on(kind, n,
  event)`` parks the n-th operation of ``kind`` on a ``threading.Event``; ``on_call(kind, n,
  callback)`` runs a callback when it begins (e.g. advance the fake clock). Kinds are
  ``CRASH_KINDS``.
* **Accounting**: ``requests_made`` counts simulated round-trips (1 per page, 1 + expansions
  per tree, ceil(n/100) per ``info``, 1 per ``about``, 1 per search page); ``requests`` lists
  them as ``"GET ..."`` strings; ``calls`` records every gateway
  method call as ``Call(method, args, kwargs, cost, seq)`` where ``cost`` is the number of
  requests that call made so far (a lazy iterator's cost grows as it is consumed).

Fixture schema (``from_fixture`` / ``load_fixture`` / ``to_fixture``; written by
``probe --save-fixture``)
-----------------------------------------------------------------------------
A JSON object::

    {
      "version": 1,
      "subreddits": [
        {"display_name": "premiere", "name": "t5_2qh1u", "subscribers": 120000,
         "subreddit_type": "public", "over18": false}
      ],
      "posts":    [ {<wire post dict>}, ... ],
      "comments": [ {<wire comment dict>}, ... ],
      "more":     [ {"post_id": "1abc2d", "parent_fullname": "t1_xyz", "count": 12,
                     "children": ["c1", "c2"]}, ... ]
    }

``posts`` and ``comments`` are the ``data`` objects as Reddit returned them, with every author
name and account id replaced by ``core.fixture_scrub`` before saving (at least
``id``, ``subreddit``, ``title``, ``created_utc`` for posts; ``id``, ``link_id``,
``parent_id``, ``body``, ``created_utc`` for comments); ``name`` is derived when absent,
``depth`` is dropped (recomputed) and ``num_comments`` is kept as captured. Subreddits
referenced by posts but absent from ``subreddits`` are created with defaults. Content state
is inferred from the wire markers: ``removed_by_category == "deleted"`` / body
``"[deleted]"`` -> deleted, any other ``removed_by_category`` / body ``"[removed]"`` ->
removed. Every section is optional.
"""

from __future__ import annotations

from threaddigest.adapters.reddit_fake.gateway import FakeRedditGateway
from threaddigest.adapters.reddit_fake.records import (
    CRASH_KINDS,
    INFO_CHUNK,
    LISTING_CAP,
    PAGE_SIZE,
    SEARCH_CAP,
    SHAPE_KINDS,
    STATUSES,
    Call,
    CrashInjected,
)

# Everything else the single module defined at top level. None of it was ever in ``__all__``
# and nothing outside this package imports it, but the redundant ``as`` form re-exports each
# name so the dotted path keeps resolving exactly as it did, without touching ``__all__``.
from threaddigest.adapters.reddit_fake.records import RATE_WINDOW as RATE_WINDOW
from threaddigest.adapters.reddit_fake.records import SEARCH_WINDOWS as SEARCH_WINDOWS
from threaddigest.adapters.reddit_fake.records import ExcSpec as ExcSpec
from threaddigest.adapters.reddit_fake.records import Transform as Transform
from threaddigest.adapters.reddit_fake.records import _as_failure as _as_failure
from threaddigest.adapters.reddit_fake.records import _author_fullname as _author_fullname
from threaddigest.adapters.reddit_fake.records import _bare as _bare
from threaddigest.adapters.reddit_fake.records import _base36 as _base36
from threaddigest.adapters.reddit_fake.records import _Block as _Block
from threaddigest.adapters.reddit_fake.records import _Failure as _Failure
from threaddigest.adapters.reddit_fake.records import _Hook as _Hook
from threaddigest.adapters.reddit_fake.records import _html as _html
from threaddigest.adapters.reddit_fake.records import _More as _More
from threaddigest.adapters.reddit_fake.records import _pop_failure as _pop_failure
from threaddigest.adapters.reddit_fake.records import _Sub as _Sub
from threaddigest.adapters.reddit_fake.trees import _Tree as _Tree

__all__ = [
    "CRASH_KINDS",
    "INFO_CHUNK",
    "LISTING_CAP",
    "PAGE_SIZE",
    "SEARCH_CAP",
    "SHAPE_KINDS",
    "STATUSES",
    "Call",
    "CrashInjected",
    "FakeRedditGateway",
]
