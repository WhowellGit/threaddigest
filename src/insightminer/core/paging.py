"""Rules for the ``/new`` sweep: when to stop, when a gap is suspected, what may be gone.

Pure: no I/O and no clock. Every timestamp here is Reddit's ``created_utc``; local
time never enters a correctness decision (docs/reference/reviews/
2026-09-12-collector-design-review.md, section 1.3).

The sweep pages the whole listing every run (forward ``after`` paging only) and lets
the upsert dedupe, so ``plan_stop`` never stops early by default: it stops on an
empty page (``exhausted``) or when Reddit's listing cap is reached (``cap``). Stickied
items are recorded as seen but excluded from every window computation, because a
pinned sticky sits outside the chronological order the window relies on.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, replace
from enum import StrEnum

DEFAULT_CAP = 1000


class StopReason(StrEnum):
    """Why a sweep ended. Values are the ``run_subreddits.stop_reason`` column."""

    EXHAUSTED = "exhausted"
    CAP = "cap"
    ERROR = "error"


@dataclass(frozen=True, slots=True)
class PageItem:
    """The three facts about a listing item that the sweep rules need."""

    reddit_id: str
    created_utc: int
    stickied: bool = False


@dataclass(frozen=True, slots=True)
class KnownPost:
    """A post already in the store, as ``removal_candidates`` needs to see it."""

    reddit_id: str
    created_utc: int
    stickied: bool = False


@dataclass(frozen=True, slots=True)
class SweepState:
    """Progress of one subreddit's sweep. Immutable; ``plan_stop`` returns the successor.

    ``items_seen`` counts listing slots (duplicates included) and drives the cap;
    ``seen_ids`` is deduplicated; ``seen_min_created_utc`` / ``seen_max_created_utc``
    span the non-stickied items only.
    """

    pages: int = 0
    items_seen: int = 0
    seen_ids: frozenset[str] = frozenset()
    seen_min_created_utc: int | None = None
    seen_max_created_utc: int | None = None

    @property
    def unique_items(self) -> int:
        return len(self.seen_ids)

    def absorb(self, page_items: Sequence[PageItem]) -> SweepState:
        """Fold one non-empty page into the state."""
        timestamps = [item.created_utc for item in page_items if not item.stickied]
        lows = [t for t in (self.seen_min_created_utc, *timestamps) if t is not None]
        highs = [t for t in (self.seen_max_created_utc, *timestamps) if t is not None]
        return replace(
            self,
            pages=self.pages + 1,
            items_seen=self.items_seen + len(page_items),
            seen_ids=self.seen_ids | {item.reddit_id for item in page_items},
            seen_min_created_utc=min(lows) if lows else None,
            seen_max_created_utc=max(highs) if highs else None,
        )


@dataclass(frozen=True, slots=True)
class StopDecision:
    """Whether to fetch another page, why not, and the state after this page."""

    stop: bool
    reason: StopReason | None
    state: SweepState


def plan_stop(
    page_items: Sequence[PageItem], state: SweepState, cap: int = DEFAULT_CAP
) -> StopDecision:
    """Decide after one page whether the sweep goes on.

    An empty page means the listing is exhausted; it is not counted as a fetched page
    and leaves ``state`` unchanged. Otherwise the page is absorbed and the sweep stops
    with ``cap`` once ``items_seen`` reaches ``cap`` (Reddit's cap counts listing
    positions, so duplicates from items shifting between fetches consume it too).
    Short pages are normal (Reddit drops deleted items after pagination) and never
    stop the sweep. Errors are reported through ``stop_on_error``.
    """
    if cap < 1:
        msg = f"cap must be >= 1, got {cap}"
        raise ValueError(msg)
    if not page_items:
        return StopDecision(stop=True, reason=StopReason.EXHAUSTED, state=state)
    new_state = state.absorb(page_items)
    if new_state.items_seen >= cap:
        return StopDecision(stop=True, reason=StopReason.CAP, state=new_state)
    return StopDecision(stop=False, reason=None, state=new_state)


def stop_on_error(state: SweepState) -> StopDecision:
    """The decision to record when a page fetch failed: progress so far is kept."""
    return StopDecision(stop=True, reason=StopReason.ERROR, state=state)


def gap_suspected(seen_min_created_utc: int | None, known_max_created_utc: int | None) -> bool:
    """After a ``cap`` stop: did the sweep end before reaching posts we already knew?

    ``known_max_created_utc`` is the store's newest non-stickied post for the
    subreddit before this sweep (``subreddits.watermark_created_utc``). No known
    posts means a first sweep, which cannot have a gap. Reaching or passing the
    watermark means the windows overlap. Having seen nothing non-stickied yet
    hitting the cap is treated as a gap (fail closed).
    """
    if known_max_created_utc is None:
        return False
    if seen_min_created_utc is None:
        return True
    return seen_min_created_utc > known_max_created_utc


def removal_candidates(
    known: Iterable[KnownPost],
    seen_ids: AbstractSet[str],
    oldest_seen_created_utc: int,
) -> list[str]:
    """Known posts inside the swept window that the sweep did not return.

    Call only after a COMPLETE sweep (``exhausted``), with ``oldest_seen_created_utc``
    the state's ``seen_min_created_utc``: a post created at or after it that is not
    in ``seen_ids`` has vanished from ``/new`` and should be checked with ``info()``.
    Stickied known posts are skipped. This is a candidate list, never a state
    change: only the state machine in ``core.deletion`` decides what a post became.
    Input order is preserved.
    """
    return [
        post.reddit_id
        for post in known
        if not post.stickied
        and post.created_utc >= oldest_seen_created_utc
        and post.reddit_id not in seen_ids
    ]
