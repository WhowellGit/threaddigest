"""Exhaustive table and property tests for the content/author state machine."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from insightminer.core.deletion import (
    GONE_AT_MISSES,
    REDDIT_REMOVAL_CATEGORIES,
    SCRUB_STATES,
    AuthorState,
    ContentState,
    Decision,
    Observation,
    decide,
)

LIVE = ContentState.LIVE
DEL = ContentState.DELETED_BY_AUTHOR
MOD = ContentState.REMOVED_BY_MODERATOR
RED = ContentState.REMOVED_BY_REDDIT
UNC = ContentState.GONE_UNCONFIRMED
GONE = ContentState.GONE
KNOWN = AuthorState.KNOWN
ACCT = AuthorState.ACCOUNT_DELETED


def obs(
    body: str | None = "intact text",
    author: str | None = "alice",
    fullname: bool = True,
    category: str | None = None,
    link: bool = False,
    info: bool | None = None,
) -> Observation:
    return Observation(
        body=body,
        author=author,
        author_fullname_present=fullname,
        removed_by_category=category,
        is_link_post=link,
        returned_by_info=info,
    )


ABSENT = obs(body=None, author=None, fullname=False, info=False)
DELETED_LINK = obs(body="", author=None, fullname=False, category="deleted", link=True)
LINK_HOLD = obs(body="", author=None, fullname=False, link=True)

# (label, prior_state, prior_author, observation, misses) -> (state, author, scrub, misses)
TABLE: list[tuple[str, ContentState, AuthorState, Observation, int, Decision]] = [
    # deleted_by_author is terminal
    ("terminal ignores live", DEL, KNOWN, obs(), 0, Decision(DEL, KNOWN, False, 0)),
    ("terminal ignores info absence", DEL, KNOWN, ABSENT, 1, Decision(DEL, KNOWN, False, 1)),
    ("terminal keeps author", DEL, ACCT, obs(body="[removed]"), 0, Decision(DEL, ACCT, False, 0)),
    # removed_by_category == 'deleted' is keyed on first
    ("deleted link post", LIVE, KNOWN, DELETED_LINK, 0, Decision(DEL, KNOWN, True, 0)),
    (
        "category deleted beats [removed]",
        LIVE,
        KNOWN,
        obs(body="[removed]", category="deleted"),
        0,
        Decision(DEL, KNOWN, True, 0),
    ),
    (
        "category deleted beats intact body",
        LIVE,
        KNOWN,
        obs(category="deleted"),
        0,
        Decision(DEL, KNOWN, True, 0),
    ),
    (
        "category deleted beats absent body",
        LIVE,
        KNOWN,
        obs(body=None, category="deleted"),
        0,
        Decision(DEL, KNOWN, True, 0),
    ),
    (
        "held link post confirmed deleted by info()",
        UNC,
        KNOWN,
        obs(body="", author=None, fullname=False, category="deleted", link=True, info=True),
        1,
        Decision(DEL, KNOWN, True, 0),
    ),
    # body == "[deleted]"
    (
        "[deleted] body",
        LIVE,
        KNOWN,
        obs(body="[deleted]", author=None, fullname=False),
        0,
        Decision(DEL, KNOWN, True, 0),
    ),
    (
        "[deleted] body is not evidence of account deletion",
        LIVE,
        KNOWN,
        obs(body="[deleted]", author=None, fullname=False),
        0,
        Decision(DEL, KNOWN, True, 0),
    ),
    (
        "[deleted] after moderator removal scrubs nothing new",
        MOD,
        KNOWN,
        obs(body="[deleted]"),
        0,
        Decision(DEL, KNOWN, False, 0),
    ),
    (
        "[deleted] beats moderator category",
        LIVE,
        KNOWN,
        obs(body="[deleted]", category="moderator"),
        0,
        Decision(DEL, KNOWN, True, 0),
    ),
    (
        "[deleted] keeps author state",
        LIVE,
        ACCT,
        obs(body="[deleted]"),
        0,
        Decision(DEL, ACCT, True, 0),
    ),
    # body == "[removed]"
    ("[removed] no category", LIVE, KNOWN, obs(body="[removed]"), 0, Decision(MOD, KNOWN, True, 0)),
    (
        "[removed] moderator",
        LIVE,
        KNOWN,
        obs(body="[removed]", category="moderator"),
        0,
        Decision(MOD, KNOWN, True, 0),
    ),
    *[
        (
            f"[removed] reddit-side category {cat}",
            LIVE,
            KNOWN,
            obs(body="[removed]", category=cat),
            0,
            Decision(RED, KNOWN, True, 0),
        )
        for cat in sorted(REDDIT_REMOVAL_CATEGORIES)
    ],
    (
        "[removed] unknown category fails closed",
        LIVE,
        KNOWN,
        obs(body="[removed]", category="brand_new_value"),
        0,
        Decision(RED, KNOWN, True, 0),
    ),
    (
        "[removed] category author is not in the known lists",
        LIVE,
        KNOWN,
        obs(body="[removed]", category="author"),
        0,
        Decision(RED, KNOWN, True, 0),
    ),
    (
        "[removed] again after removal scrubs nothing new",
        MOD,
        KNOWN,
        obs(body="[removed]", category="moderator"),
        0,
        Decision(MOD, KNOWN, False, 0),
    ),
    (
        "moderator to reddit removal scrubs nothing new",
        MOD,
        KNOWN,
        obs(body="[removed]", category="reddit"),
        0,
        Decision(RED, KNOWN, False, 0),
    ),
    (
        "held item observed removed settles and resets misses",
        UNC,
        KNOWN,
        obs(body="[removed]"),
        1,
        Decision(MOD, KNOWN, True, 0),
    ),
    (
        "[removed] keeps author state",
        LIVE,
        ACCT,
        obs(body="[removed]"),
        0,
        Decision(MOD, ACCT, True, 0),
    ),
    # removed_* returns to live only with intact content and no category
    ("moderator removal re-approved", MOD, KNOWN, obs(), 0, Decision(LIVE, KNOWN, False, 0)),
    ("reddit removal reversed", RED, KNOWN, obs(), 0, Decision(LIVE, KNOWN, False, 0)),
    (
        "intact body with moderator category stays removed",
        MOD,
        KNOWN,
        obs(category="moderator"),
        0,
        Decision(MOD, KNOWN, False, 0),
    ),
    (
        "removed link post has empty selftext, category decides",
        LIVE,
        KNOWN,
        obs(body="", category="moderator", link=True),
        0,
        Decision(MOD, KNOWN, True, 0),
    ),
    (
        "intact body, reddit category",
        LIVE,
        KNOWN,
        obs(category="reddit"),
        0,
        Decision(RED, KNOWN, True, 0),
    ),
    (
        "intact body, unknown category fails closed",
        LIVE,
        KNOWN,
        obs(category="weird"),
        0,
        Decision(RED, KNOWN, True, 0),
    ),
    # account deleted, content kept
    (
        "author None, fullname absent, intact self body",
        LIVE,
        KNOWN,
        obs(author=None, fullname=False),
        0,
        Decision(LIVE, ACCT, False, 0),
    ),
    (
        "account_deleted persists",
        LIVE,
        ACCT,
        obs(author=None, fullname=False),
        0,
        Decision(LIVE, ACCT, False, 0),
    ),
    (
        "author visible again returns to known",
        LIVE,
        ACCT,
        obs(author="alice", fullname=True),
        0,
        Decision(LIVE, KNOWN, False, 0),
    ),
    (
        "author None but fullname present is inconclusive",
        LIVE,
        KNOWN,
        obs(author=None, fullname=True),
        0,
        Decision(LIVE, KNOWN, False, 0),
    ),
    (
        "author visible but fullname absent is inconclusive",
        LIVE,
        ACCT,
        obs(author="bob", fullname=False),
        0,
        Decision(LIVE, ACCT, False, 0),
    ),
    (
        "comment author None, intact body, removed state re-approved",
        MOD,
        KNOWN,
        obs(author=None, fullname=False),
        0,
        Decision(LIVE, ACCT, False, 0),
    ),
    # author None on a link post with no category: hold, never live
    ("link post author None: hold", LIVE, KNOWN, LINK_HOLD, 0, Decision(UNC, KNOWN, False, 1)),
    (
        "link post hold does not escalate without info() absence",
        LIVE,
        KNOWN,
        LINK_HOLD,
        1,
        Decision(UNC, KNOWN, False, 2),
    ),
    (
        "link post hold confirmed present by info() but still authorless",
        UNC,
        KNOWN,
        obs(body="", author=None, fullname=False, link=True, info=True),
        1,
        Decision(UNC, KNOWN, False, 2),
    ),
    (
        "link post with author is live",
        LIVE,
        KNOWN,
        obs(body="", link=True),
        0,
        Decision(LIVE, KNOWN, False, 0),
    ),
    (
        "link post author None but fullname present still holds",
        LIVE,
        KNOWN,
        obs(body="", author=None, fullname=True, link=True),
        0,
        Decision(UNC, KNOWN, False, 1),
    ),
    # info() did not return the item
    ("first miss", LIVE, KNOWN, ABSENT, 0, Decision(UNC, KNOWN, False, 1)),
    ("second miss is gone with scrub", UNC, KNOWN, ABSENT, 1, Decision(GONE, KNOWN, True, 2)),
    ("gone stays gone", GONE, KNOWN, ABSENT, 2, Decision(GONE, KNOWN, False, 3)),
    ("removed item missing from info()", MOD, KNOWN, ABSENT, 0, Decision(UNC, KNOWN, False, 1)),
    (
        "miss counter is taken from the caller",
        UNC,
        KNOWN,
        ABSENT,
        0,
        Decision(UNC, KNOWN, False, 1),
    ),
    ("live with a prior miss goes gone", LIVE, KNOWN, ABSENT, 1, Decision(GONE, KNOWN, True, 2)),
    (
        "already scrubbed item going gone scrubs nothing new",
        RED,
        KNOWN,
        ABSENT,
        1,
        Decision(GONE, KNOWN, False, 2),
    ),
    (
        "info absence ignores other fields",
        LIVE,
        KNOWN,
        obs(info=False),
        0,
        Decision(UNC, KNOWN, False, 1),
    ),
    ("info absence keeps author state", LIVE, ACCT, ABSENT, 0, Decision(UNC, ACCT, False, 1)),
    # a later successful observation resets misses
    ("held item returns live", UNC, KNOWN, obs(info=True), 1, Decision(LIVE, KNOWN, False, 0)),
    ("gone item reappears live", GONE, KNOWN, obs(info=True), 2, Decision(LIVE, KNOWN, False, 0)),
    ("held item observed via sweep", UNC, KNOWN, obs(), 1, Decision(LIVE, KNOWN, False, 0)),
    # body None (key absent) is never live
    ("absent body holds", LIVE, KNOWN, obs(body=None), 0, Decision(UNC, KNOWN, False, 1)),
    (
        "absent body never escalates to gone on its own",
        UNC,
        KNOWN,
        obs(body=None, info=True),
        1,
        Decision(UNC, KNOWN, False, 2),
    ),
    (
        "absent body with category",
        LIVE,
        KNOWN,
        obs(body=None, category="moderator"),
        0,
        Decision(MOD, KNOWN, True, 0),
    ),
    ("absent body after removal", MOD, KNOWN, obs(body=None), 0, Decision(UNC, KNOWN, False, 1)),
    (
        "absent body after gone stays gone",
        GONE,
        KNOWN,
        obs(body=None),
        2,
        Decision(GONE, KNOWN, False, 3),
    ),
    # empty string is intact content (link posts, empty self posts)
    ("empty selftext is live", LIVE, KNOWN, obs(body=""), 0, Decision(LIVE, KNOWN, False, 0)),
    # markers are matched exactly
    (
        "marker match is exact",
        LIVE,
        KNOWN,
        obs(body="[Deleted]"),
        0,
        Decision(LIVE, KNOWN, False, 0),
    ),
    (
        "marker with whitespace is text",
        LIVE,
        KNOWN,
        obs(body=" [removed]"),
        0,
        Decision(LIVE, KNOWN, False, 0),
    ),
]


@pytest.mark.parametrize(
    ("prior_state", "prior_author", "observation", "misses", "expected"),
    [row[1:] for row in TABLE],
    ids=[row[0] for row in TABLE],
)
def test_table(
    prior_state: ContentState,
    prior_author: AuthorState,
    observation: Observation,
    misses: int,
    expected: Decision,
) -> None:
    assert decide(prior_state, prior_author, observation, misses) == expected


def test_table_covers_every_content_state_as_prior() -> None:
    assert {row[1] for row in TABLE} == set(ContentState)


def test_table_covers_every_content_state_as_outcome() -> None:
    assert {row[5].content_state for row in TABLE} == set(ContentState)


def test_negative_misses_rejected() -> None:
    with pytest.raises(ValueError, match="misses"):
        decide(LIVE, KNOWN, obs(), -1)


def test_observation_is_frozen() -> None:
    with pytest.raises(AttributeError):
        obs().body = "x"  # type: ignore[misc]


def test_enum_values_match_schema_spelling() -> None:
    assert [s.value for s in ContentState] == [
        "live",
        "deleted_by_author",
        "removed_by_moderator",
        "removed_by_reddit",
        "gone_unconfirmed",
        "gone",
    ]
    assert [a.value for a in AuthorState] == ["known", "account_deleted"]
    assert GONE_AT_MISSES == 2


def test_scrub_states_exclude_holds_and_live() -> None:
    assert SCRUB_STATES == {DEL, MOD, RED, GONE}


# ---------------------------------------------------------------- hypothesis

bodies = st.one_of(
    st.none(),
    st.sampled_from(["", "[deleted]", "[removed]", "intact", "[Deleted]", " [removed]"]),
    st.text(max_size=40),
)
categories = st.one_of(
    st.none(),
    st.sampled_from(
        ["deleted", "moderator", "author", "unknown_value", *REDDIT_REMOVAL_CATEGORIES]
    ),
    st.text(min_size=1, max_size=20),
)
observations = st.builds(
    Observation,
    body=bodies,
    author=st.one_of(st.none(), st.text(min_size=1, max_size=20)),
    author_fullname_present=st.booleans(),
    removed_by_category=categories,
    is_link_post=st.booleans(),
    returned_by_info=st.one_of(st.none(), st.booleans()),
)
priors = st.sampled_from(list(ContentState))
authors = st.sampled_from(list(AuthorState))
miss_counts = st.integers(min_value=0, max_value=10)


@settings(max_examples=500)
@given(priors, authors, observations, miss_counts)
def test_never_raises_and_invariants_hold(
    prior: ContentState, author: AuthorState, observation: Observation, misses: int
) -> None:
    decision = decide(prior, author, observation, misses)
    assert isinstance(decision, Decision)
    assert decision.misses >= 0
    if decision.scrub:
        assert decision.content_state in SCRUB_STATES
        assert prior not in SCRUB_STATES
    if decision.content_state is LIVE:
        assert decision.misses == 0
    if prior is DEL:
        assert decision == Decision(DEL, author, False, misses)


@settings(max_examples=500)
@given(priors, authors, observations, miss_counts)
def test_never_live_without_intact_content(
    prior: ContentState, author: AuthorState, observation: Observation, misses: int
) -> None:
    decision = decide(prior, author, observation, misses)
    if observation.body is None or observation.body in ("[deleted]", "[removed]"):
        assert decision.content_state is not LIVE
    if observation.removed_by_category is not None:
        assert decision.content_state is not LIVE
    if observation.returned_by_info is False:
        assert decision.content_state is not LIVE


@settings(max_examples=300)
@given(priors.filter(lambda s: s is not DEL), authors, observations, miss_counts)
def test_info_absence_counts_a_miss(
    prior: ContentState, author: AuthorState, observation: Observation, misses: int
) -> None:
    absent = Observation(
        body=observation.body,
        author=observation.author,
        author_fullname_present=observation.author_fullname_present,
        removed_by_category=observation.removed_by_category,
        is_link_post=observation.is_link_post,
        returned_by_info=False,
    )
    decision = decide(prior, author, absent, misses)
    assert decision.misses == misses + 1
    assert decision.author_state is author
    if misses + 1 >= GONE_AT_MISSES or prior is GONE:
        assert decision.content_state is GONE
    else:
        assert decision.content_state is UNC


@settings(max_examples=300)
@given(priors.filter(lambda s: s is not DEL), authors, miss_counts)
def test_deleted_markers_are_terminal_from_any_prior(
    prior: ContentState, author: AuthorState, misses: int
) -> None:
    for observation in (obs(body="[deleted]"), obs(body="", category="deleted", link=True)):
        decision = decide(prior, author, observation, misses)
        assert decision.content_state is DEL
        assert decision.misses == 0
        assert decision.scrub == (prior not in SCRUB_STATES)
