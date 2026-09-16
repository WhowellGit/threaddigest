"""Contract tests for the normalized row models in ``threaddigest.core.models``.

The rows are the only shape that crosses the normalize boundary, so these tests pin the
contract other layers rely on: strict types (no silent coercion), every column required
(no silent NULL defaults), lowercase subreddit identity, and the unknown-enum registry.
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from threaddigest.core.models import (
    KNOWN_VALUES,
    NORMALIZER_VERSION,
    UNKNOWN_ENUM_COUNTER,
    CommentRow,
    CrosspostParent,
    KnownValues,
    PostRow,
    Reject,
    count_unknown,
)

POST_KWARGS: dict[str, Any] = {
    "reddit_id": "1abc2de",
    "fullname": "t3_1abc2de",
    "subreddit": "premiere",
    "subreddit_id": "t5_2s9fq",
    "author": "editorguy",
    "author_fullname": "t2_abcd12",
    "author_flair_text": None,
    "author_is_bot": False,
    "title": "Premiere crashes on export",
    "selftext": "",
    "selftext_html": "",
    "url": "https://example.com/x",
    "domain": "example.com",
    "permalink": "/r/premiere/comments/1abc2de/premiere_crashes_on_export/",
    "created_utc": 1757649600,
    "edited_utc": None,
    "score": 128,
    "upvote_ratio": 0.94,
    "num_comments": 84,
    "link_flair_text": "Bug",
    "over_18": False,
    "spoiler": False,
    "is_self": False,
    "is_video": False,
    "is_gallery": False,
    "post_hint": "link",
    "locked": False,
    "stickied": False,
    "archived": False,
    "distinguished": None,
    "crosspost_parent": None,
    "num_crossposts": 0,
    "removed_by_category": None,
    "source": "r/premiere/new",
}

COMMENT_KWARGS: dict[str, Any] = {
    "reddit_id": "k1m2n3o",
    "fullname": "t1_k1m2n3o",
    "post_reddit_id": "1abc2de",
    "parent_fullname": "t3_1abc2de",
    "author": "helper_hank",
    "author_fullname": "t2_zz99yy",
    "author_is_bot": False,
    "body": "Try turning off hardware encoding.",
    "body_html": "<p>Try turning off hardware encoding.</p>\n",
    "created_utc": 1757653800,
    "edited_utc": None,
    "score": 45,
    "depth": 0,
    "permalink": "/r/premiere/comments/1abc2de/_/k1m2n3o/",
    "is_submitter": False,
    "stickied": False,
    "distinguished": None,
    "source": "comments",
}


def make_post(**overrides: Any) -> PostRow:
    return PostRow(**{**POST_KWARGS, **overrides})


def make_comment(**overrides: Any) -> CommentRow:
    return CommentRow(**{**COMMENT_KWARGS, **overrides})


# --- constants -----------------------------------------------------------------------------


def test_normalizer_version_is_defined_once_as_the_integer_one() -> None:
    assert NORMALIZER_VERSION == 1
    assert type(NORMALIZER_VERSION) is int


def test_unknown_enum_counter_is_the_run_counter_name_from_the_plan() -> None:
    assert UNKNOWN_ENUM_COUNTER == "unknown_enum_values"


# --- PostRow ------------------------------------------------------------------------------


def test_post_row_round_trips_every_column() -> None:
    row = make_post()
    dumped = row.model_dump()
    for key, value in POST_KWARGS.items():
        assert dumped[key] == value, key
    assert dumped["normalizer_version"] == NORMALIZER_VERSION


def test_post_row_stamps_current_normalizer_version_by_default() -> None:
    assert make_post().normalizer_version == NORMALIZER_VERSION
    assert make_post(normalizer_version=0).normalizer_version == 0


def test_post_row_lowercases_subreddit_identity() -> None:
    assert make_post(subreddit="VideoEditing").subreddit == "videoediting"


def test_post_row_is_frozen() -> None:
    row = make_post()
    with pytest.raises(ValidationError):
        row.score = 1  # type: ignore[misc]


def test_post_row_forbids_unknown_columns() -> None:
    with pytest.raises(ValidationError):
        make_post(raw_json="{}")


@pytest.mark.parametrize(
    ("field", "bad_value"),
    [
        ("score", "128"),  # str -> int is the wire-drift the normalizer must own
        ("score", 128.0),  # float -> int
        ("over_18", 0),  # int -> bool
        ("created_utc", 1757649600.0),  # epoch must already be an int
        ("title", 42),
        ("upvote_ratio", "0.9"),
    ],
)
def test_post_row_is_strict_and_never_coerces(field: str, bad_value: Any) -> None:
    with pytest.raises(ValidationError):
        make_post(**{field: bad_value})


@pytest.mark.parametrize("field", sorted(POST_KWARGS))
def test_post_row_requires_every_column_explicitly(field: str) -> None:
    """No silent defaults: a producer that forgets a column fails loudly, not with NULLs."""
    kwargs = dict(POST_KWARGS)
    del kwargs[field]
    with pytest.raises(ValidationError):
        PostRow(**kwargs)


@pytest.mark.parametrize("field", ["reddit_id", "fullname", "subreddit", "source"])
def test_post_row_identity_and_provenance_fields_must_be_non_empty(field: str) -> None:
    with pytest.raises(ValidationError):
        make_post(**{field: ""})


def test_post_row_optional_columns_accept_none() -> None:
    row = make_post(
        author=None,
        author_fullname=None,
        title=None,
        selftext=None,
        selftext_html=None,
        score=None,
        upvote_ratio=None,
        over_18=None,
        post_hint=None,
        removed_by_category=None,
    )
    assert row.author is None
    assert row.score is None


# --- CrosspostParent ----------------------------------------------------------------------


def test_crosspost_parent_holds_only_id_and_subreddit() -> None:
    parent = CrosspostParent(id="zzz111", subreddit="Premiere")
    assert parent.model_dump() == {"id": "zzz111", "subreddit": "premiere"}


@pytest.mark.parametrize("leak", ["title", "selftext", "author", "url"])
def test_crosspost_parent_refuses_parent_text(leak: str) -> None:
    with pytest.raises(ValidationError):
        CrosspostParent(**{"id": "zzz111", "subreddit": "premiere", leak: "content"})


def test_crosspost_parent_subreddit_may_be_unknown() -> None:
    assert CrosspostParent(id="zzz111", subreddit=None).subreddit is None


def test_post_row_embeds_crosspost_parent() -> None:
    row = make_post(crosspost_parent=CrosspostParent(id="zzz111", subreddit="premiere"))
    assert row.crosspost_parent is not None
    assert row.crosspost_parent.id == "zzz111"


# --- CommentRow ---------------------------------------------------------------------------


def test_comment_row_round_trips_every_column() -> None:
    dumped = make_comment().model_dump()
    for key, value in COMMENT_KWARGS.items():
        assert dumped[key] == value, key
    assert dumped["normalizer_version"] == NORMALIZER_VERSION


@pytest.mark.parametrize("field", sorted(COMMENT_KWARGS))
def test_comment_row_requires_every_column_explicitly(field: str) -> None:
    kwargs = dict(COMMENT_KWARGS)
    del kwargs[field]
    with pytest.raises(ValidationError):
        CommentRow(**kwargs)


def test_comment_row_is_frozen_and_strict() -> None:
    row = make_comment()
    with pytest.raises(ValidationError):
        row.body = "x"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        make_comment(depth="0")


# --- Reject ------------------------------------------------------------------------------


def test_reject_holds_raw_and_error() -> None:
    raw = {"id": "x", "score": 1}
    rej = Reject(raw=raw, error="created_utc: required key missing")
    assert rej.raw == raw
    assert rej.error.startswith("created_utc")


def test_reject_requires_an_error_message() -> None:
    with pytest.raises(ValidationError):
        Reject(raw={}, error="")


# --- KnownValues / count_unknown ---------------------------------------------------------


def test_registry_covers_the_three_upstream_enums() -> None:
    assert set(KNOWN_VALUES.fields) == {"post_hint", "subreddit_type", "removed_by_category"}


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("post_hint", "link"),
        ("post_hint", "hosted:video"),
        ("subreddit_type", "public"),
        ("removed_by_category", "deleted"),
        ("removed_by_category", "moderator"),
        ("removed_by_category", "reddit"),
    ],
)
def test_registry_knows_observed_values(field: str, value: str) -> None:
    assert KNOWN_VALUES.is_known(field, value)


def test_registry_is_exact_match_not_case_folded() -> None:
    assert not KNOWN_VALUES.is_known("post_hint", "Link")
    assert not KNOWN_VALUES.is_known("removed_by_category", "hologram")


def test_registry_raises_for_an_unregistered_field() -> None:
    with pytest.raises(KeyError):
        KNOWN_VALUES.is_known("distinguished", "moderator")


def test_registry_can_be_extended_locally() -> None:
    reg = KnownValues({"post_hint": ["link"]})
    assert reg.fields == ("post_hint",)
    assert reg.known("post_hint") == frozenset({"link"})
    assert reg.is_known("post_hint", "link") and not reg.is_known("post_hint", "self")


def test_count_unknown_is_empty_for_known_or_missing_values() -> None:
    assert count_unknown(make_post(post_hint="link", removed_by_category="moderator")) == []
    assert count_unknown(make_post(post_hint=None, removed_by_category=None)) == []


def test_count_unknown_names_field_and_raw_value() -> None:
    row = make_post(post_hint="hologram", removed_by_category="new_reason")
    assert count_unknown(row) == ["post_hint=hologram", "removed_by_category=new_reason"]
    # the raw value is stored untouched, never coerced to a known one
    assert row.post_hint == "hologram"


def test_count_unknown_on_comment_rows_is_empty() -> None:
    assert count_unknown(make_comment()) == []


def test_count_unknown_accepts_a_custom_registry() -> None:
    reg = KnownValues({"post_hint": ["hologram"]})
    assert count_unknown(make_post(post_hint="hologram"), reg) == []
    assert count_unknown(make_post(post_hint="link"), reg) == ["post_hint=link"]
