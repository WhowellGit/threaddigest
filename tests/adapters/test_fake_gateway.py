"""FakeRedditGateway: the scenario builder every service test drives."""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any

import pytest

from threaddigest.adapters.clock import FakeClock
from threaddigest.adapters.reddit_fake import (
    INFO_CHUNK,
    LISTING_CAP,
    PAGE_SIZE,
    SEARCH_CAP,
    Call,
    CrashInjected,
    FakeRedditGateway,
)
from threaddigest.ports import (
    AuthFailed,
    GatewayError,
    HtmlBlocked,
    Limits,
    MoreStub,
    Page,
    RateLimited,
    RedditGateway,
    SubredditForbidden,
    SubredditNotFound,
    SubredditQuarantined,
    SubredditRedirected,
    TransientError,
)

BASE = 1_757_700_000  # matches conftest.BASE: the ``seeded`` fixture's oldest created_utc
T = 1_757_800_000.0  # created_utc used by tree scenarios


def bare(fullname: str) -> str:
    return fullname.split("_", 1)[1]


def titles(page: Page) -> list[str]:
    return [item["title"] for item in page.items]


def names(items: list[dict[str, Any]]) -> list[str]:
    return [str(item["name"]) for item in items]


def tree_scenario(fake: FakeRedditGateway) -> dict[str, str]:
    """A post with a small tree and three ``more`` stubs of counts 5, 2 and 0.

    Visible at first: c1 > c11 > c111, and c2. Stub A (count 5, under the post) hides c3 and
    c4 (c31 is c3's child); stub B (count 2, under c2) hides c21; stub C (count 0, a
    "continue this thread" link under c111) hides c1111. Nine comments in all.
    """
    fake.add_subreddit("premiere")
    post = fake.add_post("premiere", title="Export fails", selftext="help", created_utc=T)
    ids = {"post": post}
    ids["c1"] = fake.add_comment(post, body="c1", author="a", created_utc=T + 1)
    ids["c2"] = fake.add_comment(post, body="c2", author="b", created_utc=T + 2)
    ids["c11"] = fake.add_comment(post, parent=ids["c1"], body="c11", author="c", created_utc=T + 3)
    ids["c111"] = fake.add_comment(
        post, parent=ids["c11"], body="c111", author="d", created_utc=T + 4
    )
    ids["c3"] = fake.add_comment(post, body="c3", author="e", created_utc=T + 5)
    ids["c31"] = fake.add_comment(post, parent=ids["c3"], body="c31", author="f", created_utc=T + 6)
    ids["c4"] = fake.add_comment(post, body="c4", author="g", created_utc=T + 7)
    ids["c21"] = fake.add_comment(post, parent=ids["c2"], body="c21", author="h", created_utc=T + 8)
    ids["c1111"] = fake.add_comment(
        post, parent=ids["c111"], body="c1111", author="i", created_utc=T + 9
    )
    fake.add_more(post, None, 5, [ids["c3"], ids["c4"]])
    fake.add_more(post, ids["c2"], 2, [ids["c21"]])
    fake.add_more(post, ids["c111"], 0, [ids["c1111"]])
    return ids


# ------------------------------------------------------------------------------ protocol


def test_satisfies_gateway_protocol(fake: FakeRedditGateway) -> None:
    assert isinstance(fake, RedditGateway)


# ---------------------------------------------------------------------------------- world


class TestWorld:
    def test_add_post_returns_fullname_and_builds_wire_shape(self, fake: FakeRedditGateway) -> None:
        fn = fake.add_post("premiere", title="Hello world", selftext="text", created_utc=BASE)
        assert fn.startswith("t3_")
        assert len(bare(fn)) == 7  # base36, like current Reddit ids
        page = next(fake.iter_new_pages("premiere", max_pages=1))
        (post,) = page.items
        assert post["name"] == fn
        assert post["id"] == bare(fn)
        assert post["subreddit"] == "premiere"
        assert post["subreddit_id"].startswith("t5_")
        assert post["author"] == "u1"
        assert post["author_fullname"].startswith("t2_")
        assert post["created_utc"] == float(BASE)
        assert post["is_self"] is True
        assert post["selftext_html"] is not None
        assert post["permalink"] == f"/r/premiere/comments/{bare(fn)}/hello_world/"
        assert post["removed_by_category"] is None
        assert post["num_comments"] == 0

    def test_created_utc_defaults_to_the_injected_clock(self) -> None:
        with_clock = FakeRedditGateway(clock=FakeClock(1_000))
        fn = with_clock.add_post("premiere", title="x")
        assert with_clock.info([fn])[0]["created_utc"] == 1_000.0
        with pytest.raises(ValueError, match="created_utc"):
            FakeRedditGateway().add_post("premiere", title="x")

    def test_link_post_has_url_domain_and_no_selftext_html(self, fake: FakeRedditGateway) -> None:
        fn = fake.add_post(
            "premiere", title="Video", created_utc=BASE, is_self=False, url="https://youtu.be/x"
        )
        (post,) = fake.info([fn])
        assert post["is_self"] is False
        assert post["url"] == "https://youtu.be/x"
        assert post["domain"] == "youtu.be"
        assert post["selftext"] == ""
        assert post["selftext_html"] is None
        assert post["post_hint"] == "link"

    def test_raw_kwargs_override_defaults(self, fake: FakeRedditGateway) -> None:
        fn = fake.add_post(
            "premiere", title="x", created_utc=BASE, score=42, edited=1_757_700_100.0, custom="y"
        )
        (post,) = fake.info([fn])
        assert post["score"] == 42
        assert post["edited"] == 1_757_700_100.0
        assert post["custom"] == "y"

    def test_explicit_id_in_either_form_and_duplicate_rejected(
        self, fake: FakeRedditGateway
    ) -> None:
        assert fake.add_post("premiere", id="abc123", title="x", created_utc=BASE) == "t3_abc123"
        assert fake.add_post("premiere", id="t3_abc124", title="x", created_utc=BASE) == "t3_abc124"
        with pytest.raises(ValueError, match="duplicate"):
            fake.add_post("premiere", id="abc123", title="y", created_utc=BASE)

    def test_deleted_author_at_creation_has_no_author_fullname(
        self, fake: FakeRedditGateway
    ) -> None:
        fn = fake.add_post("premiere", title="x", author="[deleted]", created_utc=BASE)
        (post,) = fake.info([fn])
        assert "author_fullname" not in post

    def test_author_fullname_is_stable_per_author(self, fake: FakeRedditGateway) -> None:
        a = fake.add_post("premiere", title="a", author="wes", created_utc=BASE)
        b = fake.add_post("premiere", title="b", author="wes", created_utc=BASE + 1)
        c = fake.add_post("premiere", title="c", author="other", created_utc=BASE + 2)
        got = {p["name"]: p["author_fullname"] for p in fake.info([a, b, c])}
        assert got[a] == got[b] != got[c]

    def test_add_post_auto_creates_subreddit(self, fake: FakeRedditGateway) -> None:
        fake.add_post("VideoEditing", title="x", created_utc=BASE)
        about = fake.about("videoediting")
        assert about["display_name"] == "VideoEditing"
        assert about["name"].startswith("t5_")

    def test_add_subreddit_controls_casing_identity_and_quarantine(
        self, fake: FakeRedditGateway
    ) -> None:
        key = fake.add_subreddit("VideoEditing", display_name="videoEditing", t5="t5_abc")
        assert key == "videoediting"
        about = fake.about("VIDEOEDITING")
        assert about["display_name"] == "videoEditing"
        assert about["display_name_prefixed"] == "r/videoEditing"
        assert about["name"] == "t5_abc"
        assert about["id"] == "abc"
        fake.add_subreddit("q", quarantine=True)
        with pytest.raises(SubredditQuarantined):
            fake.about("q")

    def test_add_subreddit_twice_updates_and_keeps_identity(self, fake: FakeRedditGateway) -> None:
        assert fake.add_subreddit("premiere", subscribers=1) == "premiere"
        first = fake.about("premiere")["name"]
        assert fake.add_subreddit("Premiere", subscribers=99, over18=True) == "premiere"
        about = fake.about("premiere")
        assert about["name"] == first
        assert about["subscribers"] == 99
        assert about["over18"] is True
        assert about["display_name"] == "premiere"

    def test_add_comment_wire_shape_and_num_comments(self, fake: FakeRedditGateway) -> None:
        post = fake.add_post("premiere", title="x", author="op", created_utc=BASE)
        top = fake.add_comment(post, body="top", author="op", created_utc=BASE + 1)
        child = fake.add_comment(post, parent=top, body="child", author="z", created_utc=BASE + 2)
        assert top.startswith("t1_")
        (refreshed,) = fake.info([post])
        assert refreshed["num_comments"] == 2
        tree = fake.fetch_tree(post, more_limit=0)
        first, second = tree.comments
        assert first["name"] == top
        assert first["parent_id"] == post
        assert first["link_id"] == post
        assert first["is_submitter"] is True
        assert second["name"] == child
        assert second["parent_id"] == top
        assert second["is_submitter"] is False
        assert second["permalink"].endswith(f"/{bare(child)}/")

    def test_add_comment_rejects_unknown_or_foreign_parent(self, fake: FakeRedditGateway) -> None:
        a = fake.add_post("premiere", title="a", created_utc=BASE)
        b = fake.add_post("premiere", title="b", created_utc=BASE)
        cb = fake.add_comment(b, body="on b", author="x", created_utc=BASE)
        with pytest.raises(KeyError):
            fake.add_comment(a, parent="nope", body="x", author="x", created_utc=BASE)
        with pytest.raises(KeyError):
            fake.add_comment(a, parent=cb, body="x", author="x", created_utc=BASE)
        with pytest.raises(KeyError):
            fake.add_comment("t3_missing", body="x", author="x", created_utc=BASE)
        with pytest.raises(KeyError):
            fake.add_more("t3_missing", None, 3, [])

    def test_add_crosspost(self, fake: FakeRedditGateway) -> None:
        parent = fake.add_post("editors", title="Orig", selftext="body", created_utc=BASE)
        xp = fake.add_crosspost("premiere", parent, created_utc=BASE + 1)
        (post,) = fake.info([xp])
        assert post["subreddit"] == "premiere"
        assert post["title"] == "Orig"
        assert post["selftext"] == ""
        assert post["is_self"] is False
        assert post["crosspost_parent"] == parent
        assert post["crosspost_parent_list"][0]["title"] == "Orig"
        assert post["crosspost_parent_list"][0]["selftext"] == "body"
        assert "post_hint" not in post
        custom = fake.add_crosspost("premiere", parent, title="Custom", created_utc=BASE + 2)
        assert fake.info([custom])[0]["title"] == "Custom"
        with pytest.raises(KeyError):
            fake.add_crosspost("premiere", "t3_missing", created_utc=BASE)

    def test_set_field_remove_field_and_restore(self, fake: FakeRedditGateway) -> None:
        fn = fake.add_post("premiere", title="x", created_utc=BASE)
        fake.set_field(fn, "removed_by_category", "brand_new_reason")
        fake.set_field(fn, "score", 42)
        fake.remove_field(fn, "author_fullname")
        (post,) = fake.info([fn])
        assert post["removed_by_category"] == "brand_new_reason"
        assert post["score"] == 42
        assert "author_fullname" not in post
        fake.restore(fn)
        (post,) = fake.info([fn])
        assert post["removed_by_category"] is None
        assert post["score"] == 1
        assert post["author_fullname"].startswith("t2_")

    def test_set_about_overrides_identity_fields(self, fake: FakeRedditGateway) -> None:
        fake.add_subreddit("premiere", subscribers=10)
        fake.set_about("premiere", name="t5_other", subscribers=5, brand_new_key=True)
        about = fake.about("premiere")
        assert about["name"] == "t5_other"
        assert about["subscribers"] == 5
        assert about["brand_new_key"] is True

    def test_set_raw_shape_transforms_every_emitted_payload_of_a_kind(
        self, fake: FakeRedditGateway
    ) -> None:
        ids = tree_scenario(fake)

        def nest(item: dict[str, Any]) -> dict[str, Any]:
            item["author_info"] = {"fullname": item.pop("author_fullname", None)}
            return item

        fake.set_raw_shape("post", nest)
        page = next(fake.iter_new_pages("premiere", max_pages=1))
        assert "author_fullname" not in page.items[0]
        assert page.items[0]["author_info"]["fullname"].startswith("t2_")
        tree = fake.fetch_tree(ids["post"], more_limit=0)
        assert "author_info" in tree.post
        assert "author_fullname" in tree.comments[0]  # comments untouched
        assert "author_info" in fake.info([ids["post"]])[0]
        fake.set_raw_shape("post", None)
        assert "author_fullname" in fake.info([ids["post"]])[0]
        with pytest.raises(ValueError, match="shape kind"):
            fake.set_raw_shape("listing", nest)

    def test_edit_sets_text_and_edited_timestamp(self, fake: FakeRedditGateway) -> None:
        fn = fake.add_post("premiere", title="x", selftext="v1", created_utc=BASE)
        cid = fake.add_comment(fn, body="c1", author="a", created_utc=BASE + 1)
        fake.edit(fn, "v2")
        fake.edit(cid, "c2", edited_utc=BASE + 500)
        post, comment = fake.info([fn, cid])
        assert post["selftext"] == "v2"
        assert "v2" in post["selftext_html"]
        assert post["edited"] == float(BASE + 60)  # no clock: created + 60 s
        assert comment["body"] == "c2"
        assert comment["edited"] == float(BASE + 500)
        fake.restore(fn)
        (post,) = fake.info([fn])
        assert post["selftext"] == "v1"
        assert post["edited"] is False

        clocked = FakeRedditGateway(clock=FakeClock(5_000))
        other = clocked.add_post("premiere", title="x", selftext="v1")
        clocked.edit(other, "v2")
        assert clocked.info([other])[0]["edited"] == 5_000.0

    def test_hidden_post_appears_after_unhide_at_its_chronological_place(
        self, fake: FakeRedditGateway
    ) -> None:
        fake.add_post("premiere", title="old", created_utc=BASE)
        held = fake.add_post("premiere", title="held", created_utc=BASE + 1, hidden=True)
        fake.add_post("premiere", title="new", created_utc=BASE + 2)
        assert titles(next(fake.iter_new_pages("premiere", max_pages=1))) == ["new", "old"]
        assert fake.info([held])[0]["title"] == "held"  # it exists, it is just not listed
        fake.unhide(held)
        assert titles(next(fake.iter_new_pages("premiere", max_pages=1))) == ["new", "held", "old"]


# -------------------------------------------------------------------------------- listing


class TestListing:
    def test_pages_are_newest_first_and_100_wide(self, seeded: FakeRedditGateway) -> None:
        pages = list(seeded.iter_new_pages("premiere", max_pages=10))
        assert [len(p.items) for p in pages] == [100, 100, 50]
        assert titles(pages[0])[:2] == ["post 249", "post 248"]
        assert titles(pages[2])[-1] == "post 0"
        assert [p.complete for p in pages] == [False, False, True]
        assert pages[0].after == pages[0].items[-1]["name"]
        assert pages[1].after == pages[1].items[-1]["name"]
        assert pages[2].after is None
        assert seeded.requests_made == 3

    def test_subreddit_names_are_case_insensitive(self, seeded: FakeRedditGateway) -> None:
        page = next(seeded.iter_new_pages("PREMIERE", max_pages=1))
        assert page.items[0]["subreddit"] == "premiere"

    def test_max_pages_stops_early_with_cursor(self, seeded: FakeRedditGateway) -> None:
        pages = list(seeded.iter_new_pages("premiere", max_pages=1))
        assert len(pages) == 1
        assert pages[0].complete is False
        assert pages[0].after is not None
        assert seeded.requests_made == 1

    def test_resume_from_cursor_continues_exactly(self, seeded: FakeRedditGateway) -> None:
        first = next(seeded.iter_new_pages("premiere", max_pages=1))
        rest = list(seeded.iter_new_pages("premiere", max_pages=10, after=first.after))
        assert titles(rest[0])[0] == "post 149"
        seen = names(first.items) + [n for p in rest for n in names(p.items)]
        assert len(seen) == len(set(seen)) == 250

    def test_unknown_cursor_raises_gateway_error(self, seeded: FakeRedditGateway) -> None:
        with pytest.raises(GatewayError, match="cursor"):
            next(seeded.iter_new_pages("premiere", max_pages=1, after="t3_nope"))

    def test_same_timestamp_latest_inserted_first(self, fake: FakeRedditGateway) -> None:
        older = fake.add_post("premiere", title="first", created_utc=BASE)
        newer = fake.add_post("premiere", title="second", created_utc=BASE)
        page = next(fake.iter_new_pages("premiere", max_pages=1))
        assert names(page.items) == [newer, older]

    def test_overlap_repeats_last_item_on_next_page(self, seeded: FakeRedditGateway) -> None:
        seeded.set_overlap(True)
        pages = list(seeded.iter_new_pages("premiere", max_pages=10))
        assert [len(p.items) for p in pages] == [100, 100, 52]
        assert pages[1].items[0]["name"] == pages[0].items[-1]["name"]
        assert pages[2].items[0]["name"] == pages[1].items[-1]["name"]
        assert len({n for p in pages for n in names(p.items)}) == 250

    def test_overlap_per_subreddit_with_n_items_and_clearing(
        self, seeded: FakeRedditGateway
    ) -> None:
        seeded.add_post("editors", title="e", created_utc=BASE)
        seeded.set_overlap("premiere", 2)
        pages = list(seeded.iter_new_pages("premiere", max_pages=10))
        assert [len(p.items) for p in pages] == [100, 100, 54]
        assert names(pages[1].items[:2]) == names(pages[0].items[-2:])
        assert len({n for p in pages for n in names(p.items)}) == 250
        assert len(list(seeded.iter_new_pages("editors", max_pages=10))) == 1
        seeded.set_overlap(False)
        pages = list(seeded.iter_new_pages("premiere", max_pages=10))
        assert [len(p.items) for p in pages] == [100, 100, 50]

    def test_page_sizes_make_short_pages_with_cursors(self, seeded: FakeRedditGateway) -> None:
        seeded.set_page_size("premiere", [37, 100])
        pages = list(seeded.iter_new_pages("premiere", max_pages=10))
        assert [len(p.items) for p in pages] == [37, 100, 100, 13]
        assert pages[0].after is not None
        assert pages[-1].after is None
        rest = list(seeded.iter_new_pages("premiere", max_pages=10, after=pages[0].after))
        assert [len(p.items) for p in rest] == [100, 100, 13]
        assert titles(rest[0])[0] == "post 212"

    def test_deleted_and_removed_posts_drop_from_new(self, seeded: FakeRedditGateway) -> None:
        page = next(seeded.iter_new_pages("premiere", max_pages=1))
        newest, second = page.items[0], page.items[1]
        seeded.delete(newest["name"])
        seeded.remove(second["name"])
        pages = list(seeded.iter_new_pages("premiere", max_pages=10))
        all_names = [n for p in pages for n in names(p.items)]
        assert newest["name"] not in all_names
        assert second["name"] not in all_names
        assert len(all_names) == 248
        # a short page keeps a cursor: Reddit filters after pagination
        assert len(pages[0].items) == 98
        assert pages[0].after is not None
        assert pages[0].after == page.after

    def test_post_created_removed_is_not_listed(self, fake: FakeRedditGateway) -> None:
        fake.add_post("premiere", title="spam", created_utc=BASE, removed_by_category="moderator")
        fake.add_post("premiere", title="fine", created_utc=BASE - 1)
        page = next(fake.iter_new_pages("premiere", max_pages=1))
        assert titles(page) == ["fine"]

    def test_empty_subreddit_yields_one_empty_complete_page(self, fake: FakeRedditGateway) -> None:
        fake.add_subreddit("quiet")
        pages = list(fake.iter_new_pages("quiet", max_pages=10))
        assert pages == [Page(items=[], after=None, complete=True)]
        assert fake.requests_made == 1

    def test_unknown_subreddit_redirects_like_reddit(self, fake: FakeRedditGateway) -> None:
        with pytest.raises(SubredditRedirected) as info:
            next(fake.iter_new_pages("doesnotexist", max_pages=1))
        assert info.value.path == "/subreddits/search?q=doesnotexist"
        assert fake.requests_made == 1

    def test_listing_is_capped_at_1000_items(self, fake: FakeRedditGateway) -> None:
        for i in range(LISTING_CAP + 5):
            fake.add_post("big", title=f"p{i}", created_utc=BASE + i)
        pages = list(fake.iter_new_pages("big", max_pages=20))
        assert len(pages) == LISTING_CAP // PAGE_SIZE
        assert pages[-1].complete is True
        all_titles = [t for p in pages for t in titles(p)]
        assert len(all_titles) == LISTING_CAP
        assert all_titles[0] == f"p{LISTING_CAP + 4}"
        assert "p0" not in all_titles

    def test_stickies_sit_at_their_chronological_position_unless_pinned(
        self, fake: FakeRedditGateway
    ) -> None:
        fake.add_post("premiere", title="sticky", created_utc=BASE, stickied=True)
        fake.add_post("premiere", title="newer", created_utc=BASE + 10)
        assert titles(next(fake.iter_new_pages("premiere", max_pages=1))) == ["newer", "sticky"]
        fake.set_listing_order("premiere", sticky_first=True)
        assert titles(next(fake.iter_new_pages("premiere", max_pages=1))) == ["sticky", "newer"]
        fake.set_listing_order("premiere", sticky_first=False)
        assert titles(next(fake.iter_new_pages("premiere", max_pages=1))) == ["newer", "sticky"]

    def test_returned_items_are_copies(self, seeded: FakeRedditGateway) -> None:
        page = next(seeded.iter_new_pages("premiere", max_pages=1))
        page.items[0]["title"] = "mutated"
        again = next(seeded.iter_new_pages("premiere", max_pages=1))
        assert again.items[0]["title"] == "post 249"

    def test_freeze_listing_hides_later_posts_but_not_from_new_head(
        self, seeded: FakeRedditGateway
    ) -> None:
        seeded.freeze_listing()
        seeded.add_post("premiere", title="brand new", created_utc=BASE + 10**6)
        pages = list(seeded.iter_new_pages("premiere", max_pages=10))
        assert "brand new" not in [t for p in pages for t in titles(p)]
        assert sum(len(p.items) for p in pages) == 250
        head = seeded.new_head("premiere")
        assert head is not None
        assert head["title"] == "brand new"
        seeded.unfreeze_listing("premiere")
        assert titles(next(seeded.iter_new_pages("premiere", max_pages=1)))[0] == "brand new"

    def test_frozen_listing_still_drops_deletions(self, seeded: FakeRedditGateway) -> None:
        seeded.freeze_listing("premiere")
        page = next(seeded.iter_new_pages("premiere", max_pages=1))
        seeded.delete(page.items[0]["name"])
        assert titles(next(seeded.iter_new_pages("premiere", max_pages=1)))[0] == "post 248"


class TestNewHead:
    def test_returns_newest_non_sticky_within_three(self, fake: FakeRedditGateway) -> None:
        fake.add_post("premiere", title="old", created_utc=BASE)
        fake.add_post("premiere", title="s1", created_utc=BASE + 1, stickied=True)
        fake.add_post("premiere", title="s2", created_utc=BASE + 2, stickied=True)
        head = fake.new_head("premiere")
        assert head is not None
        assert head["title"] == "old"
        assert fake.requests_made == 1

    def test_three_stickies_or_empty_listing_give_none(self, fake: FakeRedditGateway) -> None:
        fake.add_post("premiere", title="old", created_utc=BASE)
        for i in range(3):
            fake.add_post("premiere", title=f"s{i}", created_utc=BASE + 1 + i, stickied=True)
        assert fake.new_head("premiere") is None
        fake.add_subreddit("quiet")
        assert fake.new_head("quiet") is None

    def test_ignores_deleted_posts(self, fake: FakeRedditGateway) -> None:
        fake.add_post("premiere", title="old", created_utc=BASE)
        newest = fake.add_post("premiere", title="new", created_utc=BASE + 1)
        fake.delete(newest)
        head = fake.new_head("premiere")
        assert head is not None
        assert head["title"] == "old"

    def test_live_anchor_by_time_or_fullname(self, fake: FakeRedditGateway) -> None:
        oldest = fake.add_post("premiere", title="oldest", created_utc=BASE)
        fake.add_post("premiere", title="newest", created_utc=BASE + 1)
        fake.set_live_anchor("premiere", BASE + 999_999)
        head = fake.new_head("premiere")
        assert head is not None
        assert head["created_utc"] == float(BASE + 999_999)
        assert head["stickied"] is False
        fake.set_live_anchor("premiere", fullname=oldest)
        head = fake.new_head("premiere")
        assert head is not None
        assert head["name"] == oldest
        fake.set_live_anchor("premiere")
        head = fake.new_head("premiere")
        assert head is not None
        assert head["title"] == "newest"
        with pytest.raises(KeyError):
            fake.set_live_anchor("premiere", fullname="t3_missing")


# ----------------------------------------------------------------------------------- tree


class TestTree:
    def test_base_fetch_without_expansion(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        tree = fake.fetch_tree(ids["post"], more_limit=0)
        assert [c["body"] for c in tree.comments] == ["c1", "c11", "c111", "c2"]
        assert [c["depth"] for c in tree.comments] == [0, 1, 2, 0]
        assert tree.requests_used == 1
        assert fake.requests_made == 1
        assert tree.complete is False
        assert tree.more == [
            MoreStub(ids["post"], 5, [bare(ids["c3"]), bare(ids["c4"])]),
            MoreStub(ids["c2"], 2, [bare(ids["c21"])]),
            MoreStub(ids["c111"], 0, [bare(ids["c1111"])]),
        ]
        assert tree.post["title"] == "Export fails"
        assert tree.post["num_comments"] == 9

    def test_expands_largest_count_first_one_request_each(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        tree = fake.fetch_tree(ids["post"], more_limit=1)
        bodies = [c["body"] for c in tree.comments]
        assert bodies == ["c1", "c11", "c111", "c2", "c3", "c31", "c4"]
        assert [c["depth"] for c in tree.comments if c["body"] in {"c3", "c31"}] == [0, 1]
        assert [m.count for m in tree.more] == [2, 0]
        assert tree.requests_used == 2
        assert fake.requests_made == 2

        fake2 = FakeRedditGateway()
        ids2 = tree_scenario(fake2)
        tree2 = fake2.fetch_tree(ids2["post"], more_limit=2)
        assert [m.count for m in tree2.more] == [0]
        assert tree2.requests_used == 3
        assert tree2.complete is False

    def test_continue_thread_stub_costs_a_request_and_completes(
        self, fake: FakeRedditGateway
    ) -> None:
        ids = tree_scenario(fake)
        tree = fake.fetch_tree(ids["post"], more_limit=16)
        assert tree.complete is True
        assert tree.more == []
        assert tree.requests_used == 4  # base + three stubs; never more than the stubs present
        expected = ["c1", "c11", "c111", "c1111", "c2", "c21", "c3", "c31", "c4"]
        assert [c["body"] for c in tree.comments] == expected
        assert fake.requests_made == 4

    def test_nested_stub_is_only_discovered_once_reachable(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        hidden_child = fake.add_comment(
            ids["post"], parent=ids["c3"], body="c32", author="j", created_utc=T + 10
        )
        fake.add_more(ids["post"], ids["c3"], 1, [hidden_child])
        unexpanded = fake.fetch_tree(ids["post"], more_limit=0)
        assert ids["c3"] not in [m.parent_fullname for m in unexpanded.more]
        expanded = fake.fetch_tree(ids["post"], more_limit=1)
        assert MoreStub(ids["c3"], 1, [bare(hidden_child)]) in expanded.more
        assert "c32" not in [c["body"] for c in expanded.comments]

    def test_equal_counts_expand_in_insertion_order(self, fake: FakeRedditGateway) -> None:
        post = fake.add_post("premiere", title="x", created_utc=T)
        a = fake.add_comment(post, body="a", author="a", created_utc=T)
        b = fake.add_comment(post, body="b", author="b", created_utc=T)
        fake.add_more(post, None, 3, [a])
        fake.add_more(post, None, 3, [b])
        tree = fake.fetch_tree(post, more_limit=1)
        assert [c["body"] for c in tree.comments] == ["a"]
        assert tree.more == [MoreStub(post, 3, [bare(b)])]

    def test_a_large_more_node_reveals_at_most_a_hundred_per_request(
        self, fake: FakeRedditGateway
    ) -> None:
        """KI-023 (external round one, 2026-09-14): Reddit reveals at most a hundred new
        comments per ``morechildren`` request, so a stub with more behind it takes several
        requests, each leaving the remainder stubbed. Before this, one expansion revealed the
        whole tree for one request and reported it complete."""
        post = fake.add_post("premiere", title="big thread", created_utc=T)
        for i in range(202):
            fake.add_comment(post, body=f"c{i}", author="u", created_utc=T + i)
        fake.set_tree_clamp(1)

        one = fake.fetch_tree(post, more_limit=1)
        assert len(one.comments) == 1 + 100  # the kept comment plus one chunk
        assert one.complete is False  # residual work remains
        assert one.requests_used == 2  # base + one expansion
        assert one.more and one.more[0].count == 101  # 201 stubbed, 100 revealed, 101 left

        full = fake.fetch_tree(post, more_limit=16)
        assert full.complete is True
        assert len(full.comments) == 202
        assert full.requests_used == 4  # base + ceil(201/100) = 3 expansions

    def test_a_comment_an_expansion_redelivers_comes_back_once(
        self, fake: FakeRedditGateway
    ) -> None:
        """KI-042, panel finding C-5: the shape the fake could not express until 2026-09-17.

        `morechildren` is asked with `limit_children=0`, so a batch that repeats a comment the
        base fetch already delivered is the expected case, not an oddity -- and the real
        adapter re-emitted it (and, for a repeated parent, its whole subtree). The fake could
        never produce the shape, because it walks an index, so the contract suite (AD-04) as
        designed would never have seen it. `add_more(..., redelivers=...)` produces it, and
        both gateways answer with the same count: the real adapter's half is
        `tests/adapters/test_praw_gateway.py::test_a_comment_an_expansion_returns_again_is_indexed_once`.
        """
        post = fake.add_post("premiere", title="overlapping batch", created_utc=T)
        c1 = fake.add_comment(post, body="c1", author="a", created_utc=T + 1)
        c2 = fake.add_comment(post, body="c2", author="b", created_utc=T + 2)
        fake.add_more(post, None, 1, [c2], redelivers=[c1])

        tree = fake.fetch_tree(post, more_limit=1)

        assert [c["body"] for c in tree.comments] == ["c1", "c2"]
        assert [c["depth"] for c in tree.comments] == [0, 0]
        assert tree.complete is True
        assert tree.requests_used == 2

    def test_a_redelivering_expansion_really_puts_the_comment_in_the_stream_twice(
        self, fake: FakeRedditGateway
    ) -> None:
        """The control for the test above: the de-duplication is a guard, not an accident.

        Without it the fake would hand back the comment twice, exactly as the adapter did,
        and the contract row would prove nothing.
        """
        post = fake.add_post("premiere", title="overlapping batch", created_utc=T)
        c1 = fake.add_comment(post, body="c1", author="a", created_utc=T + 1)
        c2 = fake.add_comment(post, body="c2", author="b", created_utc=T + 2)
        fake.add_more(post, None, 1, [c2], redelivers=[c1])

        tree = fake._tree_index(bare(post))
        stub = tree.next_stub()
        assert stub is not None
        tree.expand(stub)

        assert [cid for cid, _ in tree.delivered()].count(bare(c1)) == 2
        assert [cid for cid, _ in tree.visible()].count(bare(c1)) == 1

    def test_a_single_more_child_with_a_large_subtree_is_revealed_whole(
        self, fake: FakeRedditGateway
    ) -> None:
        """KI-023 known fidelity limit (external round one panel, 2026-09-15): chunking is at
        direct-child granularity, so one `more` child whose OWN subtree exceeds 100 is revealed
        whole in a single request -- the fake cannot split a cascading subtree. Reddit would need
        several requests. This is pinned so the gap is documented, not silent, and is validated
        against the real adapter on the probe day before M1b."""
        post = fake.add_post("premiere", title="deep thread", created_utc=T)
        root = fake.add_comment(post, body="root", author="u", created_utc=T)
        for i in range(150):  # 150 replies to a single root comment: subtree size 151
            fake.add_comment(post, body=f"r{i}", author="u", parent=root, created_utc=T + i + 1)
        fake.add_more(post, None, 151, [root])  # one stub, one child, a 151-instance subtree

        result = fake.fetch_tree(post, more_limit=16)

        assert result.complete is True
        assert len(result.comments) == 151  # the whole subtree came back...
        assert result.requests_used == 2  # ...in ONE expansion, though Reddit needs ceil(151/100)=2
        assert result.more == []

    def test_tree_clamp_turns_the_tail_into_stubs(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        fake.set_tree_clamp(2)
        clamped = fake.fetch_tree(ids["post"], more_limit=0)
        assert [c["body"] for c in clamped.comments] == ["c1", "c11"]
        assert clamped.more == [
            MoreStub(ids["post"], 5, [bare(ids["c3"]), bare(ids["c4"])]),
            MoreStub(ids["c11"], 2, [bare(ids["c111"])]),  # c111 + c1111
            MoreStub(ids["post"], 2, [bare(ids["c2"])]),  # c2 + c21
        ]
        full = fake.fetch_tree(ids["post"], more_limit=16)
        assert full.complete is True
        assert len(full.comments) == 9
        assert full.requests_used == 6  # base + 3 real stubs + 2 synthetic ones
        fake.set_tree_clamp(None)
        assert fake.fetch_tree(ids["post"], more_limit=16).requests_used == 4

    def test_deleted_leaf_vanishes_but_deleted_parent_stays(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        fake.delete(ids["c4"])  # a true leaf
        fake.delete(ids["c1"])  # has children
        tree = fake.fetch_tree(ids["post"], more_limit=16)
        tree_names = names(tree.comments)
        assert ids["c4"] not in tree_names
        assert len(tree.comments) == 8
        placeholder = tree.comments[0]
        assert placeholder["name"] == ids["c1"]
        assert placeholder["body"] == "[deleted]"
        assert placeholder["author"] == "[deleted]"
        assert "author_fullname" not in placeholder
        assert placeholder["collapsed_reason_code"] == "DELETED"
        # info() still returns the deleted leaf as a tombstone; only vanish() omits
        (gone,) = fake.info([ids["c4"]])
        assert gone["body"] == "[deleted]"

    def test_drop_from_tree_only_affects_the_tree(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        fake.drop_from_tree(ids["c2"])
        tree = fake.fetch_tree(ids["post"], more_limit=0)
        assert ids["c2"] not in names(tree.comments)
        assert fake.info([ids["c2"]])[0]["body"] == "c2"
        fake.restore(ids["c2"])
        assert ids["c2"] in names(fake.fetch_tree(ids["post"], more_limit=0).comments)
        with pytest.raises(ValueError, match="not a comment"):
            fake.drop_from_tree(ids["post"])

    def test_removed_comment_stays_as_placeholder(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        fake.remove(ids["c2"])
        tree = fake.fetch_tree(ids["post"], more_limit=0)
        removed = next(c for c in tree.comments if c["name"] == ids["c2"])
        assert removed["body"] == "[removed]"
        assert removed["author"] == "[deleted]"
        assert "removed_by_category" not in removed
        assert fake.removals[ids["c2"]] == "moderator"

    def test_accepts_bare_id_and_refreshes_deleted_post(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        fake.delete(ids["post"])
        tree = fake.fetch_tree(bare(ids["post"]), more_limit=0)
        assert tree.post["removed_by_category"] == "deleted"
        assert tree.post["selftext"] == "[deleted]"
        assert len(tree.comments) == 4

    def test_unknown_post_is_a_gateway_error_that_still_costs(
        self, fake: FakeRedditGateway
    ) -> None:
        with pytest.raises(GatewayError, match="no such post"):
            fake.fetch_tree("zzzzzzz", more_limit=0)
        assert fake.requests_made == 1

    def test_post_without_comments(self, fake: FakeRedditGateway) -> None:
        post = fake.add_post("premiere", title="quiet", created_utc=T)
        tree = fake.fetch_tree(post, more_limit=16)
        assert tree.comments == []
        assert tree.more == []
        assert tree.complete is True
        assert tree.requests_used == 1

    def test_tree_items_are_copies(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        tree = fake.fetch_tree(ids["post"], more_limit=0)
        tree.comments[0]["body"] = "mutated"
        tree.post["title"] = "mutated"
        again = fake.fetch_tree(ids["post"], more_limit=0)
        assert again.comments[0]["body"] == "c1"
        assert again.post["title"] == "Export fails"


# ----------------------------------------------------------------------------------- info


class TestInfo:
    def test_returns_found_items_in_insertion_order_omitting_missing(
        self, fake: FakeRedditGateway
    ) -> None:
        fake.add_subreddit("premiere", t5="t5_prem")
        post = fake.add_post("premiere", title="x", created_utc=T)
        comment = fake.add_comment(post, body="c", author="a", created_utc=T)
        got = fake.info([comment, "t3_zzzzzzz", post, "t1_yyyyyyy", "t5_prem"])
        assert names(got) == ["t5_prem", post, comment]
        assert fake.requests_made == 1

    def test_comments_from_info_carry_no_depth_but_tree_comments_do(
        self, fake: FakeRedditGateway
    ) -> None:
        post = fake.add_post("premiere", title="x", created_utc=T)
        comment = fake.add_comment(post, body="c", author="a", created_utc=T)
        (from_info,) = fake.info([comment])
        assert "depth" not in from_info
        (from_tree,) = fake.fetch_tree(post, more_limit=0).comments
        assert from_tree["depth"] == 0

    def test_chunks_by_100_and_costs_nothing_when_empty(self, fake: FakeRedditGateway) -> None:
        fullnames = [fake.add_post("premiere", title=str(i), created_utc=T + i) for i in range(250)]
        assert len(fake.info(fullnames)) == 250
        assert fake.requests_made == -(-250 // INFO_CHUNK) == 3
        assert fake.info([]) == []
        assert fake.requests_made == 3

    def test_duplicate_fullnames_are_returned_once(self, fake: FakeRedditGateway) -> None:
        post = fake.add_post("premiere", title="x", created_utc=T)
        assert len(fake.info([post, post])) == 1
        assert fake.requests_made == 1

    def test_shuffle_is_seeded_and_a_permutation(self) -> None:
        def build() -> tuple[FakeRedditGateway, list[str]]:
            gw = FakeRedditGateway()
            return gw, [gw.add_post("premiere", title=str(i), created_utc=T + i) for i in range(30)]

        gw1, fullnames = build()
        gw1.set_info_order(shuffle=True, seed=7)
        order1 = names(gw1.info(fullnames))
        gw2, _ = build()
        gw2.set_info_order(shuffle=True, seed=7)
        order2 = names(gw2.info(fullnames))
        assert order1 == order2
        assert order1 != fullnames
        assert sorted(order1) == sorted(fullnames)
        gw1.set_info_order(shuffle=False)
        assert names(gw1.info(fullnames)) == fullnames

    def test_vanish_forever_and_for_n_calls(self, fake: FakeRedditGateway) -> None:
        a = fake.add_post("premiere", title="a", created_utc=T)
        b = fake.add_post("premiere", title="b", created_utc=T)
        fake.vanish(a)
        fake.vanish(b, times=2)
        assert names(fake.info([a, b])) == []
        assert names(fake.info([a, b])) == []
        assert names(fake.info([a, b])) == [b]
        fake.reappear(a)
        assert names(fake.info([a])) == [a]

    def test_vanish_hides_from_listing_tree_and_search_too(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        other = fake.add_post("premiere", title="Export fails too", created_utc=T + 1)
        fake.vanish(ids["c2"])
        assert ids["c2"] not in names(fake.fetch_tree(ids["post"], more_limit=0).comments)
        fake.vanish(ids["post"])
        assert names(next(fake.iter_new_pages("premiere", max_pages=1)).items) == [other]
        head = fake.new_head("premiere")
        assert head is not None
        assert head["name"] == other
        assert names(next(fake.search("export", sort="new", time_filter="all")).items) == [other]
        with pytest.raises(GatewayError):
            fake.fetch_tree(ids["post"], more_limit=0)
        fake.reappear(ids["post"])
        assert fake.fetch_tree(ids["post"], more_limit=0).post["name"] == ids["post"]

    def test_banned_subreddit_items_per_info_returns_flag(self, seeded: FakeRedditGateway) -> None:
        fn = seeded.add_post("premiere", title="x", created_utc=BASE + 10**6)
        seeded.ban_subreddit("premiere", info_returns=False)
        with pytest.raises(SubredditNotFound):
            seeded.about("premiere")
        with pytest.raises(SubredditNotFound):
            next(seeded.iter_new_pages("premiere", max_pages=1))
        assert seeded.info([fn]) == []
        seeded.ban_subreddit("premiere", info_returns=True)
        assert names(seeded.info([fn])) == [fn]
        seeded.set_status("premiere", "ok")
        assert seeded.about("premiere")["display_name"] == "premiere"

    def test_results_are_copies(self, fake: FakeRedditGateway) -> None:
        post = fake.add_post("premiere", title="x", created_utc=T)
        fake.info([post])[0]["title"] = "mutated"
        assert fake.info([post])[0]["title"] == "x"


# --------------------------------------------------------------------------- content state


class TestContentState:
    def test_delete_self_post(self, fake: FakeRedditGateway) -> None:
        fn = fake.add_post("premiere", title="t", selftext="secret", author="wes", created_utc=T)
        fake.delete(fn)
        (post,) = fake.info([fn])
        assert post["author"] == "[deleted]"
        assert "author_fullname" not in post
        assert post["selftext"] == "[deleted]"
        assert post["selftext_html"] is None
        assert post["removed_by_category"] == "deleted"
        assert post["title"] == "t"

    def test_delete_link_post_keeps_empty_selftext(self, fake: FakeRedditGateway) -> None:
        fn = fake.add_post("premiere", title="t", created_utc=T, is_self=False)
        fake.delete(bare(fn))
        (post,) = fake.info([fn])
        assert post["selftext"] == ""
        assert post["removed_by_category"] == "deleted"
        assert post["author"] == "[deleted]"

    def test_remove_post_records_category_under_either_spelling(
        self, fake: FakeRedditGateway
    ) -> None:
        a = fake.add_post("premiere", title="a", selftext="x", author="wes", created_utc=T)
        b = fake.add_post("premiere", title="b", selftext="y", author="wes", created_utc=T)
        c = fake.add_post("premiere", title="c", selftext="z", author="wes", created_utc=T)
        fake.remove(a)
        fake.remove(b, by="reddit")
        fake.remove(c, category="automod_filtered")
        pa, pb, pc = fake.info([a, b, c])
        assert pa["selftext"] == "[removed]"
        assert pa["removed_by_category"] == "moderator"
        assert pa["author"] == "wes"
        assert pb["removed_by_category"] == "reddit"
        assert pc["removed_by_category"] == "automod_filtered"
        assert fake.removals == {a: "moderator", b: "reddit", c: "automod_filtered"}

    def test_restore_brings_content_and_listing_back(self, fake: FakeRedditGateway) -> None:
        fn = fake.add_post("premiere", title="t", selftext="body", author="wes", created_utc=T)
        fake.remove(fn)
        assert next(fake.iter_new_pages("premiere", max_pages=1)).items == []
        fake.restore(fn)
        (post,) = fake.info([fn])
        assert post["selftext"] == "body"
        assert post["author"] == "wes"
        assert post["removed_by_category"] is None
        assert titles(next(fake.iter_new_pages("premiere", max_pages=1))) == ["t"]
        assert fn not in fake.removals

    def test_delete_account_scrubs_author_everywhere_keeps_content(
        self, fake: FakeRedditGateway
    ) -> None:
        mine = fake.add_post("premiere", title="mine", selftext="s", author="wes", created_utc=T)
        theirs = fake.add_post("premiere", title="theirs", author="bob", created_utc=T)
        c = fake.add_comment(theirs, body="hi", author="wes", created_utc=T)
        fake.delete_account("wes")
        post, other, comment = fake.info([mine, theirs, c])
        assert post["author"] == "[deleted]"
        assert "author_fullname" not in post
        assert post["selftext"] == "s"
        assert post["removed_by_category"] is None
        assert comment["author"] == "[deleted]"
        assert comment["body"] == "hi"
        assert other["author"] == "bob"
        assert len(next(fake.iter_new_pages("premiere", max_pages=1)).items) == 2

    def test_unknown_item_raises_key_error(self, fake: FakeRedditGateway) -> None:
        with pytest.raises(KeyError):
            fake.delete("t3_nope")
        with pytest.raises(KeyError):
            fake.remove("nope")


# ------------------------------------------------------------------------------- failures


class TestFailures:
    def test_fail_page_then_resume_from_cursor(self, seeded: FakeRedditGateway) -> None:
        seeded.fail_page("premiere", 2, TransientError("503"))
        pages = seeded.iter_new_pages("premiere", max_pages=10)
        first = next(pages)
        with pytest.raises(TransientError):
            next(pages)
        assert seeded.requests_made == 2  # the failed round-trip counts
        rest = list(seeded.iter_new_pages("premiere", max_pages=10, after=first.after))
        assert [len(p.items) for p in rest] == [100, 50]
        assert seeded.requests_made == 4

    def test_fail_page_times_and_exception_class(self, seeded: FakeRedditGateway) -> None:
        seeded.fail_page("premiere", 1, TransientError, times=2)
        for _ in range(2):
            with pytest.raises(TransientError):
                next(seeded.iter_new_pages("premiere", max_pages=1))
        assert len(next(seeded.iter_new_pages("premiere", max_pages=1)).items) == 100

    def test_fail_page_does_not_touch_other_pages_or_subs(self, seeded: FakeRedditGateway) -> None:
        seeded.add_post("editors", title="e", created_utc=BASE)
        seeded.fail_page("premiere", 3, TransientError)
        assert len(list(seeded.iter_new_pages("editors", max_pages=10))) == 1
        pages = seeded.iter_new_pages("premiere", max_pages=10)
        next(pages)
        next(pages)
        with pytest.raises(TransientError):
            next(pages)

    def test_rate_limit_next_hits_the_next_request_of_any_kind(
        self, seeded: FakeRedditGateway
    ) -> None:
        seeded.rate_limit_next(retry_after=37)
        with pytest.raises(RateLimited) as info:
            seeded.about("premiere")
        assert info.value.retry_after == 37
        assert seeded.about("premiere")["display_name"] == "premiere"
        assert seeded.requests_made == 2

    def test_rate_limit_twice_then_clear(self, seeded: FakeRedditGateway) -> None:
        seeded.rate_limit_next(retry_after=None, times=2)
        with pytest.raises(RateLimited) as first:
            next(seeded.iter_new_pages("premiere", max_pages=1))
        assert first.value.retry_after is None
        with pytest.raises(RateLimited):
            seeded.new_head("premiere")
        assert seeded.new_head("premiere") is not None

    def test_fail_next_applies_to_trees_and_info(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        fake.fail_next(TransientError("boom"), times=2)
        with pytest.raises(TransientError):
            fake.fetch_tree(ids["post"], more_limit=0)
        with pytest.raises(TransientError):
            fake.info([ids["post"]])
        assert fake.fetch_tree(ids["post"], more_limit=0).requests_used == 1

    def test_fail_info_hits_one_batch(self, fake: FakeRedditGateway) -> None:
        fullnames = [fake.add_post("premiere", title=str(i), created_utc=T + i) for i in range(250)]
        fake.fail_info(1, TransientError)
        with pytest.raises(TransientError):
            fake.info(fullnames)
        assert fake.requests_made == 2  # batch 0 served, batch 1 failed
        assert len(fake.info(fullnames)) == 250
        assert fake.requests_made == 5

    def test_html_403_once_by_default_or_until_cleared(self, seeded: FakeRedditGateway) -> None:
        seeded.set_html_403()
        with pytest.raises(HtmlBlocked):
            seeded.about("premiere")
        seeded.about("premiere")
        seeded.set_html_403(times=None)
        for _ in range(3):
            with pytest.raises(HtmlBlocked):
                seeded.about("premiere")
        seeded.set_html_403(times=0)
        assert seeded.about("premiere")["name"].startswith("t5_")
        assert seeded.requests_made == 6

    def test_auth_failed_surfaces_on_the_first_request(self, seeded: FakeRedditGateway) -> None:
        seeded.set_auth_failed()
        for _ in range(2):
            with pytest.raises(AuthFailed):
                seeded.about("premiere")
        assert seeded.requests_made == 2
        fresh = FakeRedditGateway()
        fresh.add_subreddit("premiere")
        fresh.set_auth_failed(times=1)
        with pytest.raises(AuthFailed):
            fresh.about("premiere")
        assert fresh.about("premiere")["display_name"] == "premiere"

    @pytest.mark.parametrize(
        ("status", "exc"),
        [
            ("forbidden", SubredditForbidden),
            ("not_found", SubredditNotFound),
            ("redirect", SubredditRedirected),
            ("quarantined", SubredditQuarantined),
        ],
    )
    def test_set_status_raises_on_every_touch_and_costs_a_request(
        self, seeded: FakeRedditGateway, status: str, exc: type[GatewayError]
    ) -> None:
        seeded.set_status("premiere", status)
        with pytest.raises(exc):
            seeded.about("premiere")
        with pytest.raises(exc):
            next(seeded.iter_new_pages("premiere", max_pages=1))
        with pytest.raises(exc):
            seeded.new_head("premiere")
        assert seeded.requests_made == 3
        seeded.set_status("premiere", "ok")
        assert seeded.about("premiere")["display_name"] == "premiere"

    def test_redirect_path_and_about_shape(self, seeded: FakeRedditGateway) -> None:
        seeded.set_status("premiere", "redirect", path="/subreddits/search?q=premiere")
        with pytest.raises(SubredditRedirected) as info:
            seeded.about("premiere")
        assert info.value.path == "/subreddits/search?q=premiere"
        seeded.set_status("premiere", "ok")
        about = seeded.about("Premiere")
        assert about["display_name"] == "premiere"
        assert about["display_name_prefixed"] == "r/premiere"
        assert about["subscribers"] == 120_000
        assert about["subreddit_type"] == "public"
        assert about["quarantine"] is False

    def test_set_status_scoped_to_one_sub_and_validates(self, seeded: FakeRedditGateway) -> None:
        seeded.add_subreddit("editors")
        seeded.set_status("editors", "forbidden")
        assert seeded.about("premiere")["display_name"] == "premiere"
        seeded.set_status("ghost", "not_found")  # unknown subs are created on the fly
        with pytest.raises(SubredditNotFound):
            seeded.about("ghost")
        with pytest.raises(ValueError, match="unknown status"):
            seeded.set_status("premiere", "banned")

    def test_injection_order_global_then_status_then_targeted(
        self, seeded: FakeRedditGateway
    ) -> None:
        seeded.set_html_403(times=1)
        seeded.rate_limit_next(retry_after=5)
        seeded.set_status("premiere", "forbidden")
        seeded.fail_page("premiere", 1, TransientError)
        expected: list[type[GatewayError]] = [
            HtmlBlocked,
            RateLimited,
            SubredditForbidden,
            SubredditForbidden,
        ]
        for exc in expected:
            with pytest.raises(exc):
                next(seeded.iter_new_pages("premiere", max_pages=1))
        seeded.set_status("premiere", "ok")
        with pytest.raises(TransientError):
            next(seeded.iter_new_pages("premiere", max_pages=1))
        assert len(next(seeded.iter_new_pages("premiere", max_pages=1)).items) == 100
        assert seeded.requests_made == 6

    def test_fail_tree_once_then_succeeds(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        fake.fail_tree(ids["post"], TransientError("timeout"))
        with pytest.raises(TransientError):
            fake.fetch_tree(ids["post"], more_limit=16)
        assert fake.requests_made == 1
        assert fake.fetch_tree(ids["post"], more_limit=16).complete is True

    def test_fail_tree_after_comments_counts_partial_expansions(
        self, fake: FakeRedditGateway
    ) -> None:
        ids = tree_scenario(fake)
        fake.fail_tree(ids["post"], CrashInjected("died mid-tree"), after_comments=5)
        with pytest.raises(CrashInjected):
            fake.fetch_tree(ids["post"], more_limit=16)
        assert fake.requests_made == 2  # base (4 visible) + one expansion reached 7 >= 5
        assert fake.fetch_tree(ids["post"], more_limit=16).complete is True

    def test_fail_tree_after_comments_never_reached_still_raises(
        self, fake: FakeRedditGateway
    ) -> None:
        ids = tree_scenario(fake)
        fake.fail_tree(ids["post"], TransientError, after_comments=99)
        with pytest.raises(TransientError):
            fake.fetch_tree(ids["post"], more_limit=16)
        assert fake.requests_made == 4

    def test_crash_after_pages_is_one_shot(self, seeded: FakeRedditGateway) -> None:
        seeded.crash_after("page", 2)
        pages = seeded.iter_new_pages("premiere", max_pages=10)
        assert len(next(pages).items) == 100
        assert len(next(pages).items) == 100
        with pytest.raises(CrashInjected):
            next(pages)
        assert seeded.requests_made == 2  # the crash happens before the third round-trip
        rerun = list(seeded.iter_new_pages("premiere", max_pages=10))
        assert [len(p.items) for p in rerun] == [100, 100, 50]

    def test_crash_after_trees_and_requests(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        fake.crash_after("tree", 1)
        fake.fetch_tree(ids["post"], more_limit=0)
        with pytest.raises(CrashInjected):
            fake.fetch_tree(ids["post"], more_limit=0)
        fake.fetch_tree(ids["post"], more_limit=0)
        fake.crash_after("request", 0)
        with pytest.raises(CrashInjected):
            fake.about("premiere")
        assert fake.about("premiere")["display_name"] == "premiere"
        with pytest.raises(ValueError, match="kind"):
            fake.crash_after("comment", 1)

    def test_crash_injected_is_not_a_gateway_error(self) -> None:
        assert not issubclass(CrashInjected, GatewayError)
        assert issubclass(CrashInjected, Exception)

    def test_block_on_parks_the_nth_operation_until_released(
        self, seeded: FakeRedditGateway
    ) -> None:
        release = threading.Event()
        seeded.block_on("about", 2, release, timeout=5)
        seeded.about("premiere")  # first call is not the one blocked
        results: list[str] = []
        worker = threading.Thread(
            target=lambda: results.append(seeded.about("premiere")["display_name"])
        )
        worker.start()
        worker.join(0.2)
        assert worker.is_alive()  # parked on the event
        assert results == []
        release.set()
        worker.join(5)
        assert not worker.is_alive()
        assert results == ["premiere"]
        assert seeded.about("premiere")["display_name"] == "premiere"  # third call runs freely

    def test_block_on_times_out_instead_of_hanging(self, seeded: FakeRedditGateway) -> None:
        seeded.block_on("about", 1, threading.Event(), timeout=0.01)
        with pytest.raises(TimeoutError, match="block_on"):
            seeded.about("premiere")
        assert seeded.requests_made == 0

    def test_on_call_runs_a_callback_when_the_nth_operation_begins(self) -> None:
        clock = FakeClock(1_000)
        gw = FakeRedditGateway(clock=clock)
        gw.add_subreddit("premiere")
        gw.on_call("about", 2, lambda: clock.advance(3_600))
        gw.about("premiere")
        assert clock.now() == 1_000
        gw.about("premiere")
        assert clock.now() == 4_600
        gw.about("premiere")
        assert clock.now() == 4_600
        with pytest.raises(ValueError, match="kind"):
            gw.on_call("listing", 1, lambda: None)

    def test_unconsumed_injections_are_reported(self) -> None:
        gw = FakeRedditGateway()
        gw.add_subreddit("premiere")
        gw.fail_page("premiere", 3, TransientError)
        gw.crash_after("tree", 1)
        gw.block_on("info", 1, threading.Event())
        gw.on_call("search", 1, lambda: None)
        gw.fail_tree("t3_x", TransientError)
        gw.fail_info(2, TransientError)
        gw.set_html_403()
        gw.rate_limit_next(30)
        with pytest.raises(AssertionError) as info:
            gw.assert_no_unconsumed_injections()
        message = str(info.value)
        for label in (
            "fail_page('premiere', 3)",
            "crash_after('tree', 1)",
            "block_on('info', 1)",
            "on_call('search', 1)",
            "fail_tree('t3_x')",
            "fail_info(2)",
            "set_html_403",
            "rate_limit_next",
        ):
            assert label in message

    def test_consumed_injections_pass_the_teardown_check(self) -> None:
        gw = FakeRedditGateway()
        gw.add_subreddit("premiere")
        gw.fail_next(TransientError)
        gw.set_status("premiere", "forbidden")  # a status is state, not a queued injection
        gw.set_auth_failed()  # forever, but fired once below
        with pytest.raises(TransientError):
            gw.about("premiere")
        with pytest.raises(AuthFailed):
            gw.about("premiere")
        gw.assert_no_unconsumed_injections()


# ----------------------------------------------------------------------------- accounting


class TestAccounting:
    def test_requests_per_operation(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        for i in range(150):
            fake.add_post("premiere", title=f"p{i}", created_utc=T + 100 + i)
        assert fake.requests_made == 0
        fake.about("premiere")
        assert fake.requests_made == 1
        fake.new_head("premiere")
        assert fake.requests_made == 2
        list(fake.iter_new_pages("premiere", max_pages=10))  # 151 posts -> 2 pages
        assert fake.requests_made == 4
        fake.fetch_tree(ids["post"], more_limit=2)  # 1 + 2 expansions
        assert fake.requests_made == 7
        fake.info([ids["post"], ids["c1"], ids["c2"]])
        assert fake.requests_made == 8
        fake.limits()
        assert fake.requests_made == 8
        assert fake.requests[0] == "GET /r/premiere/about"
        assert len(fake.requests) == 8

    def test_limits_none_until_first_request_then_derived_or_overridden(
        self, seeded: FakeRedditGateway
    ) -> None:
        assert seeded.limits() == Limits(remaining=None, used=None)
        seeded.about("premiere")
        seeded.about("premiere")
        assert seeded.limits() == Limits(remaining=998, used=2)
        seeded.set_limits(remaining=3, used=997)
        assert seeded.limits() == Limits(remaining=3, used=997)

    def test_calls_log_records_every_method_with_cost_and_seq(
        self, seeded: FakeRedditGateway
    ) -> None:
        seeded.about("premiere")
        pages = seeded.iter_new_pages("premiere", max_pages=2)  # logged at call time, lazily run
        seeded.new_head("premiere")
        seeded.info(["t3_a", "t3_b"])
        seeded.search("crash", sort="new", time_filter="week")
        seeded.limits()
        assert [(c.method, c.args, c.kwargs) for c in seeded.calls] == [
            ("about", ("premiere",), {}),
            ("iter_new_pages", ("premiere",), {"max_pages": 2, "after": None}),
            ("new_head", ("premiere",), {}),
            ("info", (["t3_a", "t3_b"],), {}),
            ("search", ("crash",), {"sort": "new", "time_filter": "week", "max_pages": 3}),
            ("limits", (), {}),
        ]
        assert [c.seq for c in seeded.calls] == [1, 2, 3, 4, 5, 6]
        assert [c.cost for c in seeded.calls] == [1, 0, 1, 1, 0, 0]
        assert seeded.calls[0] == Call("about", ("premiere",), {}, 1, 1)
        assert seeded.calls[0] == ("about", ("premiere",), {}, 1, 1)
        assert seeded.requests_made == 3  # neither iterator has been consumed
        list(pages)
        assert seeded.calls[1].cost == 2
        assert seeded.requests_made == 5

    def test_count_and_fullnames_requested(self, fake: FakeRedditGateway) -> None:
        ids = tree_scenario(fake)
        fake.info([ids["post"], ids["c1"]])
        fake.info([ids["c2"]])
        fake.fetch_tree(bare(ids["post"]), more_limit=0)
        fake.about("premiere")
        assert fake.count("info") == 2
        assert fake.count("fetch_tree") == 1
        assert fake.count("search") == 0
        assert fake.fullnames_requested("info") == [ids["post"], ids["c1"], ids["c2"]]
        assert fake.fullnames_requested("fetch_tree") == [ids["post"]]
        assert fake.fullnames_requested("about") == ["premiere"]


# --------------------------------------------------------------------------------- search


class TestSearch:
    def test_matches_all_terms_newest_first_excluding_deleted(
        self, fake: FakeRedditGateway
    ) -> None:
        fake.add_post("premiere", title="Export crash on 2024", created_utc=T)
        fake.add_post("editors", title="crash", selftext="during export", created_utc=T + 1)
        gone = fake.add_post("premiere", title="export crash again", created_utc=T + 2)
        fake.add_post("premiere", title="export works", created_utc=T + 3)
        fake.delete(gone)
        pages = list(fake.search("Export CRASH", sort="new", time_filter="all"))
        assert len(pages) == 1
        assert titles(pages[0]) == ["crash", "Export crash on 2024"]
        assert pages[0].complete is True
        assert fake.requests_made == 1

    def test_time_filter_applies_only_with_a_clock(self) -> None:
        with_clock = FakeRedditGateway(clock=FakeClock(int(T)))
        without = FakeRedditGateway()
        for gw in (with_clock, without):
            gw.add_post("premiere", title="old crash", created_utc=T - 30 * 86_400)
            gw.add_post("premiere", title="new crash", created_utc=T - 60)
        recent = next(with_clock.search("crash", sort="new", time_filter="week"))
        assert titles(recent) == ["new crash"]
        assert len(next(without.search("crash", sort="new", time_filter="week")).items) == 2
        with pytest.raises(ValueError, match="time_filter"):
            without.search("crash", sort="new", time_filter="fortnight")

    def test_pages_cap_max_pages_and_top_sort(self, fake: FakeRedditGateway) -> None:
        for i in range(SEARCH_CAP + 10):
            fake.add_post("premiere", title=f"crash {i}", created_utc=T + i, score=i % 10)
        pages = list(fake.search("crash", sort="new", time_filter="all"))
        assert [len(p.items) for p in pages] == [100, 100, 50]  # capped at 250 results
        assert pages[0].after is not None
        assert pages[-1].after is None
        assert pages[-1].complete is True
        one = list(fake.search("crash", sort="new", time_filter="all", max_pages=1))
        assert len(one) == 1
        assert one[0].complete is False
        top = next(fake.search("crash", sort="top", time_filter="all"))
        assert top.items[0]["score"] == 9
        assert top.items[0]["title"] == f"crash {SEARCH_CAP + 9}"


# -------------------------------------------------------------------------------- fixture


FIXTURE: dict[str, Any] = {
    "version": 1,
    "subreddits": [
        {
            "display_name": "premiere",
            "name": "t5_2qh1u",
            "subscribers": 120000,
            "subreddit_type": "public",
            "over18": False,
        }
    ],
    "posts": [
        {
            "id": "1abc2d3",
            "subreddit": "premiere",
            "title": "Timeline lags",
            "selftext": "since 25.1",
            "author": "someone",
            "author_fullname": "t2_abc",
            "created_utc": 1757000000.0,
            "num_comments": 3,
        },
        {
            "id": "1abc2d4",
            "subreddit": "premiere",
            "title": "gone",
            "selftext": "[deleted]",
            "author": "[deleted]",
            "created_utc": 1757000100.0,
            "removed_by_category": "deleted",
        },
        {
            "id": "1abc2d5",
            "subreddit": "VideoEditing",
            "title": "auto-created sub",
            "selftext": "",
            "author": "x",
            "created_utc": 1757000200.0,
        },
    ],
    "comments": [
        {
            "id": "c000001",
            "link_id": "t3_1abc2d3",
            "parent_id": "t3_1abc2d3",
            "body": "same here",
            "author": "a",
            "created_utc": 1757000010.0,
            "depth": 0,
        },
        {
            "id": "c000002",
            "link_id": "t3_1abc2d3",
            "parent_id": "t1_c000001",
            "body": "me too",
            "author": "b",
            "created_utc": 1757000020.0,
            "depth": 1,
        },
        {
            "id": "c000003",
            "link_id": "t3_1abc2d3",
            "parent_id": "t3_1abc2d3",
            "body": "hidden",
            "author": "c",
            "created_utc": 1757000030.0,
        },
    ],
    "more": [{"post_id": "1abc2d3", "parent_fullname": None, "count": 1, "children": ["c000003"]}],
}


class TestFixture:
    def test_load_from_json(self, tmp_path: Path) -> None:
        path = tmp_path / "scenario.json"
        path.write_text(json.dumps(FIXTURE), encoding="utf-8")
        fake = FakeRedditGateway.from_fixture(path)

        about = fake.about("premiere")
        assert about["name"] == "t5_2qh1u"
        assert about["subscribers"] == 120000
        assert fake.about("videoediting")["display_name"] == "VideoEditing"

        page = next(fake.iter_new_pages("premiere", max_pages=1))
        assert titles(page) == ["Timeline lags"]  # the deleted post dropped out of /new
        assert page.items[0]["name"] == "t3_1abc2d3"
        assert page.items[0]["subreddit_id"] == "t5_2qh1u"
        assert page.items[0]["num_comments"] == 3  # kept as captured, not recounted

        tree = fake.fetch_tree("1abc2d3", more_limit=0)
        assert [(c["body"], c["depth"]) for c in tree.comments] == [("same here", 0), ("me too", 1)]
        assert tree.more == [MoreStub("t3_1abc2d3", 1, ["c000003"])]
        assert fake.fetch_tree("1abc2d3", more_limit=1).complete is True

        got = fake.info(["t3_1abc2d4", "t1_c000001", "t3_nope"])
        assert names(got) == ["t3_1abc2d4", "t1_c000001"]
        assert "depth" not in got[1]
        assert got[0]["removed_by_category"] == "deleted"

    def test_sections_optional_and_version_checked(self, tmp_path: Path) -> None:
        empty = tmp_path / "empty.json"
        empty.write_text("{}", encoding="utf-8")
        fake = FakeRedditGateway.from_fixture(empty)
        assert fake.requests_made == 0
        bad = tmp_path / "bad.json"
        bad.write_text(json.dumps({"version": 2}), encoding="utf-8")
        with pytest.raises(ValueError, match="version"):
            FakeRedditGateway.from_fixture(bad)

    def test_load_fixture_merges_into_existing_scenario(self, tmp_path: Path) -> None:
        path = tmp_path / "scenario.json"
        path.write_text(json.dumps(FIXTURE), encoding="utf-8")
        fake = FakeRedditGateway()
        fake.add_post("premiere", title="built by hand", created_utc=1757000300.0)
        fake.load_fixture(path)
        page = next(fake.iter_new_pages("premiere", max_pages=1))
        assert titles(page) == ["built by hand", "Timeline lags"]

    def test_to_fixture_round_trips_the_world(self, tmp_path: Path) -> None:
        source = FakeRedditGateway()
        ids = tree_scenario(source)
        source.add_subreddit("premiere", subscribers=42, t5="t5_prem")
        deleted = source.add_post("premiere", title="gone", selftext="x", created_utc=T + 100)
        source.delete(deleted)
        source.remove(ids["c2"])
        path = tmp_path / "world.json"
        source.to_fixture(path)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["version"] == 1
        assert {s["display_name"] for s in data["subreddits"]} == {"premiere"}
        assert len(data["posts"]) == 2
        assert len(data["comments"]) == 9
        assert len(data["more"]) == 3

        clone = FakeRedditGateway.from_fixture(path)
        assert clone.about("premiere")["name"] == "t5_prem"
        assert clone.about("premiere")["subscribers"] == 42
        assert titles(next(clone.iter_new_pages("premiere", max_pages=1))) == ["Export fails"]
        original = source.fetch_tree(ids["post"], more_limit=16)
        copied = clone.fetch_tree(ids["post"], more_limit=16)
        assert [(c["name"], c["body"], c["depth"]) for c in copied.comments] == [
            (c["name"], c["body"], c["depth"]) for c in original.comments
        ]
        assert copied.post["num_comments"] == original.post["num_comments"]
        assert (
            clone.fetch_tree(ids["post"], more_limit=0).more
            == source.fetch_tree(ids["post"], more_limit=0).more
        )
        assert clone.info([deleted])[0]["removed_by_category"] == "deleted"
        assert clone.removals[ids["c2"]] == "moderator"
