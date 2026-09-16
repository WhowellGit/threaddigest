"""Tests for per-run request accounting."""

from __future__ import annotations

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from threaddigest.core.budget import DEFAULT_HARD_CAP, Budget, tree_cost


def test_defaults_match_plan() -> None:
    assert DEFAULT_HARD_CAP == 5000
    budget = Budget(limit=1500, reserve=100)
    assert budget.limit == 1500
    assert budget.reserve == 100
    assert budget.hard_cap == 5000
    assert budget.used == 0
    assert budget.remaining == 1500
    assert budget.spendable == 1400


def test_limit_is_clamped_to_hard_cap_on_construction() -> None:
    budget = Budget(limit=9000, reserve=100)
    assert budget.limit == 5000
    assert budget.remaining == 5000
    assert Budget(limit=9000, reserve=0, hard_cap=200).limit == 200


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(0, 0), (1, 1), (4999, 4999), (5000, 5000), (5001, 5000), (10**9, 5000), (-5, 0)],
)
def test_clamp(requested: int, expected: int) -> None:
    assert Budget(limit=1500, reserve=100).clamp(requested) == expected


def test_clamp_honours_custom_hard_cap() -> None:
    assert Budget(limit=10, reserve=0, hard_cap=50).clamp(75) == 50


def test_can_afford_respects_reserve() -> None:
    budget = Budget(limit=100, reserve=10)
    assert budget.can_afford(90) is True
    assert budget.can_afford(91) is False
    budget.record(50)
    assert budget.can_afford(40) is True
    assert budget.can_afford(41) is False


def test_can_afford_zero_is_always_true_until_reserve_is_breached() -> None:
    budget = Budget(limit=100, reserve=10)
    assert budget.can_afford(0) is True
    budget.record(95)
    assert budget.can_afford(0) is False
    assert budget.can_afford(1) is False


def test_record_accumulates_and_returns_running_total() -> None:
    budget = Budget(limit=100, reserve=10)
    assert budget.record(3) == 3
    assert budget.record(4) == 7
    assert budget.record(0) == 7
    assert budget.used == 7
    assert budget.remaining == 93
    assert budget.spendable == 83


def test_record_default_is_one_response() -> None:
    budget = Budget(limit=100, reserve=0)
    budget.record()
    assert budget.used == 1


def test_record_negative_rejected() -> None:
    budget = Budget(limit=100, reserve=0)
    with pytest.raises(ValueError, match="negative"):
        budget.record(-1)
    assert budget.used == 0


def test_every_response_counts_even_past_the_limit() -> None:
    budget = Budget(limit=10, reserve=2)
    budget.record(10)
    budget.record(3)  # an unplanned extra response still counts
    assert budget.used == 13
    assert budget.remaining == 0
    assert budget.spendable == 0
    assert budget.overspent == 3
    assert budget.can_afford(0) is False
    assert budget.exhausted is True


def test_exhausted_flips_at_the_reserve_line() -> None:
    budget = Budget(limit=10, reserve=2)
    budget.record(7)
    assert budget.exhausted is False
    budget.record(1)
    assert budget.exhausted is True


def test_zero_reserve_allows_spending_the_whole_limit() -> None:
    budget = Budget(limit=10, reserve=0)
    assert budget.can_afford(10) is True
    assert budget.can_afford(11) is False


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"limit": -1, "reserve": 0}, "limit"),
        ({"limit": 10, "reserve": -1}, "reserve"),
        ({"limit": 10, "reserve": 11}, "reserve"),
        ({"limit": 10, "reserve": 0, "hard_cap": 0}, "hard_cap"),
        ({"limit": 10, "reserve": 0, "hard_cap": -3}, "hard_cap"),
    ],
)
def test_invalid_construction(kwargs: dict[str, int], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        Budget(**kwargs)


def test_reserve_above_clamped_limit_is_rejected() -> None:
    # limit 9000 clamps to hard_cap 100; reserve 500 then exceeds it.
    with pytest.raises(ValueError, match="reserve"):
        Budget(limit=9000, reserve=500, hard_cap=100)


@pytest.mark.parametrize(("more_limit", "expected"), [(0, 1), (1, 2), (16, 17), (40, 41)])
def test_tree_cost(more_limit: int, expected: int) -> None:
    assert tree_cost(more_limit) == expected


def test_tree_cost_negative_rejected() -> None:
    with pytest.raises(ValueError, match="more_limit"):
        tree_cost(-1)


def test_tree_cost_drives_can_afford() -> None:
    budget = Budget(limit=20, reserve=2)
    assert budget.can_afford(tree_cost(16)) is True
    assert budget.can_afford(tree_cost(17)) is True
    assert budget.can_afford(tree_cost(18)) is False


# ---------------------------------------------------------------- hypothesis


@settings(max_examples=300)
@given(
    limit=st.integers(min_value=0, max_value=10_000),
    reserve=st.integers(min_value=0, max_value=10_000),
    hard_cap=st.integers(min_value=1, max_value=10_000),
    spends=st.lists(st.integers(min_value=0, max_value=500), max_size=30),
)
def test_accounting_invariants(limit: int, reserve: int, hard_cap: int, spends: list[int]) -> None:
    effective_limit = min(limit, hard_cap)
    if reserve > effective_limit:
        with pytest.raises(ValueError):
            Budget(limit=limit, reserve=reserve, hard_cap=hard_cap)
        return
    budget = Budget(limit=limit, reserve=reserve, hard_cap=hard_cap)
    assert budget.limit == effective_limit
    for n in spends:
        budget.record(n)
    assert budget.used == sum(spends)
    assert budget.remaining == max(effective_limit - budget.used, 0)
    assert budget.spendable == max(effective_limit - reserve - budget.used, 0)
    assert budget.overspent == max(budget.used - effective_limit, 0)
    assert budget.can_afford(0) == (budget.used <= effective_limit - reserve)
    assert budget.exhausted == (not budget.can_afford(1))
    for cost in (0, 1, 7, 10_000):
        assert budget.can_afford(cost) == (budget.used + cost <= effective_limit - reserve)


@settings(max_examples=200)
@given(st.integers(min_value=-(10**6), max_value=10**6), st.integers(min_value=1, max_value=10**5))
def test_clamp_is_bounded_and_idempotent(requested: int, hard_cap: int) -> None:
    budget = Budget(limit=1, reserve=0, hard_cap=hard_cap)
    clamped = budget.clamp(requested)
    assert 0 <= clamped <= hard_cap
    assert budget.clamp(clamped) == clamped
