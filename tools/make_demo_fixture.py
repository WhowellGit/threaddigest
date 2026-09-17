#!/usr/bin/env python3
"""Build the demo corpus that the end-to-end suite and ``make run`` collect from.

The corpus is **generated, never committed**. It used to live in git as
``tests/fixtures/json/demo.json`` (13,586 lines, 416 KB): a file no reviewer reads, that
every branch re-diffs, and whose contents nothing explained. This script is its only
producer. ``make fixture`` writes it to ``data/demo.json`` (``data/`` is git-ignored) for
``make run``; ``tests/conftest.py`` builds it once per pytest session into a temp
directory. The two callers share this module, so there is one definition of "the demo
corpus" rather than one per consumer.

Determinism is structural, not statistical: nothing here draws from ``random``, and the
one seed the corpus has is :data:`BASE_UTC`. Every id, timestamp, author and body is a
pure function of the constants below and of the order the builder calls run in, so two
runs produce identical bytes -- which ``tests/tools/test_make_demo_fixture.py`` pins by
running this script twice and comparing them.

The corpus, in the order it is built (ids are allocated in that order by the fake):

============  =====================================================================
premiere      one stickied rules post an hour before the block; 98 ordinary posts;
              a poll (``post_hint`` the collector does not know) between ordinary
              posts 89 and 90; one themed post whose text a ``config/seed.yaml``
              theme matches
VideoEditing  a crosspost of premiere's themed post, then 99 ordinary posts
editors       one author-deleted post (it must drop out of ``/new``), then 39
              ordinary posts
PremierePro   25 ordinary posts, no special content
AfterEffects  20 ordinary posts, no special content
aivideo       30 ordinary posts, no special content
============  =====================================================================

Usage::

    uv run python tools/make_demo_fixture.py <path>     # `make fixture` is this line
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Final, NamedTuple

from threaddigest.adapters.reddit_fake import FakeRedditGateway


class Source(NamedTuple):
    """One seeded subreddit and the block of ordinary posts generated for it."""

    #: Display name. **Must match a name in ``config/seed.yaml``**: the sweep drives off
    #: that file, so a source missing here is a source the demo run collects nothing from.
    name: str
    t5: str
    subscribers: int
    #: ``f"{title_prefix} {i}"`` titles the ordinary posts; their body is ``f"body {i}"``.
    title_prefix: str
    #: How many ordinary posts. premiere's 98 plus its sticky, poll and themed post put it
    #: over the fake's 100-post page size, so the sweep pages at least one source.
    posts: int
    #: Ordinary post ``i`` is written by ``f"{author_prefix}{i % authors}"``.
    authors: int
    author_prefix: str
    #: ``created_utc`` of ordinary post 0; each later post is :data:`POST_INTERVAL` on.
    first_post_utc: int


#: Wall clock anchor: 2025-09-12T18:40:00Z, the same instant ``tests/conftest.py`` calls
#: ``BASE``. Every timestamp in the corpus is this number plus a documented offset.
BASE_UTC: Final = 1_757_700_000

#: Seconds between consecutive posts of one source.
POST_INTERVAL: Final = 60

#: The six seeded sources, in ``config/seed.yaml``'s order (D-37). Three carry the
#: hand-tuned content described above (the sticky/poll/theme block, the crosspost, the
#: deleted post); the three added under D-37 -- PremierePro, AfterEffects, aivideo --
#: carry only a plain block of ordinary posts, appended after the original three so
#: their ids and bytes are unchanged.
SOURCES: Final = (
    Source("premiere", "t5_10001", 120_000, "premiere post", 98, 9, "pu", BASE_UTC),
    Source("PremierePro", "t5_10004", 90_000, "premiere pro post", 25, 6, "pp", 1_758_300_000),
    Source("editors", "t5_10003", 15_000, "editors post", 39, 5, "eu", 1_758_100_100),
    Source("VideoEditing", "t5_10002", 80_000, "video editing post", 99, 11, "vu", 1_757_900_000),
    Source("AfterEffects", "t5_10005", 40_000, "after effects post", 20, 4, "ae", 1_758_500_000),
    Source("aivideo", "t5_10006", 60_000, "ai video post", 30, 7, "av", 1_758_700_000),
)

#: The three original sources, which carry the hand-tuned content above; every other
#: source in :data:`SOURCES` gets a plain block of ordinary posts only.
_SPECIAL_SOURCES: Final = frozenset({"premiere", "videoediting", "editors"})

#: The pinned rules post, an hour before premiere's ordinary block. It is the oldest post
#: of the largest source, so it lands alone on that source's second ``/new`` page.
STICKY_TITLE: Final = "Read before posting: rules and FAQ"
STICKY_BODY: Final = "Please read the sidebar before posting."
STICKY_AUTHOR: Final = "mod_alex"
STICKY_UTC: Final = BASE_UTC - 3600

#: A poll: a link post whose ``post_hint`` is neither ``link`` nor ``self``. It is written
#: between ordinary posts 89 and 90 and shares post 90's timestamp, so the listing also
#: carries a created_utc tie.
POLL_INDEX: Final = 90
POLL_TITLE: Final = "Which NLE do you prefer for a 4K timeline?"
POLL_AUTHOR: Final = "pu3"
POLL_URL: Final = "https://www.reddit.com/poll/abc123"

#: The one post whose text a ``config/seed.yaml`` theme matches ("Crashes", "Export
#: failures", "Update regressions"), and the one post that is crossposted.
THEMED_TITLE: Final = "My export keeps crashing on 4K H.264 footage"
THEMED_BODY: Final = "Anyone else seeing this since the update?"
THEMED_AUTHOR: Final = "pu5"
THEMED_UTC: Final = BASE_UTC + 99 * POST_INTERVAL
CROSSPOST_UTC: Final = BASE_UTC + 100 * POST_INTERVAL

#: The author-deleted post: ``[deleted]`` author and text, ``removed_by_category`` set by
#: the fake's own ``delete()``. It is the reason ``_visible_post_count`` in
#: ``tests/e2e/test_run_happy_path.py`` is one less than the number of posts in the file.
DELETED_TITLE: Final = "[post since deleted by author]"
DELETED_AUTHOR: Final = "eu0"
DELETED_BODY: Final = "my render settings are wrong, what do you use?"
DELETED_UTC: Final = 1_758_100_000

#: Comments per post: **none**. The tranche-A sweep collects posts only (nothing in
#: ``services/sweep.py`` calls ``fetch_tree``), so a comment tree here would be corpus no
#: run reads, and every post carries ``num_comments`` 0. When comment collection lands,
#: raise this and generate the trees; :func:`check_corpus` holds the file to whatever it
#: says, so the two cannot drift apart silently.
COMMENTS_PER_POST: Final = 0


def _add_ordinary_post(fake: FakeRedditGateway, source: Source, index: int) -> str:
    return fake.add_post(
        source.name,
        title=f"{source.title_prefix} {index}",
        selftext=f"body {index}",
        author=f"{source.author_prefix}{index % source.authors}",
        created_utc=source.first_post_utc + index * POST_INTERVAL,
    )


def _add_ordinary_posts(fake: FakeRedditGateway, source: Source) -> None:
    for index in range(source.posts):
        _add_ordinary_post(fake, source, index)


def _add_premiere(fake: FakeRedditGateway, source: Source) -> str:
    """premiere's block; returns the fullname of the themed post VideoEditing crossposts."""
    fake.add_post(
        source.name,
        title=STICKY_TITLE,
        selftext=STICKY_BODY,
        author=STICKY_AUTHOR,
        created_utc=STICKY_UTC,
        stickied=True,
    )
    for index in range(source.posts):
        if index == POLL_INDEX:
            fake.add_post(
                source.name,
                title=POLL_TITLE,
                author=POLL_AUTHOR,
                created_utc=source.first_post_utc + POLL_INDEX * POST_INTERVAL,
                is_self=False,
                url=POLL_URL,
                post_hint="poll",
            )
        _add_ordinary_post(fake, source, index)
    return fake.add_post(
        source.name,
        title=THEMED_TITLE,
        selftext=THEMED_BODY,
        author=THEMED_AUTHOR,
        created_utc=THEMED_UTC,
    )


def _add_deleted_post(fake: FakeRedditGateway, source: Source) -> None:
    """A post written, then deleted by its author -- the fake's own state transition, so
    the corpus carries exactly the wire shape a deleted post has (``[deleted]`` author and
    selftext, no ``author_fullname``, ``removed_by_category``) rather than a hand-guessed
    imitation of it. The pre-deletion author and body are erased by ``delete()``.
    """
    fullname = fake.add_post(
        source.name,
        title=DELETED_TITLE,
        selftext=DELETED_BODY,
        author=DELETED_AUTHOR,
        created_utc=DELETED_UTC,
    )
    fake.delete(fullname)


def build_gateway() -> FakeRedditGateway:
    """The corpus as a live :class:`FakeRedditGateway`, built in id-allocation order.

    Looked up by name rather than unpacked positionally, because D-37 put the three
    special sources at positions 0, 2 and 3 of :data:`SOURCES` (``config/seed.yaml``'s
    order), not the first three: a positional unpack would silently pair the wrong
    source with the wrong block.
    """
    fake = FakeRedditGateway()
    for source in SOURCES:
        fake.add_subreddit(source.name, t5=source.t5, subscribers=source.subscribers)
    by_name = {source.name.lower(): source for source in SOURCES}
    premiere = by_name["premiere"]
    video_editing = by_name["videoediting"]
    editors = by_name["editors"]
    themed = _add_premiere(fake, premiere)
    fake.add_crosspost(video_editing.name, themed, created_utc=CROSSPOST_UTC)
    _add_ordinary_posts(fake, video_editing)
    _add_deleted_post(fake, editors)
    _add_ordinary_posts(fake, editors)
    for source in SOURCES:
        if source.name.lower() not in _SPECIAL_SOURCES:
            _add_ordinary_posts(fake, source)
    return fake


#: Posts the corpus must contain: every source's ordinary block plus premiere's sticky,
#: poll and themed post and VideoEditing's crosspost, plus editors' deleted post.
EXTRA_POSTS: Final = 5
EXPECTED_POSTS: Final = sum(source.posts for source in SOURCES) + EXTRA_POSTS


def check_corpus(data: dict[str, object]) -> None:
    """Hold the written file to the constants above, or raise :class:`ValueError`.

    A generator that quietly produces a different corpus than it documents is the failure
    mode a committed fixture at least made visible in a diff, so the counts are asserted
    here rather than described in a comment.
    """
    subreddits = data["subreddits"]
    posts = data["posts"]
    comments = data["comments"]
    assert isinstance(subreddits, list) and isinstance(posts, list) and isinstance(comments, list)
    expected_comments = COMMENTS_PER_POST * len(posts)
    found = (len(subreddits), len(posts), len(comments))
    expected = (len(SOURCES), EXPECTED_POSTS, expected_comments)
    if found != expected:
        msg = (
            f"generated corpus is (subreddits, posts, comments)={found}, "
            f"but the constants in {Path(__file__).name} say {expected}"
        )
        raise ValueError(msg)


def build_demo_fixture(path: Path) -> Path:
    """Write the corpus to ``path`` (creating its directory) and return the path."""
    path.parent.mkdir(parents=True, exist_ok=True)
    build_gateway().to_fixture(path)
    check_corpus(json.loads(path.read_text(encoding="utf-8")))
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("path", type=Path, help="where to write the corpus, e.g. data/demo.json")
    written = build_demo_fixture(parser.parse_args().path)
    print(f"wrote {written}: {EXPECTED_POSTS} posts across {len(SOURCES)} subreddits")


if __name__ == "__main__":
    main()
