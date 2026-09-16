"""Normalized row models: the only shape that crosses the normalize boundary.

``core.normalize`` turns Reddit wire JSON into these rows; ``db`` persists them; ``services``
and ``web`` read them. The models are deliberately *strict*:

* every column is required (no silent ``None`` defaults, so a producer that forgets a column
  fails loudly instead of writing a 100 %-NULL column), except ``normalizer_version`` which
  defaults to the one current value;
* pydantic strict mode: no ``"12" -> 12`` or ``1 -> True`` coercion. All wire coercion lives in
  ``core.normalize`` so there is exactly one place where Reddit's types are interpreted;
* ``extra="forbid"`` so a leaked wire key (or crosspost parent text) is an error;
* instances are frozen.

Timestamps are integer epoch seconds (Reddit's ``created_utc`` domain). ``subreddit`` is the
lowercase identity name. ``fullname`` is the ``t3_``/``t1_`` prefixed id.

Unknown upstream enum values (``post_hint``, ``subreddit_type``, ``removed_by_category``) are
stored raw and never coerced to a known value; ``count_unknown`` lets the collector count them
under the ``UNKNOWN_ENUM_COUNTER`` run counter.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any, Final

from pydantic import BaseModel, ConfigDict, Field, field_validator

#: Bump on any semantic change to a derived column; rows carry it so ``db reprocess`` can find
#: stale rows. Defined exactly once, here.
NORMALIZER_VERSION: Final = 1

#: Name of the run counter under which callers report unknown enum values (see the plan's
#: collector step 6).
UNKNOWN_ENUM_COUNTER: Final = "unknown_enum_values"


class _StrictRow(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", strict=True)


class CrosspostParent(_StrictRow):
    """The only two facts kept about a crosspost's parent. Parent text is never stored."""

    id: str = Field(min_length=1)
    subreddit: str | None

    @field_validator("subreddit")
    @classmethod
    def _lowercase(cls, value: str | None) -> str | None:
        return None if value is None else value.lower()


class PostRow(_StrictRow):
    """One Reddit submission (``t3``), normalized."""

    reddit_id: str = Field(min_length=1)
    fullname: str = Field(min_length=1)
    subreddit: str = Field(min_length=1)
    subreddit_id: str | None
    author: str | None
    author_fullname: str | None
    author_flair_text: str | None
    author_is_bot: bool
    title: str | None
    selftext: str | None
    selftext_html: str | None
    url: str | None
    domain: str | None
    permalink: str | None
    created_utc: int
    edited_utc: int | None
    score: int | None
    upvote_ratio: float | None
    num_comments: int | None
    link_flair_text: str | None
    over_18: bool | None
    spoiler: bool | None
    is_self: bool | None
    is_video: bool | None
    is_gallery: bool | None
    post_hint: str | None
    locked: bool | None
    stickied: bool | None
    archived: bool | None
    distinguished: str | None
    crosspost_parent: CrosspostParent | None
    num_crossposts: int | None
    removed_by_category: str | None
    source: str = Field(min_length=1)
    normalizer_version: int = NORMALIZER_VERSION

    @field_validator("subreddit")
    @classmethod
    def _lowercase(cls, value: str) -> str:
        return value.lower()


class CommentRow(_StrictRow):
    """One Reddit comment (``t1``), normalized. Tree position is the caller's concern."""

    reddit_id: str = Field(min_length=1)
    fullname: str = Field(min_length=1)
    post_reddit_id: str = Field(min_length=1)
    parent_fullname: str | None
    author: str | None
    author_fullname: str | None
    author_is_bot: bool
    body: str | None
    body_html: str | None
    created_utc: int
    edited_utc: int | None
    score: int | None
    depth: int | None
    permalink: str | None
    is_submitter: bool | None
    stickied: bool | None
    distinguished: str | None
    source: str = Field(min_length=1)
    normalizer_version: int = NORMALIZER_VERSION


class Reject(BaseModel):
    """A raw item the normalizer could not turn into a row; goes to ``raw_rejects``."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    raw: dict[str, Any]
    error: str = Field(min_length=1)


class KnownValues:
    """Registry of upstream enum values we have seen, per field.

    ``is_known`` is an exact, case-sensitive membership test. Unregistered fields raise
    ``KeyError`` so a typo cannot silently report "known".
    """

    __slots__ = ("_table",)

    def __init__(self, table: Mapping[str, Iterable[str]]) -> None:
        self._table: dict[str, frozenset[str]] = {
            field: frozenset(values) for field, values in table.items()
        }

    @property
    def fields(self) -> tuple[str, ...]:
        return tuple(self._table)

    def known(self, field: str) -> frozenset[str]:
        return self._table[field]

    def is_known(self, field: str, value: str) -> bool:
        return value in self._table[field]


#: Values observed on the wire as of 2026-09 (review §1.4 for ``removed_by_category``). Not an
#: official list: new values are stored raw and surface through ``count_unknown``.
KNOWN_VALUES: Final = KnownValues(
    {
        "post_hint": ("link", "image", "self", "hosted:video", "rich:video", "gallery"),
        "subreddit_type": (
            "public",
            "private",
            "restricted",
            "gold_restricted",
            "gold_only",
            "archived",
            "employees_only",
            "user",
        ),
        "removed_by_category": (
            "deleted",
            "moderator",
            "reddit",
            "author",
            "automod_filtered",
            "anti_evil_ops",
            "content_takedown",
            "copyright_takedown",
            "community_ops",
            "legal_operations",
        ),
    }
)


def count_unknown(row: PostRow | CommentRow, registry: KnownValues = KNOWN_VALUES) -> list[str]:
    """Return ``"field=value"`` for every registered enum field on ``row`` holding an unknown value.

    ``None`` is never unknown. The caller adds ``len(result)`` to the ``UNKNOWN_ENUM_COUNTER``
    run counter and may log the entries.
    """
    data = row.model_dump()
    unknown: list[str] = []
    for field in registry.fields:
        value = data.get(field)
        if value is None:
            continue
        if not registry.is_known(field, str(value)):
            unknown.append(f"{field}={value}")
    return unknown
