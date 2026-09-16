"""Tests for the revisit ladder."""

from __future__ import annotations

import time

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from threaddigest.core.milestones import DAY_SECONDS, DEFAULT_LADDER_DAYS, next_check

CREATED = 1_757_700_000  # an arbitrary epoch second in 2025


def test_default_ladder_matches_plan() -> None:
    assert DEFAULT_LADDER_DAYS == (1, 3, 7, 30, 365)
    assert DAY_SECONDS == 86_400


@pytest.mark.parametrize(
    ("stage", "days"),
    [(0, 1), (1, 3), (2, 7), (3, 30), (4, 365)],
)
def test_ladder_stages(stage: int, days: int) -> None:
    assert next_check(CREATED, stage) == (CREATED + days * DAY_SECONDS, stage + 1)


@pytest.mark.parametrize(
    ("stage", "multiplier"),
    [(5, 2), (6, 3), (7, 4), (50, 47)],
)
def test_beyond_last_stage_repeats_last_rung(stage: int, multiplier: int) -> None:
    assert next_check(CREATED, stage) == (CREATED + 365 * multiplier * DAY_SECONDS, stage + 1)


def test_custom_ladder() -> None:
    ladder = [2, 5]
    assert next_check(CREATED, 0, ladder) == (CREATED + 2 * DAY_SECONDS, 1)
    assert next_check(CREATED, 1, ladder) == (CREATED + 5 * DAY_SECONDS, 2)
    assert next_check(CREATED, 2, ladder) == (CREATED + 10 * DAY_SECONDS, 3)
    assert next_check(CREATED, 3, ladder) == (CREATED + 15 * DAY_SECONDS, 4)


def test_single_rung_ladder_keeps_climbing() -> None:
    assert next_check(CREATED, 0, [7]) == (CREATED + 7 * DAY_SECONDS, 1)
    assert next_check(CREATED, 1, [7]) == (CREATED + 14 * DAY_SECONDS, 2)


def test_zero_comment_post_is_first_checked_one_day_after_creation() -> None:
    # The design review's rule for num_comments == 0: check_stage=0, next_check_at=created+1d.
    next_at, _ = next_check(CREATED, 0)
    assert next_at == CREATED + DAY_SECONDS


@pytest.mark.parametrize("stage", [-1, -10])
def test_negative_stage_rejected(stage: int) -> None:
    with pytest.raises(ValueError, match="stage"):
        next_check(CREATED, stage)


@pytest.mark.parametrize("ladder", [[], [0, 1], [-1, 3], [3, 1], [3, 3]])
def test_bad_ladders_rejected(ladder: list[int]) -> None:
    with pytest.raises(ValueError, match="ladder"):
        next_check(CREATED, 0, ladder)


def test_never_consults_the_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom() -> float:
        msg = "next_check consulted time.time()"
        raise AssertionError(msg)

    monkeypatch.setattr(time, "time", boom)
    monkeypatch.setattr(time, "time_ns", boom)
    assert next_check(CREATED, 3)[0] == CREATED + 30 * DAY_SECONDS


# ---------------------------------------------------------------- hypothesis

created_utcs = st.integers(min_value=0, max_value=4_000_000_000)
stages = st.integers(min_value=0, max_value=200)
ladders = st.lists(
    st.integers(min_value=1, max_value=1000), min_size=1, max_size=8, unique=True
).map(sorted)


@settings(max_examples=300)
@given(created_utcs, stages, ladders)
def test_never_none_and_always_after_creation(created: int, stage: int, ladder: list[int]) -> None:
    next_at, next_stage = next_check(created, stage, ladder)
    assert isinstance(next_at, int)
    assert isinstance(next_stage, int)
    assert next_at > created
    assert next_stage == stage + 1


@settings(max_examples=300)
@given(created_utcs, stages, ladders)
def test_strictly_monotonic_in_stage(created: int, stage: int, ladder: list[int]) -> None:
    assert next_check(created, stage, ladder)[0] < next_check(created, stage + 1, ladder)[0]


@settings(max_examples=200)
@given(created_utcs, stages, ladders, st.integers(min_value=-(10**9), max_value=10**9))
def test_shift_invariant_in_created_utc(
    created: int, stage: int, ladder: list[int], shift: int
) -> None:
    base = next_check(created, stage, ladder)
    shifted = next_check(created + shift, stage, ladder)
    assert shifted[0] - base[0] == shift
    assert shifted[1] == base[1]


@settings(max_examples=200)
@given(created_utcs, stages, ladders)
def test_deterministic_across_calls(created: int, stage: int, ladder: list[int]) -> None:
    assert next_check(created, stage, ladder) == next_check(created, stage, tuple(ladder))
