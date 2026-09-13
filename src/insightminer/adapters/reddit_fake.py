"""In-memory ``RedditGateway`` that tests and demos build scenarios on.

``FakeRedditGateway`` is deterministic, needs no network, and mimics the *shape* of what
PRAW/Reddit return (wire-shape dicts, ``more`` stubs, ``info()`` omissions and reordering,
the domain exceptions from ``ports``) so that services tested against it also work against
the real adapter. It ships in ``src/`` so ``insightminer run --gateway fake`` works for demos.
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
* **One world.** Listing, ``new_head``, tree, ``info()`` and search all read the same store,
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
  per tree, ceil(n/100) per ``info``, 1 per ``about``, 1 per ``new_head``, 1 per search
  page); ``requests`` lists them as ``"GET ..."`` strings; ``calls`` records every gateway
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

``posts`` and ``comments`` are the ``data`` objects exactly as Reddit returned them (at least
``id``, ``subreddit``, ``title``, ``created_utc`` for posts; ``id``, ``link_id``,
``parent_id``, ``body``, ``created_utc`` for comments); ``name`` is derived when absent,
``depth`` is dropped (recomputed) and ``num_comments`` is kept as captured. Subreddits
referenced by posts but absent from ``subreddits`` are created with defaults. Content state
is inferred from the wire markers: ``removed_by_category == "deleted"`` / body
``"[deleted]"`` -> deleted, any other ``removed_by_category`` / body ``"[removed]"`` ->
removed. Every section is optional.
"""

from __future__ import annotations

import copy
import json
import random
import re
import threading
import zlib
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, NamedTuple
from urllib.parse import urlsplit

from insightminer.ports import (
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
    TreeResult,
)

PAGE_SIZE = 100
LISTING_CAP = 1000
INFO_CHUNK = 100
NEW_HEAD_LIMIT = 3
RATE_WINDOW = 1000
SEARCH_CAP = 250
SEARCH_WINDOWS: dict[str, int | None] = {
    "hour": 3600,
    "day": 86_400,
    "week": 7 * 86_400,
    "month": 31 * 86_400,
    "year": 366 * 86_400,
    "all": None,
}
STATUSES = ("ok", "forbidden", "not_found", "redirect", "quarantined")
CRASH_KINDS = ("request", "page", "tree", "info", "about", "new_head", "search")
SHAPE_KINDS = ("post", "comment", "subreddit")

type ExcSpec = BaseException | type[BaseException]
type Transform = Callable[[RawItem], RawItem]


class CrashInjected(Exception):  # noqa: N818 - reads as an event, like the ports exceptions
    """The simulated process died here. Deliberately not a ``GatewayError``: nothing catches it."""


class Call(NamedTuple):
    """One recorded gateway call; a plain tuple ``(method, args, kwargs, cost, seq)``."""

    method: str
    args: tuple[Any, ...]
    kwargs: dict[str, Any]
    cost: int
    seq: int


@dataclass
class _Failure:
    make: Callable[[], BaseException]
    times: int | None  # None = every time
    label: str
    fired: int = 0

    def take(self) -> BaseException | None:
        """Return the exception to raise, or None once this failure is used up."""
        if self.times is not None:
            if self.times <= 0:
                return None
            self.times -= 1
        self.fired += 1
        return self.make()

    @property
    def unconsumed(self) -> bool:
        """Armed but never fired: the scenario did not reach it."""
        return self.fired == 0 and (self.times is None or self.times > 0)


@dataclass
class _Sub:
    key: str
    display_name: str
    fullname: str
    subscribers: int
    subreddit_type: str
    over18: bool
    seq: int
    status: str = "ok"
    redirect_path: str | None = None
    frozen: list[str] | None = None
    anchor_created_utc: float | None = None
    anchor_fullname: str | None = None
    sticky_first: bool = False
    page_sizes: list[int] = field(default_factory=list)
    overlap: int = 0
    info_returns: bool = True
    about_extra: dict[str, Any] = field(default_factory=dict)


@dataclass(eq=False)  # identity semantics: two look-alike stubs are still two stubs
class _More:
    parent_fullname: str
    count: int
    children: list[str] = field(default_factory=list)


@dataclass
class _Block:
    n: int
    event: threading.Event
    timeout: float | None
    fired: bool = False


@dataclass
class _Hook:
    n: int
    callback: Callable[[], None]
    fired: bool = False


class _Tree:
    """Visibility bookkeeping for one ``fetch_tree`` call."""

    def __init__(self, link: str, children_of: dict[str, list[str]], stubs: list[_More]) -> None:
        self.link = link
        self.children_of = children_of
        self.stubs = stubs
        self.hidden: set[str] = {c for stub in stubs for c in stub.children}
        self.expanded: list[_More] = []

    def visible(self) -> list[tuple[str, int]]:
        """``(comment id, depth)`` in depth-first order, skipping comments behind a stub."""
        out: list[tuple[str, int]] = []
        stack = [(cid, 0) for cid in reversed(self.children_of.get(self.link, []))]
        while stack:
            cid, depth = stack.pop()
            if cid in self.hidden:
                continue
            out.append((cid, depth))
            replies = self.children_of.get(f"t1_{cid}", [])
            stack.extend((reply, depth + 1) for reply in reversed(replies))
        return out

    def reachable(self) -> list[_More]:
        """Unexpanded stubs whose parent is visible: the ones PRAW would know about."""
        shown = {self.link} | {f"t1_{cid}" for cid, _ in self.visible()}
        return [s for s in self.stubs if s not in self.expanded and s.parent_fullname in shown]

    def next_stub(self) -> _More | None:
        """Largest ``count`` first, earliest added on ties (PRAW's max-heap order)."""
        candidates = self.reachable()
        if not candidates:
            return None
        return max(candidates, key=lambda s: (s.count, -self.stubs.index(s)))

    def expand(self, stub: _More) -> None:
        self.expanded.append(stub)
        self.hidden -= set(stub.children)

    def subtree_size(self, cid: str) -> int:
        total = 1
        for reply in self.children_of.get(f"t1_{cid}", []):
            total += self.subtree_size(reply)
        return total


def _base36(n: int) -> str:
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    if n == 0:
        return "0"
    out = []
    while n:
        n, r = divmod(n, 36)
        out.append(digits[r])
    return "".join(reversed(out))


def _author_fullname(author: str) -> str:
    return "t2_" + _base36(zlib.crc32(author.encode("utf-8")))


def _html(text: str) -> str | None:
    if not text:
        return None
    return f'<!-- SC_OFF --><div class="md"><p>{escape(text)}</p></div><!-- SC_ON -->'


def _as_failure(exc: ExcSpec, times: int | None, label: str) -> _Failure:
    if isinstance(exc, BaseException):
        return _Failure(lambda: exc, times, label)
    return _Failure(exc, times, label)


def _pop_failure(queue: list[_Failure]) -> BaseException | None:
    """Take from the head of ``queue``, discarding exhausted entries."""
    while queue:
        exc = queue[0].take()
        if exc is not None:
            return exc
        queue.pop(0)
    return None


def _bare(item: str) -> str:
    return item[3:] if item[:3] in {"t1_", "t3_", "t5_"} else item


class FakeRedditGateway:
    """Scenario-building in-memory Reddit. See the module docstring for the rules it follows."""

    def __init__(self, *, clock: Clock | None = None) -> None:
        # ``clock`` supplies default ``created_utc``/``edited`` values and search time windows.
        self._clock = clock
        self._subs: dict[str, _Sub] = {}
        self._posts: dict[str, RawItem] = {}
        self._comments: dict[str, RawItem] = {}
        self._post_sub: dict[str, str] = {}
        self._seq: dict[str, int] = {}
        self._counter = 0
        self._id_counter = 36**6
        self._sub_counter = 36**4
        self._state: dict[str, str] = {}  # live | deleted | removed | hidden
        self._originals: dict[str, RawItem] = {}
        self.removals: dict[str, str] = {}
        self._vanished: dict[str, int | None] = {}
        self._dropped: set[str] = set()
        self._more: dict[str, list[_More]] = {}
        self._shapes: dict[str, Transform] = {}
        self._next_failures: list[_Failure] = []
        self._html_403: _Failure | None = None
        self._page_failures: dict[tuple[str, int], list[_Failure]] = {}
        self._tree_failures: dict[str, tuple[_Failure, int | None]] = {}
        self._info_failures: dict[int, list[_Failure]] = {}
        self._crash: dict[str, int] = {}
        self._completed: dict[str, int] = {}
        self._started: dict[str, int] = {}
        self._blocks: dict[str, list[_Block]] = {}
        self._hooks: dict[str, list[_Hook]] = {}
        self._cursor_pages: dict[tuple[str, str], int] = {}
        self._info_shuffle = False
        self._info_rng = random.Random(0)
        self._overlap_all = 0
        self._tree_clamp: int | None = None
        self._limits_override: Limits | None = None
        self._requests_made = 0
        self._current_call: int | None = None
        self.requests: list[str] = []
        self.calls: list[Call] = []

    # ------------------------------------------------------------------ fixtures

    @classmethod
    def from_fixture(cls, path: str | Path) -> FakeRedditGateway:
        """Build a gateway from a JSON scenario file (schema in the module docstring)."""
        fake = cls()
        fake.load_fixture(path)
        return fake

    def load_fixture(self, path: str | Path) -> None:
        """Merge a JSON scenario file into this gateway."""
        with Path(path).open(encoding="utf-8") as fh:
            data = json.load(fh)
        version = data.get("version", 1)
        if version != 1:
            msg = f"unsupported fixture version {version!r}"
            raise ValueError(msg)
        for sub in data.get("subreddits", []):
            self.add_subreddit(
                sub["display_name"],
                t5=sub.get("name"),
                subscribers=sub.get("subscribers", 0),
                subreddit_type=sub.get("subreddit_type", "public"),
                over18=sub.get("over18", False),
            )
        for post in data.get("posts", []):
            self._insert_post(dict(post))
        for comment in data.get("comments", []):
            self._insert_comment(dict(comment))
        for more in data.get("more", []):
            self.add_more(
                more["post_id"], more.get("parent_fullname"), more["count"], more["children"]
            )

    def to_fixture(self, path: str | Path) -> None:
        """Write the world as a JSON scenario file (same schema ``probe --save-fixture`` writes)."""
        subs = sorted(self._subs.values(), key=lambda s: s.seq)
        posts = sorted(self._posts.values(), key=lambda p: self._seq[p["name"]])
        comments = sorted(self._comments.values(), key=lambda c: self._seq[c["name"]])
        data = {
            "version": 1,
            "subreddits": [
                {
                    "display_name": s.display_name,
                    "name": s.fullname,
                    "subscribers": s.subscribers,
                    "subreddit_type": s.subreddit_type,
                    "over18": s.over18,
                }
                for s in subs
            ],
            "posts": copy.deepcopy(posts),
            "comments": copy.deepcopy(comments),
            "more": [
                {
                    "post_id": pid,
                    "parent_fullname": m.parent_fullname,
                    "count": m.count,
                    "children": list(m.children),
                }
                for pid, stubs in self._more.items()
                for m in stubs
            ],
        }
        Path(path).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    # --------------------------------------------------------------------- world

    def add_subreddit(
        self,
        name: str,
        *,
        display_name: str | None = None,
        t5: str | None = None,
        subreddit_type: str = "public",
        quarantine: bool = False,
        subscribers: int = 0,
        over18: bool = False,
    ) -> str:
        """Create (or update) a subreddit; returns its lower-cased name.

        ``display_name`` controls the casing Reddit reports (default: ``name`` as given);
        ``t5`` the identity. ``quarantine=True`` makes it behave as ``set_status('quarantined')``.
        """
        key = name.lower()
        sub = self._subs.get(key)
        if sub is None:
            self._sub_counter += 1
            sub = _Sub(
                key=key,
                display_name=display_name or name,
                fullname=t5 or "t5_" + _base36(self._sub_counter),
                subscribers=subscribers,
                subreddit_type=subreddit_type,
                over18=over18,
                seq=self._next_seq(),
            )
            self._subs[key] = sub
        else:
            if display_name is not None:
                sub.display_name = display_name
            if t5 is not None:
                sub.fullname = t5
            sub.subscribers = subscribers
            sub.subreddit_type = subreddit_type
            sub.over18 = over18
        self._seq[sub.fullname] = sub.seq
        if quarantine:
            sub.status = "quarantined"
        return key

    def add_post(
        self,
        sub: str,
        *,
        id: str | None = None,  # mirrors the wire field name
        title: str,
        selftext: str = "",
        author: str = "u1",
        created_utc: float | None = None,
        is_self: bool = True,
        url: str | None = None,
        num_comments: int | None = None,
        stickied: bool = False,
        hidden: bool = False,
        flair: str | None = None,
        removed_by_category: str | None = None,
        **raw: Any,
    ) -> str:
        """Add a post in wire shape; returns its fullname. Unknown subreddits are created.

        ``raw`` overrides or adds any wire key. ``hidden=True`` keeps it out of ``/new`` until
        ``unhide`` (a post sitting in the mod queue).
        """
        key = sub.lower()
        if key not in self._subs:
            self.add_subreddit(sub)
        subrow = self._subs[key]
        post_id = _bare(id) if id else self._next_id()
        created = self._created(created_utc)
        slug = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:50] or "_"
        permalink = f"/r/{subrow.display_name}/comments/{post_id}/{slug}/"
        if is_self:
            link = url or f"https://www.reddit.com{permalink}"
            domain = f"self.{subrow.display_name}"
        else:
            link = url or f"https://example.com/{post_id}"
            domain = urlsplit(link).netloc or "example.com"
        post: RawItem = {
            "id": post_id,
            "name": f"t3_{post_id}",
            "title": title,
            "selftext": selftext,
            "selftext_html": _html(selftext),
            "author": author,
            "author_fullname": _author_fullname(author),
            "author_flair_text": None,
            "author_premium": False,
            "created_utc": created,
            "created": created,
            "edited": False,
            "is_self": is_self,
            "url": link,
            "domain": domain,
            "permalink": permalink,
            "subreddit": subrow.display_name,
            "subreddit_id": subrow.fullname,
            "subreddit_name_prefixed": f"r/{subrow.display_name}",
            "subreddit_type": subrow.subreddit_type,
            "subreddit_subscribers": subrow.subscribers,
            "num_comments": num_comments or 0,
            "score": 1,
            "ups": 1,
            "downs": 0,
            "upvote_ratio": 1.0,
            "stickied": stickied,
            "pinned": False,
            "distinguished": None,
            "link_flair_text": flair,
            "link_flair_css_class": None,
            "removed_by_category": removed_by_category,
            "over_18": False,
            "spoiler": False,
            "archived": False,
            "locked": False,
            "hidden": False,
            "quarantine": False,
            "is_video": False,
            "is_original_content": False,
            "is_crosspostable": True,
            "is_robot_indexable": True,
            "num_crossposts": 0,
            "thumbnail": "self" if is_self else "default",
            "media": None,
            "secure_media": None,
            "gilded": 0,
            "total_awards_received": 0,
            "all_awardings": [],
            "likes": None,
            "view_count": None,
            "send_replies": True,
            "contest_mode": False,
            "suggested_sort": None,
        }
        if not is_self:
            post["post_hint"] = "link"
            post["url_overridden_by_dest"] = link
        if author == "[deleted]":
            del post["author_fullname"]
        post.update(raw)
        self._insert_post(post, hidden=hidden)
        return f"t3_{post_id}"

    def add_comment(
        self,
        post: str,
        *,
        parent: str | None = None,
        body: str,
        author: str = "u1",
        created_utc: float | None = None,
        score: int = 1,
        id: str | None = None,  # mirrors the wire field name
        **raw: Any,
    ) -> str:
        """Add a comment under ``parent`` (a comment id/fullname; None = top level).

        Returns the comment's fullname.

        Bumps the post's ``num_comments`` like Reddit does (deleted comments keep counting).
        """
        pid = _bare(post)
        post_row = self._posts.get(pid)
        if post_row is None:
            msg = f"unknown post {post!r}"
            raise KeyError(msg)
        parent_fullname = self._parent_fullname(pid, parent)
        if parent_fullname.startswith("t1_"):
            parent_comment = self._comments.get(parent_fullname[3:])
            if parent_comment is None or parent_comment["link_id"] != f"t3_{pid}":
                msg = f"parent {parent!r} is not a comment of post {post!r}"
                raise KeyError(msg)
        cid = _bare(id) if id else self._next_id()
        created = self._created(created_utc)
        comment: RawItem = {
            "id": cid,
            "name": f"t1_{cid}",
            "body": body,
            "body_html": _html(body),
            "author": author,
            "author_fullname": _author_fullname(author),
            "author_flair_text": None,
            "author_premium": False,
            "created_utc": created,
            "created": created,
            "edited": False,
            "score": score,
            "ups": score,
            "downs": 0,
            "score_hidden": False,
            "controversiality": 0,
            "link_id": f"t3_{pid}",
            "parent_id": parent_fullname,
            "subreddit": post_row["subreddit"],
            "subreddit_id": post_row["subreddit_id"],
            "subreddit_name_prefixed": post_row["subreddit_name_prefixed"],
            "subreddit_type": post_row["subreddit_type"],
            "permalink": f"{post_row['permalink']}{cid}/",
            "is_submitter": author == post_row.get("author"),
            "stickied": False,
            "distinguished": None,
            "collapsed": False,
            "collapsed_reason": None,
            "collapsed_reason_code": None,
            "archived": False,
            "locked": False,
            "gilded": 0,
            "total_awards_received": 0,
            "all_awardings": [],
            "likes": None,
            "send_replies": True,
        }
        if author == "[deleted]":
            del comment["author_fullname"]
        comment.update(raw)
        self._insert_comment(comment)
        post_row["num_comments"] = int(post_row.get("num_comments", 0)) + 1
        return f"t1_{cid}"

    def add_more(
        self, post: str, parent: str | None, count: int, children: Sequence[str] = ()
    ) -> None:
        """Hide ``children`` (comment ids) behind a ``more`` stub under ``parent``.

        ``parent`` is a comment id or fullname; None means the post itself. ``count == 0``
        is a "continue this thread" node. Expanding the stub reveals ``children`` and costs
        one request.
        """
        pid = _bare(post)
        if pid not in self._posts:
            msg = f"unknown post {post!r}"
            raise KeyError(msg)
        stub = _More(
            parent_fullname=self._parent_fullname(pid, parent),
            count=count,
            children=[_bare(c) for c in children],
        )
        self._more.setdefault(pid, []).append(stub)

    def add_crosspost(self, sub: str, parent_fullname: str, **raw: Any) -> str:
        """Add a crosspost of ``parent_fullname``: empty ``selftext``, ``crosspost_parent_list``."""
        parent = self._posts.get(_bare(parent_fullname))
        if parent is None:
            msg = f"unknown crosspost parent {parent_fullname!r}"
            raise KeyError(msg)
        title = raw.pop("title", parent["title"])
        created_utc = raw.pop("created_utc", None)
        fullname = self.add_post(
            sub,
            title=title,
            selftext="",
            created_utc=created_utc,
            is_self=False,
            url=f"https://www.reddit.com{parent['permalink']}",
            domain=parent.get("domain", "reddit.com"),
            crosspost_parent=parent["name"],
            crosspost_parent_list=[copy.deepcopy(parent)],
            **raw,
        )
        post = self._store(fullname)
        post.pop("post_hint", None)
        post.pop("url_overridden_by_dest", None)
        return fullname

    def set_about(self, sub: str, **fields: Any) -> None:
        """Override any key of ``about(sub)`` (e.g. ``name='t5_other'`` for an identity change)."""
        self._sub_row(sub).about_extra.update(fields)

    def set_field(self, fullname: str, key: str, value: Any) -> None:
        """Set one raw key on a stored post or comment (unknown enum values, score bumps...)."""
        fn, item = self._resolve(fullname)
        self._remember(fn)
        item[key] = value

    def remove_field(self, fullname: str, key: str) -> None:
        """Drop one raw key from a stored post or comment (e.g. an absent ``author_fullname``)."""
        fn, item = self._resolve(fullname)
        self._remember(fn)
        item.pop(key, None)

    def set_raw_shape(self, kind: str, transform: Transform | None) -> None:
        """Apply ``transform`` to every emitted payload of ``kind`` (one of ``SHAPE_KINDS``).

        Passing None clears the transform.
        """
        if kind not in SHAPE_KINDS:
            msg = f"unknown shape kind {kind!r}; expected one of {SHAPE_KINDS}"
            raise ValueError(msg)
        if transform is None:
            self._shapes.pop(kind, None)
        else:
            self._shapes[kind] = transform

    def edit(self, fullname: str, body: str, *, edited_utc: float | None = None) -> None:
        """Replace the text and set ``edited`` to a float (clock time, or created + 60 s)."""
        fn, item = self._resolve(fullname)
        self._remember(fn)
        key = "selftext" if fn.startswith("t3_") else "body"
        item[key] = body
        item[f"{key}_html"] = _html(body)
        if edited_utc is None:
            edited_utc = self._clock.now() if self._clock else float(item["created_utc"]) + 60
        item["edited"] = float(edited_utc)

    def unhide(self, fullname: str) -> None:
        """Late approval: a ``hidden=True`` post appears in ``/new`` at its chronological place."""
        fn, _ = self._resolve(fullname)
        if self._state.get(fn) == "hidden":
            self._state[fn] = "live"

    # ------------------------------------------------------------- content state

    def delete(self, fullname: str) -> None:
        """Author deletion: ``[deleted]`` author and text; posts get ``removed_by_category``.

        A deleted link post keeps its empty ``selftext`` (Reddit only blanks self text).
        """
        fn, item = self._resolve(fullname)
        self._remember(fn)
        item["author"] = "[deleted]"
        item.pop("author_fullname", None)
        if fn.startswith("t3_"):
            if item.get("is_self", True):
                item["selftext"] = "[deleted]"
                item["selftext_html"] = None
            item["removed_by_category"] = "deleted"
        else:
            item["body"] = "[deleted]"
            item["body_html"] = None
            item["collapsed_reason_code"] = "DELETED"
        self._state[fn] = "deleted"
        self.removals.pop(fn, None)

    def remove(self, fullname: str, by: str = "moderator", *, category: str | None = None) -> None:
        """Moderator/Reddit removal: ``[removed]`` text; posts carry ``removed_by_category=by``.

        ``category`` is an alias of ``by``. Comments show ``[deleted]`` as author (what
        non-moderators see) and, like Reddit, carry no ``removed_by_category``; the category is
        kept in ``self.removals`` either way.
        """
        if category is not None:
            by = category
        fn, item = self._resolve(fullname)
        self._remember(fn)
        if fn.startswith("t3_"):
            if item.get("is_self", True):
                item["selftext"] = "[removed]"
                item["selftext_html"] = None
            item["removed_by_category"] = by
        else:
            item["body"] = "[removed]"
            item["body_html"] = None
            item["author"] = "[deleted]"
            item.pop("author_fullname", None)
        self._state[fn] = "removed"
        self.removals[fn] = by

    def restore(self, fullname: str) -> None:
        """Undo ``delete``/``remove``/``edit``/``set_field``/``delete_account`` for one item."""
        fn, _ = self._resolve(fullname)
        original = self._originals.pop(fn, None)
        if original is not None:
            self._store(fn).clear()
            self._store(fn).update(copy.deepcopy(original))
        self._state[fn] = "live"
        self.removals.pop(fn, None)
        self._dropped.discard(fn)

    def delete_account(self, author: str) -> None:
        """Account deletion: author fields scrubbed on every item by ``author``; content intact."""
        for fn, item in self._all_items():
            if item.get("author") == author:
                self._remember(fn)
                item["author"] = "[deleted]"
                item.pop("author_fullname", None)

    def vanish(self, fullname: str, times: int | None = None) -> None:
        """Make the item disappear from ``info()``, listings, trees and search.

        ``times=None`` is forever; ``times=N`` lasts until ``info()`` has asked for it N times
        (so ``times=1`` is a transient miss). ``times <= 0`` clears a previous ``vanish``.
        """
        fn, _ = self._resolve(fullname)
        if times is not None and times <= 0:
            self._vanished.pop(fn, None)
        else:
            self._vanished[fn] = times

    def reappear(self, fullname: str) -> None:
        """Undo ``vanish``."""
        fn, _ = self._resolve(fullname)
        self._vanished.pop(fn, None)

    def drop_from_tree(self, comment_fullname: str) -> None:
        """Omit a comment from ``fetch_tree`` only, as Reddit drops a deleted leaf.

        ``info()`` is unaffected (it still follows ``delete``/``vanish``).
        """
        fn, _ = self._resolve(comment_fullname)
        if not fn.startswith("t1_"):
            msg = f"{comment_fullname!r} is not a comment"
            raise ValueError(msg)
        self._dropped.add(fn)

    def ban_subreddit(self, sub: str, *, info_returns: bool = True) -> None:
        """Listing/about/new_head raise ``SubredditNotFound``; ``info()`` on its items per flag."""
        row = self._sub_row(sub)
        row.status = "not_found"
        row.info_returns = info_returns

    # ---------------------------------------------------------- listing behaviour

    def set_page_size(self, sub: str, sizes: Sequence[int]) -> None:
        """Underlying page lengths per page (page 1 first); pages beyond the list use 100."""
        self._sub_row(sub).page_sizes = list(sizes)

    def set_overlap(self, sub: str | bool | None = None, n: int = 1) -> None:
        """Repeat the last ``n`` items of each page at the start of the next (a shifted listing).

        ``sub`` names one subreddit; None or True applies to all; False clears everything.
        """
        if sub is False:
            self._overlap_all = 0
            for row in self._subs.values():
                row.overlap = 0
        elif sub is None or sub is True:
            self._overlap_all = n
        else:
            self._sub_row(sub).overlap = n

    def set_listing_order(self, sub: str, *, sticky_first: bool = True) -> None:
        """Pin stickies at the head of ``/new`` instead of their chronological position."""
        self._sub_row(sub).sticky_first = sticky_first

    def freeze_listing(self, sub: str | None = None) -> None:
        """Snapshot ``/new`` for ``sub`` (all subreddits when None).

        Posts added afterwards never appear in the listing until ``unfreeze_listing``;
        ``new_head`` keeps reading the live store.
        """
        for row in self._sub_rows(sub):
            row.frozen = self._sorted_post_ids(row)

    def unfreeze_listing(self, sub: str | None = None) -> None:
        for row in self._sub_rows(sub):
            row.frozen = None

    def set_live_anchor(
        self, sub: str, created_utc: float | None = None, *, fullname: str | None = None
    ) -> None:
        """Fix what ``new_head(sub)`` returns, independent of the (possibly frozen) listing.

        Pass ``fullname`` to return that stored post, or ``created_utc`` for a synthetic post
        at that time; neither clears the anchor.
        """
        row = self._sub_row(sub)
        if fullname is not None:
            self._resolve(fullname)
            row.anchor_fullname = f"t3_{_bare(fullname)}"
            row.anchor_created_utc = None
        else:
            row.anchor_fullname = None
            row.anchor_created_utc = None if created_utc is None else float(created_utc)

    def set_info_order(self, shuffle: bool, seed: int = 0) -> None:
        """Return ``info()`` chunks in a seeded pseudo-random order instead of insertion order."""
        self._info_shuffle = shuffle
        self._info_rng = random.Random(seed)

    def set_tree_clamp(self, n: int | None) -> None:
        """Serve at most ``n`` comments in the base tree fetch; the rest become ``more`` stubs."""
        self._tree_clamp = n

    def set_limits(self, remaining: int | None, used: int | None = None) -> None:
        """Override what ``limits()`` reports (e.g. a low ``remaining`` for budget tests)."""
        self._limits_override = Limits(remaining=remaining, used=used)

    # --------------------------------------------------------- failure injection

    def fail_page(self, sub: str, page_no: int, exc: ExcSpec, times: int | None = 1) -> None:
        """Raise ``exc`` when page ``page_no`` (1-based) of ``sub``'s ``/new`` is requested."""
        label = f"fail_page({sub!r}, {page_no})"
        self._page_failures.setdefault((sub.lower(), page_no), []).append(
            _as_failure(exc, times, label)
        )

    def fail_tree(
        self,
        post: str,
        exc: ExcSpec,
        after_comments: int | None = None,
        times: int | None = 1,
    ) -> None:
        """Raise ``exc`` from ``fetch_tree(post)``.

        With ``after_comments=N`` (N > 0) the fake first performs, and counts, the expansions
        needed to reveal N comments, then raises, so ``requests_made`` reads as a mid-tree
        crash; None or 0 raises right after the base request.
        """
        pid = _bare(post)
        self._tree_failures[pid] = (_as_failure(exc, times, f"fail_tree({post!r})"), after_comments)

    def fail_info(self, batch_index: int, exc: ExcSpec, times: int | None = 1) -> None:
        """Raise ``exc`` on the ``batch_index``-th (0-based) 100-item batch of ``info()``."""
        label = f"fail_info({batch_index})"
        self._info_failures.setdefault(batch_index, []).append(_as_failure(exc, times, label))

    def fail_next(self, exc: ExcSpec, times: int | None = 1) -> None:
        """Raise ``exc`` on the next ``times`` requests of any kind."""
        self._next_failures.append(_as_failure(exc, times, "fail_next"))

    def rate_limit_next(self, retry_after: float | None = 60.0, times: int | None = 1) -> None:
        """Answer the next ``times`` requests with ``RateLimited(retry_after)``."""
        self._next_failures.append(
            _Failure(lambda: RateLimited(retry_after), times, "rate_limit_next")
        )

    def set_status(self, sub: str, status: str, path: str | None = None) -> None:
        """Make every request touching ``sub`` raise the matching subreddit error.

        ``status`` is one of ``STATUSES``; ``'ok'`` clears. Unknown subreddits are created.
        """
        if status not in STATUSES:
            msg = f"unknown status {status!r}; expected one of {STATUSES}"
            raise ValueError(msg)
        row = self._sub_row(sub)
        row.status = status
        row.redirect_path = path
        if status == "ok":
            row.info_returns = True

    def set_html_403(self, times: int | None = 1) -> None:
        """Answer the next ``times`` requests with ``HtmlBlocked`` (a Cloudflare page).

        ``times=None`` is forever; ``times <= 0`` clears.
        """
        if times is not None and times <= 0:
            self._html_403 = None
        else:
            self._html_403 = _as_failure(HtmlBlocked, times, "set_html_403")

    def set_auth_failed(self, times: int | None = None) -> None:
        """Every request (``times=None``) or the next ``times`` raise ``AuthFailed``."""
        self._next_failures.append(_as_failure(AuthFailed, times, "set_auth_failed"))

    def crash_after(self, kind: str, n: int) -> None:
        """Raise ``CrashInjected`` when operation ``n+1`` of ``kind`` begins.

        ``kind`` is one of ``CRASH_KINDS``; one-shot (see the module docstring).
        """
        self._check_kind(kind)
        self._crash[kind] = n
        self._completed[kind] = 0

    def block_on(
        self, kind: str, n: int, event: threading.Event, *, timeout: float | None = 30.0
    ) -> None:
        """Park the ``n``-th operation of ``kind`` until ``event`` is set (SIGTERM tests).

        Raises ``TimeoutError`` if the event is not set within ``timeout`` seconds.
        """
        self._check_kind(kind)
        self._blocks.setdefault(kind, []).append(_Block(n, event, timeout))

    def on_call(self, kind: str, n: int, callback: Callable[[], None]) -> None:
        """Run ``callback`` when the ``n``-th operation of ``kind`` begins (to advance a clock)."""
        self._check_kind(kind)
        self._hooks.setdefault(kind, []).append(_Hook(n, callback))

    # ------------------------------------------------------------------ recording

    def count(self, method: str) -> int:
        """Number of recorded calls of ``method``."""
        return sum(1 for c in self.calls if c.method == method)

    def fullnames_requested(self, method: str) -> list[str]:
        """Items asked of ``method``: flattened fullnames for ``info``, ``t3_`` ids for
        ``fetch_tree``, the first argument for everything else."""
        out: list[str] = []
        for call in self.calls:
            if call.method != method:
                continue
            if method == "info":
                out.extend(str(fn) for fn in call.args[0])
            elif method == "fetch_tree":
                out.append(f"t3_{_bare(str(call.args[0]))}")
            elif call.args:
                out.append(str(call.args[0]))
        return out

    def assert_no_unconsumed_injections(self) -> None:
        """Fail when a planted failure, crash, block or hook was never reached (panel rule 4)."""
        pending: list[str] = []
        pending += [f.label for f in self._next_failures if f.unconsumed]
        if self._html_403 is not None and self._html_403.unconsumed:
            pending.append(self._html_403.label)
        for queue in self._page_failures.values():
            pending += [f.label for f in queue if f.unconsumed]
        for failure, _ in self._tree_failures.values():
            if failure.unconsumed:
                pending.append(failure.label)
        for queue in self._info_failures.values():
            pending += [f.label for f in queue if f.unconsumed]
        pending += [f"crash_after({kind!r}, {n})" for kind, n in self._crash.items()]
        for kind, blocks in self._blocks.items():
            pending += [f"block_on({kind!r}, {b.n})" for b in blocks if not b.fired]
        for kind, hooks in self._hooks.items():
            pending += [f"on_call({kind!r}, {h.n})" for h in hooks if not h.fired]
        if pending:
            msg = "unconsumed failure injections: " + ", ".join(pending)
            raise AssertionError(msg)

    # --------------------------------------------------------------------- gateway

    @property
    def requests_made(self) -> int:
        return self._requests_made

    def about(self, name: str) -> RawItem:
        self._record("about", (name,), {})
        self._begin("about")
        self._request(f"GET /r/{name}/about")
        sub = self._sub_for(name)
        self._check_status(sub)
        self._done("about")
        return self._emit("subreddit", self._sub_dict(sub))

    def iter_new_pages(
        self, name: str, *, max_pages: int, after: str | None = None
    ) -> Iterator[Page]:
        idx = self._record("iter_new_pages", (name,), {"max_pages": max_pages, "after": after})
        return self._iter_listing(name, max_pages=max_pages, after=after, call_index=idx)

    def new_head(self, name: str) -> RawItem | None:
        self._record("new_head", (name,), {})
        self._begin("new_head")
        self._request(f"GET /r/{name}/new?limit={NEW_HEAD_LIMIT}")
        sub = self._sub_for(name)
        self._check_status(sub)
        self._done("new_head")
        if sub.anchor_fullname is not None:
            return self._emit("post", self._posts[sub.anchor_fullname[3:]])
        if sub.anchor_created_utc is not None:
            return self._anchor_post(sub, sub.anchor_created_utc)
        listed = [pid for pid in self._sorted_post_ids(sub) if self._listed(f"t3_{pid}")]
        for pid in listed[:NEW_HEAD_LIMIT]:
            post = self._posts[pid]
            if not post.get("stickied", False):
                return self._emit("post", post)
        return None

    def fetch_tree(self, post_id: str, *, more_limit: int) -> TreeResult:
        self._record("fetch_tree", (post_id,), {"more_limit": more_limit})
        pid = _bare(post_id)
        self._begin("tree")
        self._request(f"GET /comments/{pid}")
        post = self._posts.get(pid)
        if post is None or f"t3_{pid}" in self._vanished:
            msg = f"no such post {post_id!r}"
            raise GatewayError(msg)
        pending, after_n = self._take_tree_failure(pid)
        if pending is not None and not after_n:
            raise pending
        tree = self._tree_index(pid)
        expansions = self._expand_tree(tree, more_limit, pending, after_n)
        comments: list[RawItem] = []
        for cid, depth in tree.visible():
            fn = f"t1_{cid}"
            if fn in self._dropped or fn in self._vanished:
                continue
            if self._state.get(fn) == "deleted" and not tree.children_of.get(fn):
                continue  # Reddit drops deleted leaf comments from trees
            item = self._emit("comment", self._comments[cid])
            item["depth"] = depth
            comments.append(item)
        more = [MoreStub(s.parent_fullname, s.count, list(s.children)) for s in tree.reachable()]
        self._done("tree")
        return TreeResult(
            post=self._emit("post", post),
            comments=comments,
            more=more,
            requests_used=1 + expansions,
            complete=not more,
        )

    def info(self, fullnames: Sequence[str]) -> list[RawItem]:
        names = list(dict.fromkeys(fullnames))
        self._record("info", (list(fullnames),), {})
        self._begin("info")
        found: list[RawItem] = []
        for batch, start in enumerate(range(0, len(names), INFO_CHUNK)):
            chunk = names[start : start + INFO_CHUNK]
            self._request(f"GET /api/info?id={','.join(chunk)}")
            exc = _pop_failure(self._info_failures.get(batch, []))
            if exc is not None:
                raise exc
            hits: list[RawItem] = []
            for fn in chunk:
                item = self._lookup(fn)
                if item is None or self._consume_vanish(fn):
                    continue
                item = self._emit(self._kind_of(fn), item)
                item.pop("depth", None)
                hits.append(item)
            hits.sort(key=lambda d: self._seq.get(d["name"], 0))
            if self._info_shuffle:
                self._info_rng.shuffle(hits)
            found.extend(hits)
        self._done("info")
        return found

    def search(
        self, query: str, *, sort: str, time_filter: str, max_pages: int = 3
    ) -> Iterator[Page]:
        idx = self._record(
            "search",
            (query,),
            {"sort": sort, "time_filter": time_filter, "max_pages": max_pages},
        )
        if time_filter not in SEARCH_WINDOWS:
            msg = f"unknown time_filter {time_filter!r}"
            raise ValueError(msg)
        return self._iter_search(
            query, sort=sort, time_filter=time_filter, max_pages=max_pages, call_index=idx
        )

    def limits(self) -> Limits:
        self._record("limits", (), {})
        if self._limits_override is not None:
            return self._limits_override
        if self._requests_made == 0:
            return Limits(remaining=None, used=None)
        return Limits(remaining=max(0, RATE_WINDOW - self._requests_made), used=self._requests_made)

    # ------------------------------------------------------------------- internals

    def _iter_listing(
        self, name: str, *, max_pages: int, after: str | None, call_index: int
    ) -> Iterator[Page]:
        key = name.lower()
        cursor = after
        pages = 0
        while pages < max_pages:
            self._current_call = call_index
            self._begin("page")
            suffix = f"&after={cursor}" if cursor else ""
            self._request(f"GET /r/{name}/new?limit={PAGE_SIZE}{suffix}")
            sub = self._sub_for(name)
            self._check_status(sub)
            ids = self._underlying(sub)
            start = self._start_index(sub, ids, cursor)
            page_no = 1
            if cursor is not None:
                page_no = self._cursor_pages.get((key, cursor), start // PAGE_SIZE + 1)
            exc = _pop_failure(self._page_failures.get((key, page_no), []))
            if exc is not None:
                raise exc
            size = PAGE_SIZE
            if page_no - 1 < len(sub.page_sizes):
                size = sub.page_sizes[page_no - 1]
            chunk = ids[start : start + size]
            end = start + len(chunk)
            exhausted = end >= len(ids)
            items = [
                self._emit("post", self._posts[pid]) for pid in chunk if self._listed(f"t3_{pid}")
            ]
            next_cursor = None if exhausted else f"t3_{chunk[-1]}"
            if next_cursor is not None:
                self._cursor_pages[(key, next_cursor)] = page_no + 1
            pages += 1
            self._done("page")
            yield Page(items=items, after=next_cursor, complete=exhausted)
            if exhausted:
                return
            cursor = next_cursor

    def _start_index(self, sub: _Sub, ids: list[str], cursor: str | None) -> int:
        if cursor is None:
            return 0
        cid = _bare(cursor)
        overlap = sub.overlap or self._overlap_all
        if cid in ids:
            return max(0, ids.index(cid) + 1 - overlap)
        post = self._posts.get(cid)
        if post is None or self._post_sub.get(cid) != sub.key:
            msg = f"unknown cursor {cursor!r} for r/{sub.display_name}"
            raise GatewayError(msg)
        cursor_key = self._order_key(cid)
        return sum(1 for pid in ids if self._order_key(pid) < cursor_key)

    def _iter_search(
        self, query: str, *, sort: str, time_filter: str, max_pages: int, call_index: int
    ) -> Iterator[Page]:
        terms = query.lower().split()
        window = SEARCH_WINDOWS[time_filter]
        cutoff = None
        if window is not None and self._clock is not None:
            cutoff = self._clock.now() - window
        matches: list[str] = []
        for pid, post in self._posts.items():
            if not self._listed(f"t3_{pid}"):
                continue
            if cutoff is not None and post["created_utc"] < cutoff:
                continue
            haystack = f"{post.get('title', '')} {post.get('selftext', '')}".lower()
            if all(term in haystack for term in terms):
                matches.append(pid)
        if sort == "new":
            matches.sort(key=self._order_key)
        else:
            matches.sort(key=lambda pid: (-self._posts[pid].get("score", 0), self._order_key(pid)))
        matches = matches[:SEARCH_CAP]
        start = 0
        pages = 0
        while pages < max_pages:
            self._current_call = call_index
            self._begin("search")
            self._request(f"GET /r/all/search?q={query}&sort={sort}&t={time_filter}&start={start}")
            chunk = matches[start : start + PAGE_SIZE]
            end = start + len(chunk)
            exhausted = end >= len(matches)
            items = [self._emit("post", self._posts[pid]) for pid in chunk]
            pages += 1
            self._done("search")
            yield Page(
                items=items,
                after=None if exhausted else f"t3_{chunk[-1]}",
                complete=exhausted,
            )
            if exhausted:
                return
            start = end

    def _record(self, method: str, args: tuple[Any, ...], kwargs: dict[str, Any]) -> int:
        index = len(self.calls)
        self.calls.append(Call(method, args, kwargs, 0, index + 1))
        self._current_call = index
        return index

    def _request(self, label: str) -> None:
        """One simulated HTTP round-trip: count it, then apply global failure injections."""
        self._begin("request")
        self._requests_made += 1
        self.requests.append(label)
        if self._current_call is not None:
            call = self.calls[self._current_call]
            self.calls[self._current_call] = call._replace(cost=call.cost + 1)
        if self._html_403 is not None:
            exc = self._html_403.take()
            if exc is not None:
                raise exc
            self._html_403 = None
        exc = _pop_failure(self._next_failures)
        if exc is not None:
            raise exc
        self._done("request")

    def _begin(self, kind: str) -> None:
        n = self._crash.get(kind)
        if n is not None and self._completed.get(kind, 0) >= n:
            del self._crash[kind]
            msg = f"crash injected after {n} {kind} operation(s)"
            raise CrashInjected(msg)
        started = self._started.get(kind, 0) + 1
        self._started[kind] = started
        for hook in self._hooks.get(kind, []):
            if hook.n == started and not hook.fired:
                hook.fired = True
                hook.callback()
        for block in self._blocks.get(kind, []):
            if block.n == started and not block.fired:
                block.fired = True
                if not block.event.wait(block.timeout):
                    msg = f"block_on({kind!r}, {block.n}) waited {block.timeout}s"
                    raise TimeoutError(msg)

    def _done(self, kind: str) -> None:
        self._completed[kind] = self._completed.get(kind, 0) + 1

    def _take_tree_failure(self, pid: str) -> tuple[BaseException | None, int | None]:
        entry = self._tree_failures.get(pid)
        if entry is None:
            return None, None
        failure, after_n = entry
        exc = failure.take()
        if exc is None:
            del self._tree_failures[pid]
            return None, None
        return exc, after_n

    def _tree_index(self, pid: str) -> _Tree:
        link = f"t3_{pid}"
        children_of: dict[str, list[str]] = {}
        for cid, comment in self._comments.items():
            if comment["link_id"] == link:
                children_of.setdefault(comment["parent_id"], []).append(cid)
        stubs = list(self._more.get(pid, []))
        tree = _Tree(link, children_of, stubs)
        if self._tree_clamp is None:
            return tree
        shown = tree.visible()
        kept = {link} | {f"t1_{cid}" for cid, _ in shown[: self._tree_clamp]}
        by_parent: dict[str, list[str]] = {}
        for cid, _ in shown[self._tree_clamp :]:
            parent = self._comments[cid]["parent_id"]
            if parent in kept:
                by_parent.setdefault(parent, []).append(cid)
        for parent, children in by_parent.items():
            count = sum(tree.subtree_size(cid) for cid in children)
            stubs.append(_More(parent, count, children))
        return _Tree(link, children_of, stubs)

    def _expand_tree(
        self, tree: _Tree, more_limit: int, pending: BaseException | None, after_n: int | None
    ) -> int:
        """Expand stubs one request each; raise ``pending`` once ``after_n`` comments are visible.

        Returns the number of expansions performed.
        """
        expansions = 0
        while True:
            if pending is not None and after_n is not None and len(tree.visible()) >= after_n:
                raise pending
            stub = tree.next_stub() if expansions < more_limit else None
            if stub is None:
                break
            self._request(
                f"GET /api/morechildren?link_id={tree.link}&parent={stub.parent_fullname}"
            )
            expansions += 1
            tree.expand(stub)
        if pending is not None:
            raise pending
        return expansions

    def _emit(self, kind: str, item: RawItem) -> RawItem:
        """A deep copy of ``item`` with the ``set_raw_shape`` transform for ``kind`` applied."""
        out = copy.deepcopy(item)
        transform = self._shapes.get(kind)
        return transform(out) if transform is not None else out

    @staticmethod
    def _kind_of(fullname: str) -> str:
        return {"t3_": "post", "t1_": "comment", "t5_": "subreddit"}.get(fullname[:3], "post")

    @staticmethod
    def _check_kind(kind: str) -> None:
        if kind not in CRASH_KINDS:
            msg = f"unknown operation kind {kind!r}; expected one of {CRASH_KINDS}"
            raise ValueError(msg)

    def _created(self, created_utc: float | None) -> float:
        if created_utc is not None:
            return float(created_utc)
        if self._clock is None:
            msg = "created_utc is required when the fake has no clock"
            raise ValueError(msg)
        return float(self._clock.now())

    def _sub_for(self, name: str) -> _Sub:
        sub = self._subs.get(name.lower())
        if sub is None:
            path = f"/subreddits/search?q={name}"
            raise SubredditRedirected(path)
        return sub

    def _sub_row(self, sub: str) -> _Sub:
        """The subreddit row, created on the fly for builder calls."""
        key = sub.lower()
        if key not in self._subs:
            self.add_subreddit(sub)
        return self._subs[key]

    def _sub_rows(self, sub: str | None) -> list[_Sub]:
        if sub is None:
            return list(self._subs.values())
        return [self._sub_for(sub)]

    @staticmethod
    def _check_status(sub: _Sub) -> None:
        name = f"r/{sub.display_name}"
        if sub.status == "forbidden":
            msg = f"{name} is private"
            raise SubredditForbidden(msg)
        if sub.status == "not_found":
            msg = f"{name} is banned"
            raise SubredditNotFound(msg)
        if sub.status == "redirect":
            path = sub.redirect_path or f"/subreddits/search?q={sub.display_name}"
            raise SubredditRedirected(path)
        if sub.status == "quarantined":
            msg = f"{name} is quarantined"
            raise SubredditQuarantined(msg)

    def _sub_dict(self, sub: _Sub) -> RawItem:
        about: RawItem = {
            "id": sub.fullname[3:],
            "name": sub.fullname,
            "display_name": sub.display_name,
            "display_name_prefixed": f"r/{sub.display_name}",
            "title": sub.display_name,
            "public_description": "",
            "description": "",
            "subscribers": sub.subscribers,
            "subreddit_type": sub.subreddit_type,
            "over18": sub.over18,
            "quarantine": sub.status == "quarantined",
            "url": f"/r/{sub.display_name}/",
            "created_utc": 1_400_000_000.0,
            "lang": "en",
        }
        about.update(sub.about_extra)
        return about

    @staticmethod
    def _anchor_post(sub: _Sub, created_utc: float) -> RawItem:
        return {
            "id": "anchor",
            "name": "t3_anchor",
            "title": "live anchor",
            "selftext": "",
            "author": "anchor",
            "created_utc": created_utc,
            "created": created_utc,
            "is_self": True,
            "stickied": False,
            "subreddit": sub.display_name,
            "subreddit_id": sub.fullname,
            "num_comments": 0,
            "removed_by_category": None,
        }

    def _insert_post(self, post: RawItem, *, hidden: bool = False) -> None:
        pid = str(post["id"])
        fn = f"t3_{pid}"
        if pid in self._posts or pid in self._comments:
            msg = f"duplicate id {pid!r}"
            raise ValueError(msg)
        post.setdefault("name", fn)
        sub_name = str(post["subreddit"])
        key = sub_name.lower()
        if key not in self._subs:
            self.add_subreddit(sub_name, t5=post.get("subreddit_id"))
        post.setdefault("subreddit_id", self._subs[key].fullname)
        post.setdefault("created_utc", 0.0)
        post.setdefault("num_comments", 0)
        self._posts[pid] = post
        self._post_sub[pid] = key
        self._seq[fn] = self._next_seq()
        category = post.get("removed_by_category")
        if category == "deleted" or post.get("selftext") == "[deleted]":
            self._state[fn] = "deleted"
        elif category is not None or post.get("selftext") == "[removed]":
            self._state[fn] = "removed"
            self.removals[fn] = str(category or "moderator")
        else:
            self._state[fn] = "hidden" if hidden else "live"

    def _insert_comment(self, comment: RawItem) -> None:
        cid = str(comment["id"])
        fn = f"t1_{cid}"
        if cid in self._comments or cid in self._posts:
            msg = f"duplicate id {cid!r}"
            raise ValueError(msg)
        comment.setdefault("name", fn)
        comment.pop("depth", None)
        pid = _bare(str(comment["link_id"]))
        post = self._posts.get(pid)
        if post is None:
            msg = f"comment {cid!r} belongs to unknown post {pid!r}"
            raise KeyError(msg)
        comment.setdefault("subreddit", post["subreddit"])
        comment.setdefault("subreddit_id", post["subreddit_id"])
        comment.setdefault("created_utc", 0.0)
        self._comments[cid] = comment
        self._seq[fn] = self._next_seq()
        body = comment.get("body")
        if body == "[deleted]":
            self._state[fn] = "deleted"
        elif body == "[removed]":
            self._state[fn] = "removed"
            self.removals[fn] = "moderator"
        else:
            self._state[fn] = "live"

    @staticmethod
    def _parent_fullname(pid: str, parent: str | None) -> str:
        if parent is None:
            return f"t3_{pid}"
        if parent.startswith(("t1_", "t3_")):
            return parent
        return f"t1_{parent}"

    def _resolve(self, fullname: str) -> tuple[str, RawItem]:
        """Accept a fullname or a bare id; return ``(fullname, stored item)``."""
        if fullname.startswith("t3_"):
            post = self._posts.get(fullname[3:])
            if post is not None:
                return fullname, post
        elif fullname.startswith("t1_"):
            comment = self._comments.get(fullname[3:])
            if comment is not None:
                return fullname, comment
        else:
            if fullname in self._posts:
                return f"t3_{fullname}", self._posts[fullname]
            if fullname in self._comments:
                return f"t1_{fullname}", self._comments[fullname]
        msg = f"unknown item {fullname!r}"
        raise KeyError(msg)

    def _store(self, fn: str) -> RawItem:
        return self._posts[fn[3:]] if fn.startswith("t3_") else self._comments[fn[3:]]

    def _lookup(self, fn: str) -> RawItem | None:
        """The stored object for a fullname, or None when Reddit would not return it."""
        if fn.startswith("t3_"):
            post = self._posts.get(fn[3:])
            if post is None or not self._subs[self._post_sub[fn[3:]]].info_returns:
                return None
            return post
        if fn.startswith("t1_"):
            comment = self._comments.get(fn[3:])
            if comment is None:
                return None
            sub_key = self._post_sub[_bare(str(comment["link_id"]))]
            return comment if self._subs[sub_key].info_returns else None
        if fn.startswith("t5_"):
            for sub in self._subs.values():
                if sub.fullname == fn:
                    return self._sub_dict(sub)
        return None

    def _all_items(self) -> list[tuple[str, RawItem]]:
        posts = [(f"t3_{pid}", p) for pid, p in self._posts.items()]
        comments = [(f"t1_{cid}", c) for cid, c in self._comments.items()]
        return posts + comments

    def _remember(self, fn: str) -> None:
        if fn not in self._originals:
            self._originals[fn] = copy.deepcopy(self._store(fn))

    def _listed(self, fn: str) -> bool:
        """Present in listings, ``new_head`` and search."""
        return self._state.get(fn, "live") == "live" and fn not in self._vanished

    def _consume_vanish(self, fn: str) -> bool:
        if fn not in self._vanished:
            return False
        remaining = self._vanished[fn]
        if remaining is None:
            return True
        remaining -= 1
        if remaining <= 0:
            del self._vanished[fn]
        else:
            self._vanished[fn] = remaining
        return True

    def _order_key(self, pid: str) -> tuple[float, int]:
        return (-float(self._posts[pid]["created_utc"]), -self._seq[f"t3_{pid}"])

    def _sorted_post_ids(self, sub: _Sub) -> list[str]:
        ids = [pid for pid, key in self._post_sub.items() if key == sub.key]
        ids.sort(key=self._order_key)
        if sub.sticky_first:
            ids.sort(key=lambda pid: not self._posts[pid].get("stickied", False))
        return ids[:LISTING_CAP]

    def _underlying(self, sub: _Sub) -> list[str]:
        if sub.frozen is not None:
            return sub.frozen
        return self._sorted_post_ids(sub)

    def _next_seq(self) -> int:
        self._counter += 1
        return self._counter

    def _next_id(self) -> str:
        self._id_counter += 1
        return _base36(self._id_counter)


__all__ = [
    "CRASH_KINDS",
    "INFO_CHUNK",
    "LISTING_CAP",
    "NEW_HEAD_LIMIT",
    "PAGE_SIZE",
    "SEARCH_CAP",
    "SHAPE_KINDS",
    "STATUSES",
    "Call",
    "CrashInjected",
    "FakeRedditGateway",
]
