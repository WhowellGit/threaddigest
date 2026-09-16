"""``FakeRedditGateway``: the composed class, its fixtures, and the last gateway calls.

The scenario builders, the content-state transitions, the listings and the trees each
live in their own module and are layered here onto the one store in ``world.py``. What
is left is the fixture round trip and the three gateway calls that belong to no other
group: ``about``, ``info`` and ``limits``.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Sequence
from pathlib import Path

from threaddigest.adapters.reddit_fake.builders import _Builders
from threaddigest.adapters.reddit_fake.content_state import _ContentState
from threaddigest.adapters.reddit_fake.listings import _Listings
from threaddigest.adapters.reddit_fake.records import (
    INFO_CHUNK,
    RATE_WINDOW,
    _pop_failure,
    _sub_dict,
)
from threaddigest.adapters.reddit_fake.trees import _Trees
from threaddigest.ports import Limits, RawItem


class FakeRedditGateway(_Builders, _ContentState, _Listings, _Trees):
    """Scenario-building in-memory Reddit. See the package docstring for the rules it follows."""

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

    # ------------------------------------------------------------------- gateway

    def about(self, name: str) -> RawItem:
        self._record("about", (name,), {})
        self._begin("about")
        self._request(f"GET /r/{name}/about")
        sub = self._sub_for(name)
        self._check_status(sub)
        self._done("about")
        return self._emit("subreddit", _sub_dict(sub))

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

    def limits(self) -> Limits:
        self._record("limits", (), {})
        if self._limits_override is not None:
            return self._limits_override
        if self._requests_made == 0:
            return Limits(remaining=None, used=None)
        return Limits(remaining=max(0, RATE_WINDOW - self._requests_made), used=self._requests_made)
