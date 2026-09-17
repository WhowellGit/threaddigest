"""The scenario builders that put posts, comments and ``more`` stubs into the world.

Each ``add_*`` returns the fullname Reddit would report and writes a payload in wire
shape; ``set_field`` / ``remove_field`` / ``set_raw_shape`` / ``edit`` bend that shape
for the tests that need an odd one.
"""

from __future__ import annotations

import copy
import re
from collections.abc import Sequence
from typing import Any
from urllib.parse import urlsplit

from threaddigest.adapters.reddit_fake.items import _Items
from threaddigest.adapters.reddit_fake.records import (
    SHAPE_KINDS,
    Transform,
    _author_fullname,
    _bare,
    _html,
    _More,
)
from threaddigest.ports import RawItem


class _Builders(_Items):
    """``add_post`` and friends: everything that builds or bends a stored payload."""

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
        self,
        post: str,
        parent: str | None,
        count: int,
        children: Sequence[str] = (),
        redelivers: Sequence[str] = (),
    ) -> None:
        """Hide ``children`` (comment ids) behind a ``more`` stub under ``parent``.

        ``parent`` is a comment id or fullname; None means the post itself. ``count == 0``
        is a "continue this thread" node. Expanding the stub reveals ``children`` and costs
        one request.

        ``redelivers`` names comments the expansion returns *again* although they are already
        visible -- the shape ``morechildren`` produces when it is asked with
        ``limit_children=0``, which is how the real adapter asks. They are not hidden, so they
        reveal nothing; what they exercise is the promise both gateways make, that
        ``TreeResult.comments`` holds each comment once however often Reddit sends it (KI-042).
        """
        pid = _bare(post)
        if pid not in self._posts:
            msg = f"unknown post {post!r}"
            raise KeyError(msg)
        stub = _More(
            parent_fullname=self._parent_fullname(pid, parent),
            count=count,
            children=[_bare(c) for c in children],
            redelivers=[_bare(c) for c in redelivers],
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
