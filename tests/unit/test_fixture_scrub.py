"""The fixture scrub: every author name and account id replaced, everything else kept."""

from __future__ import annotations

import copy

from threaddigest.core import fixture_scrub as fs

PAYLOAD = {
    "posts": [
        {
            "id": "abc123",
            "name": "t3_abc123",
            "author": "real_person_one",
            "author_fullname": "t2_9zq8x",
            "title": "Premiere crashes on export",
            "selftext": "It happens every time.",
            "subreddit_id": "t5_2qh1o",
            "score": 12,
            "crosspost_parent_list": [{"author": "real_person_two", "author_fullname": "t2_77abc"}],
        },
        {"id": "def456", "author": "[deleted]", "removed_by_category": "deleted", "selftext": ""},
        {
            "id": "ghi789",
            "author": "AutoModerator",
            "author_fullname": "t2_6l4z3",
            "title": "Weekly",
        },
    ],
    "comments": [
        {
            "id": "c1",
            "link_id": "t3_abc123",
            "author": "real_person_one",
            "author_fullname": "t2_9zq8x",
        },
        {"id": "c2", "link_id": "t3_abc123", "author": "real_person_two", "body": "[removed]"},
        {"id": "c3", "link_id": "t3_abc123", "author": "[deleted]", "body": "[deleted]"},
    ],
}


def test_names_and_ids_are_replaced_consistently_and_everything_else_is_kept() -> None:
    before = copy.deepcopy(PAYLOAD)
    out = fs.scrub(PAYLOAD)
    assert PAYLOAD == before  # pure: the input is not mutated
    posts, comments = out["posts"], out["comments"]
    assert posts[0]["author"] == "fx_user_1"
    assert posts[0]["author_fullname"] == "t2_fx1"  # the id beside the name takes its number
    parent = posts[0]["crosspost_parent_list"][0]
    assert parent == {"author": "fx_user_2", "author_fullname": "t2_fx2"}
    assert comments[0]["author"] == "fx_user_1"
    assert comments[0]["author_fullname"] == "t2_fx1"  # the same person across posts and comments
    assert comments[1]["author"] == "fx_user_2"
    # Kept: the wire markers, the bot, and every non-author field.
    assert posts[1] == {
        "id": "def456",
        "author": "[deleted]",
        "removed_by_category": "deleted",
        "selftext": "",
    }
    assert posts[2]["author"] == "AutoModerator"
    assert posts[2]["author_fullname"] == "t2_fx3"  # a bot's id is still an account id
    assert comments[2] == {
        "id": "c3",
        "link_id": "t3_abc123",
        "author": "[deleted]",
        "body": "[deleted]",
    }
    assert posts[0]["title"] == "Premiere crashes on export"
    assert posts[0]["subreddit_id"] == "t5_2qh1o" and posts[0]["name"] == "t3_abc123"


def test_scrubbing_is_idempotent() -> None:
    once = fs.scrub(PAYLOAD)
    assert fs.scrub(once) == once


def test_offending_values_finds_real_names_and_ids_and_nothing_in_a_scrubbed_payload() -> None:
    assert fs.offending_values(PAYLOAD) == [
        "real_person_one",
        "t2_9zq8x",
        "real_person_two",
        "t2_77abc",
        "t2_6l4z3",
        "real_person_one",
        "t2_9zq8x",
        "real_person_two",
    ]
    assert fs.offending_values(fs.scrub(PAYLOAD)) == []
    assert fs.offending_values({"author": "[deleted]", "link_author": "fx_user_9"}) == []


def test_a_lone_id_without_a_name_gets_its_own_number() -> None:
    raw = {"data": {"author_fullname": "t2_abc", "author": "someone"}, "extra": ["t2_zzz"]}
    scrubbed = {"data": {"author_fullname": "t2_fx1", "author": "fx_user_1"}, "extra": ["t2_fx2"]}
    assert fs.scrub(raw) == scrubbed
