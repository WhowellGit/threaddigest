"""The one in-memory world every path of the fake reads and writes.

``_World`` owns the state (subreddit rows, posts, comments, ``more`` stubs, content
state, the counters, and the armed-failure queues the request path consumes) together
with the store internals that read and write it: insert, resolve, look up, emit, and
the subreddit-row helpers. Every mixin in this package derives from it, so each of
them can be about one concern and still share one store.
"""

from __future__ import annotations

import copy
import random

from insightminer.adapters.reddit_fake.records import (
    LISTING_CAP,
    Call,
    Transform,
    _base36,
    _Block,
    _Failure,
    _Hook,
    _More,
    _Sub,
)
from insightminer.ports import (
    Clock,
    Limits,
    RawItem,
    SubredditForbidden,
    SubredditNotFound,
    SubredditQuarantined,
    SubredditRedirected,
)


class _World:
    """The store: state plus the internals that read and write it."""

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

    # ------------------------------------------------------------------ subreddits

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

    def _order_key(self, pid: str) -> tuple[float, int]:
        return (-float(self._posts[pid]["created_utc"]), -self._seq[f"t3_{pid}"])

    # ---------------------------------------------------------- posts and comments

    def _emit(self, kind: str, item: RawItem) -> RawItem:
        """A deep copy of ``item`` with the ``set_raw_shape`` transform for ``kind`` applied."""
        out = copy.deepcopy(item)
        transform = self._shapes.get(kind)
        return transform(out) if transform is not None else out

    @staticmethod
    def _kind_of(fullname: str) -> str:
        return {"t3_": "post", "t1_": "comment", "t5_": "subreddit"}.get(fullname[:3], "post")

    def _created(self, created_utc: float | None) -> float:
        if created_utc is not None:
            return float(created_utc)
        if self._clock is None:
            msg = "created_utc is required when the fake has no clock"
            raise ValueError(msg)
        return float(self._clock.now())

    def _next_seq(self) -> int:
        self._counter += 1
        return self._counter

    def _next_id(self) -> str:
        self._id_counter += 1
        return _base36(self._id_counter)
