"""Pure planning for one comment-tree fetch.

Which bound limits one fetch (``more_limit_for``), whether a post is skipped
(``plan_fetch``), which bound stopped expansion (``stop_reason``), and the write order
of a fetched tree (``flatten``). Pure: no I/O, no database, no gateway calls -- ``core/``
imports nothing above ``core/`` (docs/PLAN.md, "Four layers only"; ``ports`` sits above
``core`` in that order, so the ``TreeResult`` shape below is redeclared structurally
rather than imported). ``num_comments`` is never a completeness check (it counts deleted
items too, docs/PLAN.md § Silent-failure controls): it decides only whether the fetch is
skipped, never whether a tree is complete.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Literal, Protocol

RawItem = dict[str, Any]
"""One Reddit object in wire shape -- matches ``ports.RawItem`` structurally."""

StopBound = Literal["budget", "cap", "limit"]


class TreeResultLike(Protocol):
    """The shape this module needs from ``ports.TreeResult``: ``comments``, ``more``, and
    ``complete``. Expressed structurally, as read-only properties matching a frozen
    dataclass's fields, so ``core`` never imports ``ports``; a real ``ports.TreeResult``
    satisfies this without change, and so does a value built directly from ``ports``'s own
    dataclasses in a test.
    """

    @property
    def comments(self) -> Sequence[RawItem]: ...

    @property
    def more(self) -> Sequence[object]: ...

    @property
    def complete(self) -> bool: ...


def more_limit_for(replace_more_limit: int, per_post_cap: int, spendable: int) -> int:
    """The ``more_limit`` to pass to ``fetch_tree`` for one post.

    The smallest of the configured ``replace_more`` limit, the per-post expansion cap,
    and what the budget can still spend after the tree's own first request
    (``core.budget.tree_cost(0) == 1``, hence ``spendable - 1``). Never negative, even
    when ``spendable`` is 0 or 1.
    """
    if replace_more_limit < 0:
        msg = f"replace_more_limit must be >= 0, got {replace_more_limit}"
        raise ValueError(msg)
    if per_post_cap < 0:
        msg = f"per_post_cap must be >= 0, got {per_post_cap}"
        raise ValueError(msg)
    if spendable < 0:
        msg = f"spendable must be >= 0, got {spendable}"
        raise ValueError(msg)
    budget_bound = max(spendable - 1, 0)
    return min(replace_more_limit, per_post_cap, budget_bound)


@dataclass(frozen=True, slots=True)
class TreePlan:
    """Whether to fetch a post's tree, and with what ``more_limit`` if so.

    ``advance_ladder`` is set only for a skip: the stage still owes the post its next
    ``next_check_at`` (docs/PLAN.md § Collector algorithm step 3) even though nothing
    was fetched. Whether a real fetch's ladder advances depends on the fetch's own
    outcome (a transient failure does not advance it), which this module cannot see,
    so a planned (non-skip) fetch always carries ``advance_ladder=False`` and leaves
    that decision to the stage.
    """

    skip: bool
    reason: str | None
    advance_ladder: bool
    more_limit: int


def plan_fetch(
    num_comments: int,
    *,
    replace_more_limit: int,
    per_post_cap: int,
    spendable: int,
) -> TreePlan:
    """Plan one post's tree fetch.

    ``num_comments`` decides only the skip, never completeness. A post with
    ``num_comments == 0`` is planned as a skip (``reason="empty"``) that still
    advances the ladder. Otherwise the plan carries the ``more_limit`` to request,
    from ``more_limit_for``.
    """
    if num_comments < 0:
        msg = f"num_comments must be >= 0, got {num_comments}"
        raise ValueError(msg)
    if num_comments == 0:
        return TreePlan(skip=True, reason="empty", advance_ladder=True, more_limit=0)
    limit = more_limit_for(replace_more_limit, per_post_cap, spendable)
    return TreePlan(skip=False, reason=None, advance_ladder=False, more_limit=limit)


def stop_reason(
    result: TreeResultLike,
    *,
    replace_more_limit: int,
    per_post_cap: int,
    spendable_before: int,
) -> StopBound | None:
    """Which bound stopped expansion, or ``None`` when the fetch left no stubs behind.

    The three bounds are named as ``more_limit_for`` computed them: ``"budget"`` for
    ``spendable_before - 1`` (never negative), ``"cap"`` for ``per_post_expansion_cap``,
    ``"limit"`` for ``replace_more_limit``. Ties resolve budget before cap before limit.
    """
    if not result.more:
        return None
    budget_bound = max(spendable_before - 1, 0)
    bounds: list[tuple[StopBound, int]] = [
        ("budget", budget_bound),
        ("cap", per_post_cap),
        ("limit", replace_more_limit),
    ]
    # min() on a list is stable: with a tie it returns the first-listed candidate, which is
    # exactly the budget-before-cap-before-limit order the bounds list is written in.
    name, _value = min(bounds, key=lambda bound: bound[1])
    return name


def is_complete(result: TreeResultLike) -> bool:
    """Whether the tree is complete. Delegates to the port's own field (``ports.py``
    already defines ``complete`` as "fetch succeeded and no stubs remain"), so
    completeness is never defined twice.
    """
    return result.complete


def flatten(result: TreeResultLike) -> list[RawItem]:
    """``result.comments`` in depth-first order, every parent before its children.

    Rebuilt from each comment's ``id`` and ``parent_id`` rather than trusted as
    already sorted, so the guarantee holds regardless of what order the gateway
    delivered them in. A comment whose parent is not another item in
    ``result.comments`` (the post itself, or a parent left behind an unexpanded
    ``more`` stub) is planted as a root rather than dropped. Siblings keep the
    relative order ``result.comments`` gives them. ``result.more`` stubs are never
    included; they carry no comment to write.
    """
    ids = {str(item["id"]) for item in result.comments}
    children_of: dict[str, list[RawItem]] = defaultdict(list)
    roots: list[RawItem] = []
    for item in result.comments:
        parent_id = _base_id(item.get("parent_id"))
        if parent_id is not None and parent_id in ids:
            children_of[parent_id].append(item)
        else:
            roots.append(item)

    ordered: list[RawItem] = []

    def visit(item: RawItem) -> None:
        ordered.append(item)
        for child in children_of.get(str(item["id"]), []):
            visit(child)

    for root in roots:
        visit(root)
    return ordered


def _base_id(fullname: object) -> str | None:
    """``"t1_abc123"`` -> ``"abc123"``; anything falsy or unprefixed is ``None``."""
    if not isinstance(fullname, str) or not fullname:
        return None
    _, _, base = fullname.partition("_")
    return base or None
