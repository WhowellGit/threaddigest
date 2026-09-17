"""Tests for pure comment-tree planning: bounds, the skip decision, stop reasons, order."""

from __future__ import annotations

import pytest

from threaddigest.core.trees import (
    TreePlan,
    flatten,
    is_complete,
    more_limit_for,
    plan_fetch,
    stop_reason,
)
from threaddigest.ports import MoreStub, RawItem, TreeResult

POST = {"id": "post1", "name": "t3_post1"}


def result(comments: list[RawItem] | None = None, more: list[MoreStub] | None = None) -> TreeResult:
    comments = comments or []
    more = more or []
    return TreeResult(post=POST, comments=comments, more=more, requests_used=1, complete=not more)


def comment(comment_id: str, parent_id: str) -> RawItem:
    return {"id": comment_id, "parent_id": parent_id}


# --------------------------------------------------------------------- more_limit_for


# (replace_more_limit, per_post_cap, spendable, expected): each case names a different bound
# as the smallest -- limit, cap, budget (spendable - 1), then the zero/one budget-exhaustion edge.
@pytest.mark.parametrize(
    ("replace_more_limit", "per_post_cap", "spendable", "expected"),
    [(16, 40, 100, 16), (16, 5, 100, 5), (16, 40, 10, 9), (16, 40, 0, 0), (16, 40, 1, 0)],
)
def test_more_limit_is_the_smallest_of_the_three_bounds(
    replace_more_limit: int, per_post_cap: int, spendable: int, expected: int
) -> None:
    assert more_limit_for(replace_more_limit, per_post_cap, spendable) == expected


def test_more_limit_never_goes_negative_when_spendable_is_zero_or_one() -> None:
    assert more_limit_for(replace_more_limit=16, per_post_cap=40, spendable=0) == 0
    assert more_limit_for(replace_more_limit=16, per_post_cap=40, spendable=1) == 0


@pytest.mark.parametrize(
    ("kwargs", "match"),
    [
        ({"replace_more_limit": -1, "per_post_cap": 40, "spendable": 100}, "replace_more_limit"),
        ({"replace_more_limit": 16, "per_post_cap": -1, "spendable": 100}, "per_post_cap"),
        ({"replace_more_limit": 16, "per_post_cap": 40, "spendable": -1}, "spendable"),
    ],
)
def test_more_limit_rejects_negative_inputs(kwargs: dict[str, int], match: str) -> None:
    with pytest.raises(ValueError, match=match):
        more_limit_for(**kwargs)


# ------------------------------------------------------------------------- plan_fetch


def test_a_zero_comment_post_is_planned_as_a_skip_that_still_advances() -> None:
    plan = plan_fetch(0, replace_more_limit=16, per_post_cap=40, spendable=100)
    assert plan == TreePlan(skip=True, reason="empty", advance_ladder=True, more_limit=0)


def test_a_post_with_comments_is_planned_with_the_bounded_more_limit() -> None:
    plan = plan_fetch(12, replace_more_limit=16, per_post_cap=40, spendable=10)
    assert plan == TreePlan(skip=False, reason=None, advance_ladder=False, more_limit=9)


# ------------------------------------------------------------------------ stop_reason

STUB = MoreStub(parent_fullname="t3_post1", count=5)


@pytest.mark.parametrize(
    ("replace_more_limit", "per_post_cap", "spendable_before", "expected"),
    [
        (16, 40, 5, "budget"),  # spendable - 1 == 4 is the smallest bound
        (16, 3, 100, "cap"),
        (2, 40, 100, "limit"),
        (4, 4, 5, "budget"),  # three-way tie: budget wins
        (4, 4, 21, "cap"),  # cap == limit, budget's bound (20) is bigger: cap wins
    ],
)
def test_the_stop_reason_names_which_bound_stopped_it(
    replace_more_limit: int, per_post_cap: int, spendable_before: int, expected: str
) -> None:
    assert (
        stop_reason(
            result(more=[STUB]),
            replace_more_limit=replace_more_limit,
            per_post_cap=per_post_cap,
            spendable_before=spendable_before,
        )
        == expected
    )


def test_the_stop_reason_tie_order_is_budget_cap_limit() -> None:
    # Same case as the parametrized ties above, spelled out once for the node id the brief names.
    tied = result(more=[STUB])
    assert stop_reason(tied, replace_more_limit=4, per_post_cap=4, spendable_before=5) == "budget"
    assert stop_reason(tied, replace_more_limit=4, per_post_cap=4, spendable_before=21) == "cap"


def test_a_complete_result_has_no_stop_reason() -> None:
    assert (
        stop_reason(result(), replace_more_limit=16, per_post_cap=40, spendable_before=100) is None
    )


# ------------------------------------------------------------------------- is_complete


def test_is_complete_delegates_to_the_port_s_own_field() -> None:
    assert is_complete(result()) is True
    assert is_complete(result(more=[STUB])) is False
    # complete is whatever the port says, even disagreeing with `more` -- is_complete must
    # not recompute it as `not result.more`.
    disagreeing = TreeResult(post=POST, comments=[], more=[], requests_used=1, complete=False)
    assert is_complete(disagreeing) is False


# ---------------------------------------------------------------------------- flatten


def test_depth_first_order_puts_every_parent_before_its_children() -> None:
    a, b, c, d = (
        comment("a", "t3_post1"),
        comment("b", "t1_a"),
        comment("c", "t3_post1"),
        comment("d", "t1_b"),
    )
    # Deliberately scrambled: a real gateway is trusted to deliver depth-first order, but
    # flatten rebuilds it from id/parent_id so the guarantee does not depend on that trust.
    assert flatten(result(comments=[d, b, a, c])) == [a, b, d, c]


def test_flatten_keeps_sibling_order_from_the_result() -> None:
    a, b, c, d = (
        comment("a", "t3_post1"),
        comment("b", "t3_post1"),
        comment("c", "t1_a"),
        comment("d", "t1_a"),
    )
    assert flatten(result(comments=[a, b, c, d])) == [a, c, d, b]


def test_flatten_excludes_stubs_and_treats_a_hidden_parent_as_a_root() -> None:
    # e's parent ("t1_hidden") is not in result.comments (it is behind an unexpanded stub),
    # so e is planted as its own root rather than dropped.
    e = comment("e", "t1_hidden")
    hidden_stub = MoreStub(parent_fullname="t3_post1", count=5, children=["hidden"])
    assert flatten(result(comments=[e], more=[hidden_stub])) == [e]
