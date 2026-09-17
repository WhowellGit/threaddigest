"""Deletion, removal, restoration and disappearance: the content-state transitions.

One mutation here shows on every path at once (listing, tree, ``info()``, search),
because they all read the same store. ``vanish`` and ``drop_from_tree`` are the two
exceptions that hide an item from some paths only, as Reddit does.
"""

from __future__ import annotations

import copy

from threaddigest.adapters.reddit_fake.items import _Items


class _ContentState(_Items):
    """``delete`` / ``remove`` / ``restore`` and the other state transitions."""

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
        """Listing and about raise ``SubredditNotFound``; ``info()`` on its items per flag."""
        row = self._sub_row(sub)
        row.status = "not_found"
        row.info_returns = info_returns
