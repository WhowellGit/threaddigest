"""Tests for the /new sweep stop, cap, gap, and removal-candidate rules."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from threaddigest.core.paging import (
    KnownPost,
    PageItem,
    StopDecision,
    StopReason,
    SweepState,
    gap_suspected,
    plan_stop,
    removal_candidates,
    stop_on_error,
)

T0 = 1_757_700_000


def page(
    start: int, count: int, *, newest_utc: int = T0, stickied: set[int] | None = None
) -> list[PageItem]:
    """Build a page of `count` items numbered from `start`, newest first, one minute apart."""
    return [
        PageItem(
            reddit_id=f"p{n}", created_utc=newest_utc - 60 * n, stickied=n in (stickied or set())
        )
        for n in range(start, start + count)
    ]


def sweep(*pages: list[PageItem], cap: int = 1000) -> list[StopDecision]:
    state = SweepState()
    decisions: list[StopDecision] = []
    for items in pages:
        decision = plan_stop(items, state, cap=cap)
        decisions.append(decision)
        state = decision.state
        if decision.stop:
            break
    return decisions


# ---------------------------------------------------------------- plan_stop


def test_empty_listing_is_exhausted_immediately() -> None:
    decision = plan_stop([], SweepState())
    assert decision.stop is True
    assert decision.reason is StopReason.EXHAUSTED
    assert decision.state == SweepState()
    assert decision.state.pages == 0
    assert decision.state.items_seen == 0
    assert decision.state.seen_min_created_utc is None
    assert decision.state.seen_max_created_utc is None


def test_full_page_never_stops_early() -> None:
    decision = plan_stop(page(0, 100), SweepState())
    assert decision.stop is False
    assert decision.reason is None
    assert decision.state.pages == 1
    assert decision.state.items_seen == 100
    assert decision.state.unique_items == 100


def test_short_page_with_more_to_come_keeps_going() -> None:
    # Reddit removes deleted items after pagination: a page of 37 is normal.
    decisions = sweep(page(0, 100), page(100, 37), page(137, 100))
    assert [d.stop for d in decisions] == [False, False, False]
    assert decisions[-1].state.pages == 3
    assert decisions[-1].state.items_seen == 237


def test_exhaustion_after_short_page() -> None:
    decisions = sweep(page(0, 100), page(100, 37), [])
    assert decisions[-1].stop is True
    assert decisions[-1].reason is StopReason.EXHAUSTED
    assert decisions[-1].state.pages == 2, "the empty page is not a fetched page"
    assert decisions[-1].state.items_seen == 137
    assert decisions[-1].state.seen_min_created_utc == T0 - 60 * 136
    assert decisions[-1].state.seen_max_created_utc == T0


def test_overlapping_pages_count_once_in_seen_ids() -> None:
    # Items shift between page fetches: the same id can appear on two pages.
    first = page(0, 100)
    second = page(95, 100)  # p95..p99 repeat
    decisions = sweep(first, second, [])
    final = decisions[-1].state
    assert final.items_seen == 200
    assert final.unique_items == 195
    assert final.seen_ids == frozenset(f"p{n}" for n in range(195))


def test_duplicate_within_a_page_counts_once() -> None:
    item = PageItem("dup", T0)
    decision = plan_stop([item, item], SweepState())
    assert decision.state.items_seen == 2
    assert decision.state.unique_items == 1


def test_cap_reached_on_tenth_full_page() -> None:
    pages = [page(100 * i, 100) for i in range(10)]
    decisions = sweep(*pages)
    assert len(decisions) == 10
    assert [d.stop for d in decisions[:9]] == [False] * 9
    assert decisions[-1].stop is True
    assert decisions[-1].reason is StopReason.CAP
    assert decisions[-1].state.items_seen == 1000
    assert decisions[-1].state.pages == 10


def test_cap_counts_listing_slots_not_unique_ids() -> None:
    # Reddit's cap is on listing positions; duplicates from shifting still consume them.
    decisions = sweep(page(0, 600), page(590, 400))
    assert decisions[-1].stop is True
    assert decisions[-1].reason is StopReason.CAP
    assert decisions[-1].state.unique_items == 990


def test_custom_cap() -> None:
    decisions = sweep(page(0, 100), page(100, 100), page(200, 100), cap=250)
    assert [d.stop for d in decisions] == [False, False, True]
    assert decisions[-1].reason is StopReason.CAP


def test_cap_below_one_rejected() -> None:
    with pytest.raises(ValueError, match="cap"):
        plan_stop(page(0, 1), SweepState(), cap=0)


def test_stickies_excluded_from_window_but_recorded() -> None:
    old_sticky = PageItem("sticky", T0 - 10 * 86_400, stickied=True)
    new_sticky = PageItem("sticky2", T0 + 10 * 86_400, stickied=True)
    items = [new_sticky, *page(0, 5), old_sticky]
    decision = plan_stop(items, SweepState())
    assert decision.state.seen_max_created_utc == T0
    assert decision.state.seen_min_created_utc == T0 - 60 * 4
    assert "sticky" in decision.state.seen_ids
    assert "sticky2" in decision.state.seen_ids
    assert decision.state.items_seen == 7


def test_page_of_only_stickies_leaves_window_unset() -> None:
    decision = plan_stop([PageItem("s", T0, stickied=True)], SweepState())
    assert decision.stop is False
    assert decision.state.seen_min_created_utc is None
    assert decision.state.seen_max_created_utc is None
    assert decision.state.unique_items == 1


def test_window_tracks_extremes_across_pages_regardless_of_order() -> None:
    decisions = sweep(
        [PageItem("a", 500), PageItem("b", 900)], [PageItem("c", 100), PageItem("d", 700)], []
    )
    final = decisions[-1].state
    assert final.seen_min_created_utc == 100
    assert final.seen_max_created_utc == 900


def test_state_is_immutable_and_input_state_untouched() -> None:
    state = SweepState()
    plan_stop(page(0, 3), state)
    assert state == SweepState()
    with pytest.raises(AttributeError):
        state.pages = 5  # type: ignore[misc]


def test_stop_on_error_preserves_progress() -> None:
    state = plan_stop(page(0, 100), SweepState()).state
    decision = stop_on_error(state)
    assert decision.stop is True
    assert decision.reason is StopReason.ERROR
    assert decision.state == state


def test_stop_reasons_match_schema_spelling() -> None:
    assert [r.value for r in StopReason] == ["exhausted", "cap", "error"]


# ---------------------------------------------------------------- gap_suspected


def test_no_gap_when_sweep_reaches_known_territory() -> None:
    assert gap_suspected(seen_min_created_utc=100, known_max_created_utc=150) is False
    assert gap_suspected(seen_min_created_utc=150, known_max_created_utc=150) is False


def test_gap_when_oldest_seen_is_newer_than_newest_known() -> None:
    assert gap_suspected(seen_min_created_utc=200, known_max_created_utc=150) is True


def test_no_gap_on_first_ever_sweep() -> None:
    assert gap_suspected(seen_min_created_utc=200, known_max_created_utc=None) is False


def test_gap_fails_closed_when_nothing_non_sticky_was_seen() -> None:
    assert gap_suspected(seen_min_created_utc=None, known_max_created_utc=150) is True


def test_gap_undecidable_with_nothing_known_and_nothing_seen() -> None:
    assert gap_suspected(seen_min_created_utc=None, known_max_created_utc=None) is False


# ---------------------------------------------------------------- removal_candidates

KNOWN = [
    KnownPost("k_new", T0 - 60),
    KnownPost("k_mid", T0 - 600),
    KnownPost("k_edge", T0 - 6000),
    KnownPost("k_old", T0 - 6001),
    KnownPost("k_sticky", T0 - 60, stickied=True),
]


def test_candidates_are_unseen_known_posts_inside_the_window() -> None:
    seen = {"k_new", "other"}
    assert removal_candidates(KNOWN, seen, oldest_seen_created_utc=T0 - 6000) == ["k_mid", "k_edge"]


def test_boundary_is_inclusive_and_older_posts_are_outside() -> None:
    assert removal_candidates(KNOWN, set(), oldest_seen_created_utc=T0 - 6000) == [
        "k_new",
        "k_mid",
        "k_edge",
    ]
    assert removal_candidates(KNOWN, set(), oldest_seen_created_utc=T0 - 5999) == ["k_new", "k_mid"]


def test_stickies_never_become_candidates() -> None:
    assert "k_sticky" not in removal_candidates(KNOWN, set(), oldest_seen_created_utc=0)


def test_all_seen_yields_no_candidates() -> None:
    seen = {k.reddit_id for k in KNOWN}
    assert removal_candidates(KNOWN, seen, oldest_seen_created_utc=0) == []


def test_empty_known_yields_no_candidates() -> None:
    assert removal_candidates([], {"a", "b"}, oldest_seen_created_utc=0) == []


def test_candidates_preserve_input_order_and_accept_frozenset() -> None:
    known = [KnownPost("b", 20), KnownPost("a", 30), KnownPost("c", 10)]
    assert removal_candidates(known, frozenset(), oldest_seen_created_utc=10) == ["b", "a", "c"]


def test_candidates_accept_any_iterable() -> None:
    known = (KnownPost(f"g{i}", 100 + i) for i in range(3))
    assert removal_candidates(known, {"g1"}, oldest_seen_created_utc=101) == ["g2"]


# ---------------------------------------------------------------- hypothesis

items = st.builds(
    PageItem,
    reddit_id=st.text(alphabet="abcdefghij", min_size=1, max_size=3),
    created_utc=st.integers(min_value=0, max_value=10**9),
    stickied=st.booleans(),
)
pages = st.lists(st.lists(items, max_size=30), min_size=1, max_size=12)


@settings(max_examples=200)
@given(pages, st.integers(min_value=1, max_value=300))
def test_sweep_invariants(page_list: list[list[PageItem]], cap: int) -> None:
    state = SweepState()
    raw = 0
    for items_ in page_list:
        decision = plan_stop(items_, state, cap=cap)
        raw += len(items_)
        state = decision.state
        assert state.items_seen == raw
        assert state.unique_items <= state.items_seen
        assert state.unique_items <= len({i.reddit_id for p in page_list for i in p})
        if state.seen_min_created_utc is not None:
            assert state.seen_max_created_utc is not None
            assert state.seen_min_created_utc <= state.seen_max_created_utc
        if decision.stop:
            assert decision.reason in (StopReason.EXHAUSTED, StopReason.CAP)
            if decision.reason is StopReason.CAP:
                assert state.items_seen >= cap
            else:
                assert items_ == []
            break
        assert decision.reason is None
        assert state.items_seen < cap


@settings(max_examples=200)
@given(
    st.lists(
        st.builds(
            KnownPost,
            reddit_id=st.text(alphabet="abcdefghij", min_size=1, max_size=3),
            created_utc=st.integers(min_value=0, max_value=1000),
            stickied=st.booleans(),
        ),
        max_size=30,
    ),
    st.frozensets(st.text(alphabet="abcdefghij", min_size=1, max_size=3), max_size=20),
    st.integers(min_value=0, max_value=1000),
)
def test_removal_candidates_invariants(
    known: list[KnownPost], seen: frozenset[str], oldest: int
) -> None:
    result = removal_candidates(known, seen, oldest)
    expected = [
        k.reddit_id
        for k in known
        if not k.stickied and k.created_utc >= oldest and k.reddit_id not in seen
    ]
    assert result == expected
    assert not (set(result) & set(seen))
