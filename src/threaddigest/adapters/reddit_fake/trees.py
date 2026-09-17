"""Comment trees: visibility bookkeeping, ``more`` expansion, and ``fetch_tree``.

``_Tree`` answers which comments are visible and which stub PRAW would reach for next;
``_Trees`` turns that into one base request plus one request per expansion, honouring
the ``?limit`` clamp, the ``more_limit`` budget and a mid-tree failure.
"""

from __future__ import annotations

from threaddigest.adapters.reddit_fake.recording import _Requests
from threaddigest.adapters.reddit_fake.records import _bare, _More
from threaddigest.ports import GatewayError, MoreStub, RawItem, TreeResult

#: Reddit's ``/api/morechildren`` reveals at most this many new comment instances per request
#: (KI-023, external round one, 2026-09-14). A stub with more behind it takes several requests,
#: each leaving the remainder as a fresh stub, so a budget or completeness test cannot pass
#: against a tree the real adapter could not fetch that cheaply.
MORE_CHUNK = 100


class _Tree:
    """Visibility bookkeeping for one ``fetch_tree`` call."""

    def __init__(self, link: str, children_of: dict[str, list[str]], stubs: list[_More]) -> None:
        self.link = link
        self.children_of = children_of
        self.stubs = stubs
        self.hidden: set[str] = {c for stub in stubs for c in stub.children}
        self.expanded: list[_More] = []
        self.redelivered: list[str] = []

    def delivered(self) -> list[tuple[str, int]]:
        """Every ``(comment id, depth)`` this fetch handed over, duplicates included.

        ``visible()`` is a walk of an index and so cannot repeat itself; Reddit can. An
        expansion built with ``add_more(..., redelivers=...)`` returns a comment the base
        fetch already delivered, and this is where that duplicate enters the stream, so the
        de-duplication in :meth:`_Trees.fetch_tree` is exercised rather than merely true by
        construction (KI-042, the fidelity gap panel finding C-5 named).
        """
        shown = self.visible()
        depths = dict(shown)
        return shown + [(cid, depths[cid]) for cid in self.redelivered if cid in depths]

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

    def expand(self, stub: _More, *, limit: int = MORE_CHUNK) -> _More | None:
        """Reveal up to ``limit`` new comment instances from ``stub``, its direct children in
        order (each child's whole subtree counts toward the limit, as Reddit counts revealed
        instances). If children remain hidden, a replacement stub for them is added and
        returned, so the next request continues where this one stopped (KI-023).

        **Known fidelity limit (external round one panel, 2026-09-15).** Chunking is at
        direct-child granularity, so a *single* child whose own subtree exceeds ``limit`` is
        still revealed whole in one request -- the fake cannot partially reveal a cascading
        subtree, because un-hiding a comment makes its already-un-hidden descendants visible.
        A real ``morechildren`` would need several requests for that child. This matters only
        for a comment with a very large reply thread and is pinned by
        ``test_a_single_more_child_with_a_large_subtree_is_revealed_whole`` so it is a documented
        gap, not a silent one; the real chunking is validated on the probe day before M1b.
        """
        self.expanded.append(stub)
        self.redelivered.extend(stub.redelivers)
        revealed = 0
        leftover: list[str] = []
        for cid in stub.children:
            if leftover:  # once stopped, everything after stays hidden, in order
                leftover.append(cid)
                continue
            size = self.subtree_size(cid)
            if revealed and revealed + size > limit:
                leftover.append(cid)
                continue
            self.hidden.discard(cid)
            revealed += size
        if not leftover:
            return None
        replacement = _More(
            stub.parent_fullname,
            sum(self.subtree_size(cid) for cid in leftover),
            leftover,
        )
        self.stubs.append(replacement)
        return replacement

    def subtree_size(self, cid: str) -> int:
        total = 1
        for reply in self.children_of.get(f"t1_{cid}", []):
            total += self.subtree_size(reply)
        return total


class _Trees(_Requests):
    """``fetch_tree`` and the indexing and expansion it rests on."""

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
        comments = self._comments_of(tree)
        more = [MoreStub(s.parent_fullname, s.count, list(s.children)) for s in tree.reachable()]
        self._done("tree")
        return TreeResult(
            post=self._emit("post", post),
            comments=comments,
            more=more,
            requests_used=1 + expansions,
            complete=not more,
        )

    def _comments_of(self, tree: _Tree) -> list[RawItem]:
        """The delivered stream as the port sees it: each comment once, in depth-first order.

        A comment Reddit delivered twice (``add_more(..., redelivers=...)``) is emitted on its
        first appearance and skipped afterwards, which is the promise ``TreeResult.comments``
        makes and the one the real adapter broke until KI-042.
        """
        comments: list[RawItem] = []
        seen: set[str] = set()
        for cid, depth in tree.delivered():
            fn = f"t1_{cid}"
            if cid in seen or fn in self._dropped or fn in self._vanished:
                continue
            seen.add(cid)
            if self._state.get(fn) == "deleted" and not tree.children_of.get(fn):
                continue  # Reddit drops deleted leaf comments from trees
            item = self._emit("comment", self._comments[cid])
            item["depth"] = depth
            comments.append(item)
        return comments

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
