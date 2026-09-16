"""``/new`` paging, the freshness anchor (cut from the product, N-08; the fake keeps the
listing-side seam) and search: the listing side of the gateway.

The setters at the top shape what a listing does (page lengths, overlap, sticky order,
a frozen snapshot, the live anchor); the iterators below cut the underlying set into
pages and then filter it, so a page can be short with a non-None ``after`` exactly as
Reddit's is.
"""

from __future__ import annotations

import random
from collections.abc import Iterator, Sequence

from threaddigest.adapters.reddit_fake.recording import _Requests
from threaddigest.adapters.reddit_fake.records import (
    NEW_HEAD_LIMIT,
    PAGE_SIZE,
    SEARCH_CAP,
    SEARCH_WINDOWS,
    _anchor_post,
    _bare,
    _pop_failure,
    _Sub,
)
from threaddigest.ports import GatewayError, Limits, Page, RawItem


class _Listings(_Requests):
    """What ``iter_new_pages``, ``new_head`` and ``search`` return, and how to bend it."""

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

    # --------------------------------------------------------------------- listing

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
            return _anchor_post(sub, sub.anchor_created_utc)
        listed = [pid for pid in self._sorted_post_ids(sub) if self._listed(f"t3_{pid}")]
        for pid in listed[:NEW_HEAD_LIMIT]:
            post = self._posts[pid]
            if not post.get("stickied", False):
                return self._emit("post", post)
        return None

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

    # ---------------------------------------------------------------------- search

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
