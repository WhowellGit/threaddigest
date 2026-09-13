"""Content and author state machine for stored Reddit items (posts and comments).

Pure: no I/O, no clock, no imports from the rest of the project.

The STATE SHAPE (``ContentState``, ``AuthorState`` and the transitions that
``decide`` allows between them) is locked by docs/PLAN.md, "Data model". The
PREDICATES that map a wire observation onto a transition are PROVISIONAL until
the M1 ``probe`` fixtures (a deleted self post, a deleted link post, a
moderator-removed post, a Reddit-removed post, a deleted comment, a removed
comment) confirm how each situation manifests. They follow
docs/reference/reviews/2026-09-12-collector-design-review.md section 1.4 and
fail closed wherever that review marks a value as unverified: anything that
is not demonstrably intact public content is never ``live``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Final, NamedTuple


class ContentState(StrEnum):
    """Stored state of an item's content. Values are the ``content_state`` column."""

    LIVE = "live"
    DELETED_BY_AUTHOR = "deleted_by_author"
    REMOVED_BY_MODERATOR = "removed_by_moderator"
    REMOVED_BY_REDDIT = "removed_by_reddit"
    GONE_UNCONFIRMED = "gone_unconfirmed"
    GONE = "gone"


class AuthorState(StrEnum):
    """Stored state of an item's author. Values are the ``author_state`` column."""

    KNOWN = "known"
    ACCOUNT_DELETED = "account_deleted"


DELETED_MARKER: Final = "[deleted]"
REMOVED_MARKER: Final = "[removed]"
DELETED_CATEGORY: Final = "deleted"
MODERATOR_CATEGORY: Final = "moderator"

#: ``removed_by_category`` values that mean Reddit (not a subreddit moderator) removed
#: the item. Observed in the wild, not officially documented; see the design review 1.4.
REDDIT_REMOVAL_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "reddit",
        "automod_filtered",
        "anti_evil_ops",
        "content_takedown",
        "copyright_takedown",
        "community_ops",
        "legal_operations",
    }
)

#: Number of consecutive ``info()`` misses at which an item is declared ``gone``.
GONE_AT_MISSES: Final = 2

#: States whose content must be purged from the store (a compliance obligation).
#: ``gone_unconfirmed`` is a hold, not a purge; ``live`` keeps content.
SCRUB_STATES: Final[frozenset[ContentState]] = frozenset(
    {
        ContentState.DELETED_BY_AUTHOR,
        ContentState.REMOVED_BY_MODERATOR,
        ContentState.REMOVED_BY_REDDIT,
        ContentState.GONE,
    }
)


@dataclass(frozen=True, slots=True)
class Observation:
    """What one fetch presented for an item, already reduced to the fields that matter.

    ``body`` is ``selftext`` for posts and ``body`` for comments; ``None`` means the
    key was absent on the wire (an empty string is intact content: link posts and
    text-less self posts have ``selftext == ""``). ``author`` is ``None`` when Reddit
    shows ``[deleted]``. ``author_fullname_present`` records whether the
    ``author_fullname`` key existed (Reddit drops it for deleted accounts).
    ``returned_by_info`` is ``None`` unless the check was an ``info()`` lookup, in
    which case ``False`` means the item was missing from the response and the other
    fields carry no information.
    """

    body: str | None
    author: str | None
    author_fullname_present: bool
    removed_by_category: str | None
    is_link_post: bool
    returned_by_info: bool | None


class Decision(NamedTuple):
    """Result of ``decide``: the new states, whether to scrub now, the new miss count."""

    content_state: ContentState
    author_state: AuthorState
    scrub: bool
    misses: int


def decide(
    prior_state: ContentState,
    prior_author: AuthorState,
    obs: Observation,
    misses: int,
) -> Decision:
    """Apply one observation to an item's stored state.

    Rules, evaluated in this order; the first that applies wins:

    1. ``deleted_by_author`` is terminal: the prior states come back unchanged, no
       scrub, ``misses`` untouched, whatever the observation says.
    2. ``returned_by_info is False`` (an ``info()`` lookup did not return the item;
       every other field is ignored): ``misses + 1``; ``gone`` when that reaches
       ``GONE_AT_MISSES`` or the item was already ``gone``, else ``gone_unconfirmed``.
    3. ``removed_by_category == "deleted"`` or ``body == "[deleted]"`` →
       ``deleted_by_author``. The category is keyed on before any body predicate
       because a deleted LINK post carries an empty ``selftext``, not the marker.
    4. Any other non-None ``removed_by_category``, whatever the body (a removed link
       post also has an empty ``selftext``): ``"moderator"`` → ``removed_by_moderator``;
       a value in ``REDDIT_REMOVAL_CATEGORIES`` → ``removed_by_reddit``; an unknown
       value → ``removed_by_reddit`` (fail closed, never live). This includes the
       observed-but-unexplained value ``"author"``.
    5. ``body is None`` (key absent on the wire) → hold: ``gone_unconfirmed`` with
       ``misses + 1`` (an item already ``gone`` stays ``gone``). Never live, and
       never escalated to ``gone`` by this rule alone: only rule 2 confirms absence.
    6. ``body == "[removed]"`` with no category → ``removed_by_moderator``.
    7. ``author is None`` on a LINK post with no category → deletion pending an
       ``info()`` check: the same hold as rule 5.
    8. Otherwise the content is intact → ``live`` with ``misses = 0``. This is the
       only way ``removed_*``, ``gone_unconfirmed`` and ``gone`` return to live: intact
       content and no ``removed_by_category``. Author state: ``author is None`` with
       ``author_fullname`` absent → ``account_deleted`` (content stays; the caller
       scrubs author fields only); author present with ``author_fullname`` present →
       ``known``; any other combination keeps the prior author state.

    On every non-live outcome the author state is carried over unchanged: a
    ``[deleted]`` body or a removal hides the author without saying anything about
    the account.

    ``scrub`` is True only on the transition INTO one of ``SCRUB_STATES`` from a state
    outside it. Re-observing an already scrubbed item asks for nothing, and a hold
    never scrubs. Rules 3, 4, 6 and 8 reset ``misses`` to 0 because the item was
    observed; rules 2, 5 and 7 add one.
    """
    if misses < 0:
        msg = f"misses must be >= 0, got {misses}"
        raise ValueError(msg)
    if prior_state is ContentState.DELETED_BY_AUTHOR:
        return Decision(prior_state, prior_author, False, misses)
    if obs.returned_by_info is False:
        return _hold(prior_state, prior_author, misses, escalate=True)
    if obs.removed_by_category == DELETED_CATEGORY or obs.body == DELETED_MARKER:
        return _settle(prior_state, prior_author, ContentState.DELETED_BY_AUTHOR)
    if obs.removed_by_category is not None:
        return _settle(prior_state, prior_author, _classify_removal(obs.removed_by_category))
    if obs.body is None:
        return _hold(prior_state, prior_author, misses, escalate=False)
    if obs.body == REMOVED_MARKER:
        return _settle(prior_state, prior_author, ContentState.REMOVED_BY_MODERATOR)
    if obs.author is None and obs.is_link_post:
        return _hold(prior_state, prior_author, misses, escalate=False)
    return _settle(prior_state, _author_state(prior_author, obs), ContentState.LIVE)


def _classify_removal(category: str) -> ContentState:
    """Map a non-``deleted`` ``removed_by_category`` onto a removal state, failing closed."""
    if category == MODERATOR_CATEGORY:
        return ContentState.REMOVED_BY_MODERATOR
    return ContentState.REMOVED_BY_REDDIT


def _settle(
    prior_state: ContentState, author_state: AuthorState, new_state: ContentState
) -> Decision:
    """The item was observed with a definite state: reset misses, scrub on entry."""
    scrub = new_state in SCRUB_STATES and prior_state not in SCRUB_STATES
    return Decision(new_state, author_state, scrub, 0)


def _hold(
    prior_state: ContentState, prior_author: AuthorState, misses: int, *, escalate: bool
) -> Decision:
    """The item could not be confirmed: count a miss and hold it out of ``live``."""
    new_misses = misses + 1
    if prior_state is ContentState.GONE or (escalate and new_misses >= GONE_AT_MISSES):
        scrub = prior_state not in SCRUB_STATES
        return Decision(ContentState.GONE, prior_author, scrub, new_misses)
    return Decision(ContentState.GONE_UNCONFIRMED, prior_author, False, new_misses)


def _author_state(prior: AuthorState, obs: Observation) -> AuthorState:
    """Author state for intact content; inconclusive combinations keep the prior value."""
    if obs.author is None and not obs.author_fullname_present:
        return AuthorState.ACCOUNT_DELETED
    if obs.author is not None and obs.author_fullname_present:
        return AuthorState.KNOWN
    return prior
