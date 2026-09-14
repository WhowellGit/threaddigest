"""Posts and comments: putting them into the world, finding them, reading them back.

``_Items`` is the half of the store that deals with individual items rather than with
subreddit rows: the two inserters that derive a payload's content state from its wire
markers, the resolver that accepts a fullname or a bare id, and the reads every other
path goes through (``_lookup`` for ``info()``, ``_listed`` for listings and search,
``_remember`` so ``restore`` has something to put back).
"""

from __future__ import annotations

import copy

from insightminer.adapters.reddit_fake.records import _bare, _sub_dict
from insightminer.adapters.reddit_fake.world import _World
from insightminer.ports import RawItem


class _Items(_World):
    """Inserting, resolving and reading the posts and comments of one world."""

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
                    return _sub_dict(sub)
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
