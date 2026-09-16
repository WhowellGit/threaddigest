"""Raw Reddit JSON -> ``PostRow`` / ``CommentRow`` / ``Reject``. Pure: dicts in, models out.

Input is the ``data`` object of a ``t3``/``t1`` listing child as a plain mapping. Both wire
shapes the collector meets are accepted through :func:`canonicalize`:

* **listing JSON** (``reddit.request()`` / ``/r/x/new.json``): ``author`` is a string,
  ``"[deleted]"`` for deleted accounts; ``subreddit`` is a string; ``replies`` is ``""`` or a
  nested listing;
* **PRAW-attribute JSON** (``vars(obj)`` of a ``Submission``/``Comment``, which is how comment
  trees arrive): ``author`` is ``{"name": ...}`` or ``None``, ``subreddit`` is
  ``{"display_name": ...}``, ``replies`` has moved to ``_replies``, and private ``_*`` keys plus
  PRAW-only attributes are present.

Both must normalize to identical rows (the shape-parity requirement). Everything here operates
on dicts only; nothing ever calls ``getattr`` on a value, because a lazy PRAW object fires an HTTP
request when a missing attribute is touched (design review §1.1).

Rules: required keys (``id``, ``created_utc``, and ``subreddit`` for posts) missing or ``None``
-> ``Reject``; optional keys absent or ``None`` -> typed ``None``; a present value of the wrong
type -> ``Reject`` naming the field (shape drift must be loud, never a silently NULL column);
``edited`` ``false``/``true`` -> ``None``, number -> ``int``; ``author`` ``"[deleted]"`` ->
``None``; ``crosspost_parent_list[0]`` reduced to ``{id, subreddit}``; ``selftext_html`` /
``body_html`` are *our* rendering (markdown-it + nh3), never Reddit's; control characters are
stripped from every string; ``subreddit`` is lowercased. ``normalize_*`` never raise.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Mapping
from typing import Any, Final, TypeGuard

import nh3
from markdown_it import MarkdownIt
from pydantic import ValidationError

from threaddigest.core.models import (
    NORMALIZER_VERSION,
    CommentRow,
    CrosspostParent,
    PostRow,
    Reject,
)

REQUIRED_POST_KEYS: Final = ("id", "created_utc", "subreddit")
REQUIRED_COMMENT_KEYS: Final = ("id", "created_utc")

DELETED_AUTHOR: Final = "[deleted]"

#: Bot accounts that do not end in "bot". Lowercase.
KNOWN_BOTS: Final = frozenset({"automoderator", "savevideo", "vredditdownloader"})

#: Public instance attributes PRAW adds to objects that are not Reddit fields.
PRAW_ONLY_KEYS: Final = frozenset({"comment_limit", "comment_sort"})

#: nh3 allow-list. Covers what Reddit-flavoured markdown produces and nothing else: no ``img``
#: (remote images would leak the viewer's address; the UI's CSP forbids them anyway), no
#: ``span``/``div``, no ``class``/``style``/``id``.
ALLOWED_TAGS: Final = frozenset(
    {
        "p", "br", "hr",
        "a", "em", "strong", "del", "s", "code", "pre", "blockquote",
        "ul", "ol", "li",
        "h1", "h2", "h3", "h4", "h5", "h6",
        "table", "thead", "tbody", "tr", "th", "td",
        "sup", "sub",
    }
)  # fmt: skip
ALLOWED_ATTRIBUTES: Final[dict[str, set[str]]] = {"a": {"href", "title"}, "ol": {"start"}}
ALLOWED_URL_SCHEMES: Final = frozenset({"http", "https", "mailto"})
LINK_REL: Final = "noopener noreferrer nofollow"

# \t \n \r are kept; everything else below 0x20 is stripped.
_CONTROL_RE: Final = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
# Lone surrogates (possible via JSON "\ud800" escapes) break UTF-8 encoders downstream.
_SURROGATE_RE: Final = re.compile(r"[\ud800-\udfff]")

_MARKDOWN: Final = MarkdownIt(
    "commonmark", {"html": False, "linkify": False, "typographer": False}
).enable(["table", "strikethrough"])


def _attribute_filter(tag: str, attribute: str, value: str) -> str | None:
    # nh3 checks schemes on absolute URLs; protocol-relative ones (``//host/x``) slip through as
    # "relative" and would point off-site, so drop them. Site-relative ``/r/...`` links stay.
    if attribute == "href" and value.lstrip().startswith("//"):
        return None
    return value


_CLEANER: Final = nh3.Cleaner(
    tags=set(ALLOWED_TAGS),
    attributes=ALLOWED_ATTRIBUTES,
    url_schemes=set(ALLOWED_URL_SCHEMES),
    link_rel=LINK_REL,
    strip_comments=True,
    attribute_filter=_attribute_filter,
)


class _InvalidFieldError(Exception):
    """A field could not be interpreted; becomes ``Reject(error="<field>: <message>")``."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(f"{field}: {message}")
        self.field = field
        self.message = message


# --- text -----------------------------------------------------------------------------------


def clean_text(text: str) -> str:
    """Strip C0 control characters (except tab/newline/CR) and replace lone surrogates."""
    text = _CONTROL_RE.sub("", text)
    return _SURROGATE_RE.sub("\ufffd", text)


def render_markdown(text: str) -> str:
    """Render Reddit-flavoured markdown to sanitized HTML.

    markdown-it-py (CommonMark + tables + strikethrough, raw HTML disabled so it is escaped as
    text) followed by nh3 with the allow-list above. Safe to store and render unescaped.
    """
    html: str = _MARKDOWN.render(clean_text(text))
    return _CLEANER.clean(html)


def is_bot_author(author: str | None, distinguished: str | None, stickied: bool | None) -> bool:
    """Heuristic bot flag, computed per item from that item's own fields (never inherited).

    True for AutoModerator and the small known-bot list, names ending in "bot" (case-insensitive),
    and moderator-distinguished stickies (megathread/boilerplate posts).
    """
    if distinguished == "moderator" and stickied is True:
        return True
    if author is None:
        return False
    name = author.lower()
    return name in KNOWN_BOTS or name.endswith("bot")


# --- canonical shape -------------------------------------------------------------------------


def canonicalize(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Map either wire shape to one canonical dict (see the module docstring).

    * unwraps a ``{"kind": "t3", "data": {...}}`` listing envelope;
    * drops private ``_*`` keys, PRAW-only attributes, and ``replies`` (children are their own
      rows; the nested listing would duplicate the tree into every row);
    * ``author`` given as ``{"name": ...}`` becomes the name; ``subreddit`` given as
      ``{"display_name": ...}`` becomes the display name;
    * every entry of ``crosspost_parent_list`` is reduced to ``{"id", "subreddit"}`` (KI-016):
      the canonical dict is what ``posts.raw_json`` and ``raw_rejects.raw_json`` store, and
      the parent's text and author must never be stored, because the parent lives in an
      unmonitored subreddit and is never reconciled (``docs/decisions/DECISIONS.md``).

    Values that are neither plain data nor mappings (e.g. a live PRAW object) are left untouched
    and rejected later by type, never probed with ``getattr``.
    """
    data: Mapping[str, Any] = raw
    if set(data) <= {"kind", "data"} and isinstance(data.get("data"), Mapping):
        data = data["data"]
    out: dict[str, Any] = {}
    for key, value in data.items():
        if not isinstance(key, str) or key.startswith("_") or key in PRAW_ONLY_KEYS:
            continue
        if key == "replies":
            continue
        out[key] = value
    author = out.get("author")
    if isinstance(author, Mapping):
        out["author"] = author.get("name")
    subreddit = out.get("subreddit")
    if isinstance(subreddit, Mapping):
        out["subreddit"] = subreddit.get("display_name")
    return _strip_crosspost_parents(out)


def _strip_crosspost_parents(data: dict[str, Any]) -> dict[str, Any]:
    """Reduce each crosspost parent record to its pointer, in place.

    A non-mapping entry (a list-in-list or any other shape drift) is reduced to an empty
    pointer, never passed through: this is the canonical dict stored as ``raw_json``, and a
    non-mapping entry could otherwise carry the parent's text/author verbatim into the store
    of an unmonitored, never-reconciled post (KI-016, external round one panel 2026-09-15; the
    earlier "left for the normalizer to reject" comment was false -- ``_crosspost_parent`` only
    inspects entry 0 and would silently fall through, storing the rest). A non-list value is
    left as is for the normalizer to reject by type.
    """
    parents = data.get("crosspost_parent_list")
    if isinstance(parents, list):
        data["crosspost_parent_list"] = [
            {"id": parent.get("id"), "subreddit": parent.get("subreddit")}
            if isinstance(parent, Mapping)
            else {"id": None, "subreddit": None}
            for parent in parents
        ]
    return data


# --- typed coercers: wire value -> column value, or _InvalidFieldError ----------------------


def _is_number(value: object) -> TypeGuard[int | float]:
    """True for int/float but not bool (a bool on the wire where a number belongs is drift)."""
    return isinstance(value, int | float) and not isinstance(value, bool)


def _finite(field: str, value: float) -> float:
    if not math.isfinite(value):
        raise _InvalidFieldError(field, "not a finite number")
    return value


def _require(data: Mapping[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        if data.get(key) is None:
            raise _InvalidFieldError(key, "required key missing")


def _req_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise _InvalidFieldError(key, f"expected str, got {type(value).__name__}")
    value = clean_text(value)
    if not value:
        raise _InvalidFieldError(key, "empty")
    return value


def _req_epoch(data: Mapping[str, Any], key: str) -> int:
    value = data.get(key)
    if _is_number(value):
        return int(_finite(key, value))
    raise _InvalidFieldError(key, f"expected number, got {type(value).__name__}")


def _opt_str(data: Mapping[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise _InvalidFieldError(key, f"expected str, got {type(value).__name__}")
    return clean_text(value)


def _opt_int(data: Mapping[str, Any], key: str) -> int | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, float):
        if not _finite(key, value).is_integer():
            raise _InvalidFieldError(key, f"expected int, got non-integral float {value!r}")
        return int(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    raise _InvalidFieldError(key, f"expected int, got {type(value).__name__}")


def _opt_float(data: Mapping[str, Any], key: str) -> float | None:
    value = data.get(key)
    if value is None:
        return None
    if _is_number(value):
        return float(_finite(key, value))
    raise _InvalidFieldError(key, f"expected float, got {type(value).__name__}")


def _opt_bool(data: Mapping[str, Any], key: str) -> bool | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise _InvalidFieldError(key, f"expected bool, got {type(value).__name__}")
    return value


def _author(data: Mapping[str, Any]) -> str | None:
    author = _opt_str(data, "author")
    return None if author == DELETED_AUTHOR else author


def _edited(data: Mapping[str, Any]) -> int | None:
    """``edited`` is ``false`` (never), ``true`` (legacy: edited, time unknown) or an epoch."""
    value = data.get("edited")
    if value is None or isinstance(value, bool):
        return None
    if _is_number(value):
        return int(_finite("edited", value))
    raise _InvalidFieldError("edited", f"expected bool or number, got {type(value).__name__}")


def _fullname(data: Mapping[str, Any], reddit_id: str, prefix: str) -> str:
    expected = f"{prefix}_{reddit_id}"
    name = data.get("name")
    if name is None:
        return expected
    if not isinstance(name, str):
        raise _InvalidFieldError("name", f"expected str, got {type(name).__name__}")
    if name != expected:
        raise _InvalidFieldError("name", f"{name!r} does not match id {reddit_id!r}")
    return name


def _crosspost_parent(data: Mapping[str, Any]) -> CrosspostParent | None:
    parents = data.get("crosspost_parent_list")
    if parents is not None and not isinstance(parents, list):
        raise _InvalidFieldError(
            "crosspost_parent_list", f"expected list, got {type(parents).__name__}"
        )
    if parents and isinstance(parents[0], Mapping):
        parent = canonicalize(parents[0])
        parent_id = parent.get("id")
        parent_sub = parent.get("subreddit")
        if isinstance(parent_id, str) and parent_id:
            subreddit = clean_text(parent_sub) if isinstance(parent_sub, str) else None
            return CrosspostParent(id=clean_text(parent_id), subreddit=subreddit)
    fullname = _opt_str(data, "crosspost_parent")
    if fullname:
        return CrosspostParent(id=fullname.removeprefix("t3_"), subreddit=None)
    return None


# --- entry points --------------------------------------------------------------------------


def _reject_raw(raw: object) -> dict[str, Any]:
    """The item as ``raw_rejects.raw_json`` keeps it: whole, apart from the crosspost parent
    text, which is never stored on any surface (KI-016)."""
    if isinstance(raw, Mapping):
        return _strip_crosspost_parents({str(key): value for key, value in raw.items()})
    return {"repr": repr(raw)[:1000]}


def _validation_message(exc: ValidationError) -> str:
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err["loc"]) or "<row>"
        parts.append(f"{loc}: {err['msg']}")
    return "; ".join(parts)


def _guarded[T: (PostRow, CommentRow)](raw: object, build: Callable[[], T]) -> T | Reject:
    """Run ``build``; convert every failure into a ``Reject``. The boundary never raises."""
    if not isinstance(raw, Mapping):
        return Reject(raw=_reject_raw(raw), error=f"not a mapping: {type(raw).__name__}")
    try:
        return build()
    except _InvalidFieldError as exc:
        return Reject(raw=_reject_raw(raw), error=str(exc))
    except ValidationError as exc:
        return Reject(raw=_reject_raw(raw), error=_validation_message(exc))
    except Exception as exc:  # noqa: BLE001 - boundary contract: one bad item becomes a
        # counted Reject (type and message recorded), never a crashed run.
        return Reject(raw=_reject_raw(raw), error=f"unexpected {type(exc).__name__}: {exc}")


def normalize_post(raw: Mapping[str, Any], *, source: str) -> PostRow | Reject:
    """Normalize one submission. ``source`` is provenance (e.g. ``"r/premiere/new"``)."""

    def build() -> PostRow:
        data = canonicalize(raw)
        _require(data, REQUIRED_POST_KEYS)
        reddit_id = _req_str(data, "id")
        author = _author(data)
        distinguished = _opt_str(data, "distinguished")
        stickied = _opt_bool(data, "stickied")
        selftext = _opt_str(data, "selftext")
        return PostRow(
            reddit_id=reddit_id,
            fullname=_fullname(data, reddit_id, "t3"),
            subreddit=_req_str(data, "subreddit").lower(),
            subreddit_id=_opt_str(data, "subreddit_id"),
            author=author,
            author_fullname=_opt_str(data, "author_fullname"),
            author_flair_text=_opt_str(data, "author_flair_text"),
            author_is_bot=is_bot_author(author, distinguished, stickied),
            title=_opt_str(data, "title"),
            selftext=selftext,
            selftext_html=None if selftext is None else render_markdown(selftext),
            url=_opt_str(data, "url"),
            domain=_opt_str(data, "domain"),
            permalink=_opt_str(data, "permalink"),
            created_utc=_req_epoch(data, "created_utc"),
            edited_utc=_edited(data),
            score=_opt_int(data, "score"),
            upvote_ratio=_opt_float(data, "upvote_ratio"),
            num_comments=_opt_int(data, "num_comments"),
            link_flair_text=_opt_str(data, "link_flair_text"),
            over_18=_opt_bool(data, "over_18"),
            spoiler=_opt_bool(data, "spoiler"),
            is_self=_opt_bool(data, "is_self"),
            is_video=_opt_bool(data, "is_video"),
            is_gallery=_opt_bool(data, "is_gallery"),
            post_hint=_opt_str(data, "post_hint"),
            locked=_opt_bool(data, "locked"),
            stickied=stickied,
            archived=_opt_bool(data, "archived"),
            distinguished=distinguished,
            crosspost_parent=_crosspost_parent(data),
            num_crossposts=_opt_int(data, "num_crossposts"),
            removed_by_category=_opt_str(data, "removed_by_category"),
            source=source,
            normalizer_version=NORMALIZER_VERSION,
        )

    return _guarded(raw, build)


def normalize_comment(
    raw: Mapping[str, Any], *, source: str, post_reddit_id: str
) -> CommentRow | Reject:
    """Normalize one comment of post ``post_reddit_id``.

    The caller knows which post the tree belongs to; when the wire carries ``link_id`` it must
    agree, otherwise the comment is rejected rather than filed under the wrong post. ``depth``
    is absent on ``/api/info`` results and stays ``None`` there.
    """

    def build() -> CommentRow:
        if not post_reddit_id:
            raise _InvalidFieldError("post_reddit_id", "empty")
        data = canonicalize(raw)
        _require(data, REQUIRED_COMMENT_KEYS)
        reddit_id = _req_str(data, "id")
        link_id = _opt_str(data, "link_id")
        if link_id is not None and link_id != f"t3_{post_reddit_id}":
            raise _InvalidFieldError(
                "link_id", f"{link_id!r} does not match post {post_reddit_id!r}"
            )
        author = _author(data)
        distinguished = _opt_str(data, "distinguished")
        stickied = _opt_bool(data, "stickied")
        body = _opt_str(data, "body")
        return CommentRow(
            reddit_id=reddit_id,
            fullname=_fullname(data, reddit_id, "t1"),
            post_reddit_id=post_reddit_id,
            parent_fullname=_opt_str(data, "parent_id"),
            author=author,
            author_fullname=_opt_str(data, "author_fullname"),
            author_is_bot=is_bot_author(author, distinguished, stickied),
            body=body,
            body_html=None if body is None else render_markdown(body),
            created_utc=_req_epoch(data, "created_utc"),
            edited_utc=_edited(data),
            score=_opt_int(data, "score"),
            depth=_opt_int(data, "depth"),
            permalink=_opt_str(data, "permalink"),
            is_submitter=_opt_bool(data, "is_submitter"),
            stickied=stickied,
            distinguished=distinguished,
            source=source,
            normalizer_version=NORMALIZER_VERSION,
        )

    return _guarded(raw, build)
