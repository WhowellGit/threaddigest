#!/usr/bin/env python3
"""Build the demo corpus that the end-to-end suite and ``make run`` collect from.

The corpus is **generated, never committed**. It used to live in git as
``tests/fixtures/json/demo.json`` (13,586 lines, 416 KB): a file no reviewer reads, that
every branch re-diffs, and whose contents nothing explained. This script is its only
producer. ``make fixture`` writes it to ``.build/demo.json`` for ``make run``;
``tests/conftest.py`` builds it once per pytest session into a temp directory. It used to be
written to ``data/demo.json``, inside the real data directory, which :func:`build_demo_fixture`
now refuses (KI-048). The two callers share this module, so there is one definition of "the demo
corpus" rather than one per consumer.

Determinism is structural, not statistical: nothing here draws from ``random``, and the
one seed the corpus has is its **base**, the instant premiere's first ordinary post was
created. Every id, timestamp, author and body is a pure function of that base, of the
offsets below, and of the order the builder calls run in, so two runs from the same base
produce identical bytes -- which ``tests/tools/test_make_demo_fixture.py`` pins by running
this script twice with ``--base`` and comparing them.

The base defaults to **midnight UTC of the current day, minus the corpus's own span**, so the
corpus's *newest* post lands on today rather than its oldest. Anchoring the start (the
original design) let most of the corpus drift into the future -- every source after the
first was created after "today" -- which is not a shape a real Reddit post has and let the
digest's seven-day window (``services.report.WINDOW_DAYS``) hold the entire corpus regardless
of how old a source's offset said it was. Anchoring the end keeps every ``created_utc`` in the
past and lets the window do its job: the newest sources sit inside it, the oldest sit outside
it. ``--base YYYY-MM-DD`` pins the corpus's *start* at that day's midnight, as the anchor
always has, for anyone who wants the same bytes twice on different days.

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

    uv run python tools/make_demo_fixture.py <path>                 # `make fixture` is this line
    uv run python tools/make_demo_fixture.py <path> --base 2025-09-12   # a pinned anchor
"""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, date, datetime, time
from pathlib import Path
from typing import Final, NamedTuple

from threaddigest.adapters.reddit_fake import FakeRedditGateway
from threaddigest.settings import ALLOW_REAL_DATA_DIR, DataDirRefused, default_data_dir


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
    #: Seconds after the corpus base at which ordinary post 0 was created; each later post is
    #: :data:`POST_INTERVAL` on. An offset rather than a wall-clock instant, because the base
    #: moves with the day the corpus is generated and only the offsets are the scenario.
    first_post_offset: int


#: Seconds between consecutive posts of one source.
POST_INTERVAL: Final = 60


def day_start_utc(day: date) -> int:
    """Midnight UTC of ``day``, in epoch seconds: the shape every base has."""
    return int(datetime.combine(day, time.min, tzinfo=UTC).timestamp())


def default_base_utc() -> int:
    """The corpus base when ``--base`` is not given: midnight UTC of the current day, minus
    the corpus's own span, so the corpus's *newest* post -- not its oldest -- lands on today.

    UTC rather than the display timezone, because ``created_utc`` is Reddit's clock and the
    digest's window is measured in it; midnight rather than the current second, so two runs
    of the same day still produce identical bytes.

    Midnight minus the span, not ``datetime.now()`` minus the span: midnight of the current
    day is, by construction, never later than the instant this function runs, so the newest
    timestamp it produces (midnight, since base + span == midnight) is strictly earlier than
    "now" at every point past the first instant of the day -- which every real invocation is.
    ``datetime.now()`` minus the span would put the newest post at the exact instant this
    function was called, which is *not yet in the past* at that instant and would only become
    so by the accident of however much wall-clock time the rest of the run happens to spend.
    """
    return day_start_utc(datetime.now(tz=UTC).date()) - _corpus_span_seconds()


#: The six seeded sources, in ``config/seed.yaml``'s order (D-37). Three carry the
#: hand-tuned content described above (the sticky/poll/theme block, the crosspost, the
#: deleted post); the three added under D-37 -- PremierePro, AfterEffects, aivideo --
#: carry only a plain block of ordinary posts, appended after the original three so
#: their ids and bytes are unchanged.
SOURCES: Final = (
    Source("premiere", "t5_10001", 120_000, "premiere post", 98, 9, "pu", 0),
    Source("PremierePro", "t5_10004", 90_000, "premiere pro post", 25, 6, "pp", 600_000),
    Source("editors", "t5_10003", 15_000, "editors post", 39, 5, "eu", 400_100),
    Source("VideoEditing", "t5_10002", 80_000, "video editing post", 99, 11, "vu", 200_000),
    Source("AfterEffects", "t5_10005", 40_000, "after effects post", 20, 4, "ae", 800_000),
    Source("aivideo", "t5_10006", 60_000, "ai video post", 30, 7, "av", 1_000_000),
)

#: The three original sources, which carry the hand-tuned content above; every other
#: source in :data:`SOURCES` gets a plain block of ordinary posts only.
_SPECIAL_SOURCES: Final = frozenset({"premiere", "videoediting", "editors"})

#: The pinned rules post, an hour before premiere's ordinary block. It is the oldest post
#: of the largest source, so it lands alone on that source's second ``/new`` page.
STICKY_TITLE: Final = "Read before posting: rules and FAQ"
STICKY_BODY: Final = "Please read the sidebar before posting."
STICKY_AUTHOR: Final = "mod_alex"
STICKY_OFFSET: Final = -3600

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
THEMED_OFFSET: Final = 99 * POST_INTERVAL
CROSSPOST_OFFSET: Final = 100 * POST_INTERVAL

#: The author-deleted post: ``[deleted]`` author and text, ``removed_by_category`` set by
#: the fake's own ``delete()``. It is the reason ``_visible_post_count`` in
#: ``tests/e2e/test_run_happy_path.py`` is one less than the number of posts in the file.
DELETED_TITLE: Final = "[post since deleted by author]"
DELETED_AUTHOR: Final = "eu0"
DELETED_BODY: Final = "my render settings are wrong, what do you use?"
DELETED_OFFSET: Final = 400_000


def _corpus_span_seconds() -> int:
    """The largest offset (seconds after ``base``) any post in :func:`build_gateway` carries
    -- currently aivideo's last ordinary post, about 11.6 days out.

    Computed from :data:`SOURCES` and the special offsets above rather than hand-picked, so a
    change to either moves the span -- and therefore :func:`default_base_utc` -- with it
    instead of leaving a number here to silently drift out of sync with what the generator
    actually emits.
    """
    candidates = [THEMED_OFFSET, CROSSPOST_OFFSET, DELETED_OFFSET]
    candidates += [
        source.first_post_offset + (source.posts - 1) * POST_INTERVAL
        for source in SOURCES
        if source.posts
    ]
    return max(candidates)


#: Comments per post: **none**. The tranche-A sweep collects posts only (nothing in
#: ``services/sweep.py`` calls ``fetch_tree``), so a comment tree here would be corpus no
#: run reads, and every post carries ``num_comments`` 0. When comment collection lands,
#: raise this and generate the trees; :func:`check_corpus` holds the file to whatever it
#: says, so the two cannot drift apart silently.
COMMENTS_PER_POST: Final = 0


def _add_ordinary_post(fake: FakeRedditGateway, source: Source, index: int, *, base: int) -> str:
    return fake.add_post(
        source.name,
        title=f"{source.title_prefix} {index}",
        selftext=f"body {index}",
        author=f"{source.author_prefix}{index % source.authors}",
        created_utc=base + source.first_post_offset + index * POST_INTERVAL,
    )


def _add_ordinary_posts(fake: FakeRedditGateway, source: Source, *, base: int) -> None:
    for index in range(source.posts):
        _add_ordinary_post(fake, source, index, base=base)


def _add_premiere(fake: FakeRedditGateway, source: Source, *, base: int) -> str:
    """premiere's block; returns the fullname of the themed post VideoEditing crossposts."""
    fake.add_post(
        source.name,
        title=STICKY_TITLE,
        selftext=STICKY_BODY,
        author=STICKY_AUTHOR,
        created_utc=base + STICKY_OFFSET,
        stickied=True,
    )
    for index in range(source.posts):
        if index == POLL_INDEX:
            fake.add_post(
                source.name,
                title=POLL_TITLE,
                author=POLL_AUTHOR,
                created_utc=base + source.first_post_offset + POLL_INDEX * POST_INTERVAL,
                is_self=False,
                url=POLL_URL,
                post_hint="poll",
            )
        _add_ordinary_post(fake, source, index, base=base)
    return fake.add_post(
        source.name,
        title=THEMED_TITLE,
        selftext=THEMED_BODY,
        author=THEMED_AUTHOR,
        created_utc=base + THEMED_OFFSET,
    )


def _add_deleted_post(fake: FakeRedditGateway, source: Source, *, base: int) -> None:
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
        created_utc=base + DELETED_OFFSET,
    )
    fake.delete(fullname)


def build_gateway(*, base: int) -> FakeRedditGateway:
    """The corpus as a live :class:`FakeRedditGateway`, built in id-allocation order.

    ``base`` is the instant premiere's first ordinary post was created; every other
    timestamp is it plus one of the offsets above, so moving the base moves the whole
    corpus and changes nothing else about the scenario.

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
    themed = _add_premiere(fake, premiere, base=base)
    fake.add_crosspost(video_editing.name, themed, created_utc=base + CROSSPOST_OFFSET)
    _add_ordinary_posts(fake, video_editing, base=base)
    _add_deleted_post(fake, editors, base=base)
    _add_ordinary_posts(fake, editors, base=base)
    for source in SOURCES:
        if source.name.lower() not in _SPECIAL_SOURCES:
            _add_ordinary_posts(fake, source, base=base)
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


def refuses_real_data_dir(path: Path) -> bool:
    """Would writing the corpus to ``path`` put it inside the real data directory?

    A pure predicate, so the rule can be asserted against the real path by a test that
    cannot write anything. ``THREADDIGEST_ALLOW_REAL_DATA_DIR`` lifts it, the same escape
    hatch ``Settings`` takes and named by the same one literal.
    """
    if os.environ.get(ALLOW_REAL_DATA_DIR):
        return False
    return path.expanduser().resolve().is_relative_to(default_data_dir().resolve())


def build_demo_fixture(path: Path, *, base: int | None = None) -> Path:
    """Write the corpus to ``path`` (creating its directory) and return the path.

    ``base`` defaults to :func:`default_base_utc`, so a caller that does not care -- the
    pytest session fixture, ``make fixture`` -- gets a corpus anchored on today.

    A path inside the real data directory is refused before anything is created (KI-048):
    this corpus is fabricated, and the data directory is where the operator's collected data
    lives, which future tooling -- backups, exports, retention -- has no reason to treat as
    foreign. ``make fixture`` wrote ``data/demo.json`` until 2026-09-17 and now writes into
    ``.build/``; the refusal is keyed on the path rather than on pytest, so it holds in a
    plain shell too.
    """
    if refuses_real_data_dir(path):
        msg = (
            f"refusing to write the generated demo corpus to {path}, which is inside the real "
            f"data directory {default_data_dir()}: the corpus is fabricated and that directory "
            f"holds collected data. Write it under .build/ (what `make fixture` does) or set "
            f"{ALLOW_REAL_DATA_DIR}=1 to opt in."
        )
        raise DataDirRefused(msg)
    path.parent.mkdir(parents=True, exist_ok=True)
    build_gateway(base=default_base_utc() if base is None else base).to_fixture(path)
    check_corpus(json.loads(path.read_text(encoding="utf-8")))
    return path


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "path",
        type=Path,
        help="where to write the corpus, e.g. .build/demo.json; a path inside the real "
        "data directory is refused",
    )
    parser.add_argument(
        "--base",
        type=date.fromisoformat,
        default=None,
        metavar="YYYY-MM-DD",
        help="anchor the corpus at midnight UTC of this day instead of today, for byte-stable "
        "output across days",
    )
    args = parser.parse_args()
    base = None if args.base is None else day_start_utc(args.base)
    try:
        written = build_demo_fixture(args.path, base=base)
    except DataDirRefused as exc:
        # `make fixture` is an operator-facing line: the refusal is a usage error with the
        # reason, not a traceback (argparse exits 2 and prints to stderr).
        parser.error(str(exc))
    print(f"wrote {written}: {EXPECTED_POSTS} posts across {len(SOURCES)} subreddits")


if __name__ == "__main__":
    main()
