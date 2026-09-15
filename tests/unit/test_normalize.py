"""Tests for ``insightminer.core.normalize``: raw Reddit JSON -> PostRow / CommentRow / Reject.

Fixtures under tests/fixtures/json/synthetic are hand-written placeholders (see the README
there); the assertions below describe the contract the M1a ``probe`` captures must satisfy.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from insightminer.core.models import (
    NORMALIZER_VERSION,
    CommentRow,
    CrosspostParent,
    PostRow,
    Reject,
)
from insightminer.core.normalize import (
    ALLOWED_ATTRIBUTES,
    ALLOWED_TAGS,
    REQUIRED_COMMENT_KEYS,
    REQUIRED_POST_KEYS,
    canonicalize,
    clean_text,
    is_bot_author,
    normalize_comment,
    normalize_post,
    render_markdown,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "json" / "synthetic"
POST_ID = "1abc2de"


def load(name: str) -> dict[str, Any]:
    with (FIXTURES / name).open(encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data


def post(raw: dict[str, Any], source: str = "r/premiere/new") -> PostRow:
    result = normalize_post(raw, source=source)
    assert isinstance(result, PostRow), result
    return result


def comment(raw: dict[str, Any], post_id: str = POST_ID, source: str = "comments") -> CommentRow:
    result = normalize_comment(raw, source=source, post_reddit_id=post_id)
    assert isinstance(result, CommentRow), result
    return result


def reject_post(raw: Any, source: str = "r/premiere/new") -> Reject:
    result = normalize_post(raw, source=source)
    assert isinstance(result, Reject), result
    return result


def reject_comment(raw: Any, post_id: str = POST_ID) -> Reject:
    result = normalize_comment(raw, source="comments", post_reddit_id=post_id)
    assert isinstance(result, Reject), result
    return result


# --- fixtures: every column ---------------------------------------------------------------


def test_link_post_fixture_maps_every_column() -> None:
    row = post(load("post_link.json"))
    assert row.reddit_id == "1abc2de"
    assert row.fullname == "t3_1abc2de"
    assert row.subreddit == "premiere"
    assert row.subreddit_id == "t5_2s9fq"
    assert row.author == "editorguy"
    assert row.author_fullname == "t2_abcd12"
    assert row.author_flair_text == "Premiere Pro 2026"
    assert row.author_is_bot is False
    assert row.title == "Premiere 2026 crashes on export with H.264 after update"
    assert row.selftext == ""
    assert row.selftext_html == ""
    assert row.url == "https://example.com/blog/premiere-crash"
    assert row.domain == "example.com"
    assert row.permalink == (
        "/r/premiere/comments/1abc2de/premiere_2026_crashes_on_export_with_h264_after/"
    )
    assert row.created_utc == 1757649600 and type(row.created_utc) is int
    assert row.edited_utc is None
    assert row.score == 128
    assert row.upvote_ratio == 0.94
    assert row.num_comments == 84
    assert row.link_flair_text == "Bug"
    assert row.over_18 is False
    assert row.spoiler is False
    assert row.is_self is False
    assert row.is_video is False
    assert row.is_gallery is False
    assert row.post_hint == "link"
    assert row.locked is False
    assert row.stickied is False
    assert row.archived is False
    assert row.distinguished is None
    assert row.crosspost_parent is None
    assert row.num_crossposts == 0
    assert row.removed_by_category is None
    assert row.source == "r/premiere/new"
    assert row.normalizer_version == NORMALIZER_VERSION


def test_self_post_fixture_renders_markdown_and_lowercases_subreddit() -> None:
    row = post(load("post_self.json"), source="r/videoediting/new")
    assert row.subreddit == "videoediting"
    assert row.is_self is True
    assert row.is_gallery is None  # key absent on the wire -> typed None, not False
    assert row.edited_utc == 1757653200 and type(row.edited_utc) is int
    assert row.selftext is not None and row.selftext.startswith("Since the **26.1** update")
    html = row.selftext_html
    assert html is not None
    assert "<strong>26.1</strong>" in html
    assert "<table>" in html and "<td>smooth</td>" in html
    assert "<ol>" in html and "<em>Mercury</em>" in html
    assert "<script" not in html
    assert "&lt;script&gt;" in html  # raw HTML in the source is shown as text


def test_deleted_link_post_fixture() -> None:
    row = post(load("post_deleted_link.json"))
    assert row.author is None
    assert row.author_fullname is None
    assert row.author_is_bot is False
    assert row.removed_by_category == "deleted"
    assert row.selftext == "" and row.selftext_html == ""
    assert row.title == "Free LUT pack for Premiere (my site)"  # titles survive author deletion


def test_comment_fixture_maps_every_column() -> None:
    row = comment(load("comment.json"))
    assert row.reddit_id == "k1m2n3o"
    assert row.fullname == "t1_k1m2n3o"
    assert row.post_reddit_id == POST_ID
    assert row.parent_fullname == "t3_1abc2de"
    assert row.author == "helper_hank"
    assert row.author_fullname == "t2_zz99yy"
    assert row.author_is_bot is False
    assert row.body is not None and row.body.startswith("Try turning off **hardware")
    assert row.body_html == (
        "<p>Try turning off <strong>hardware-accelerated encoding</strong> in the export "
        "settings. Fixed it for me on 26.0.1.</p>\n"
    )
    assert row.created_utc == 1757653800
    assert row.edited_utc is None
    assert row.score == 45
    assert row.depth == 0
    assert row.permalink is not None and row.permalink.endswith("/k1m2n3o/")
    assert row.is_submitter is False
    assert row.stickied is False
    assert row.distinguished is None
    assert row.source == "comments"
    assert row.normalizer_version == NORMALIZER_VERSION


def test_deleted_comment_fixture() -> None:
    row = comment(load("comment_deleted.json"))
    assert row.author is None
    assert row.author_fullname is None
    assert row.body == "[deleted]"
    assert row.body_html == "<p>[deleted]</p>\n"
    assert row.parent_fullname == "t1_k1m2n3o"
    assert row.depth == 1


# --- required keys -> Reject -------------------------------------------------------------


def test_required_key_sets_are_the_plans() -> None:
    assert set(REQUIRED_POST_KEYS) == {"id", "created_utc", "subreddit"}
    assert set(REQUIRED_COMMENT_KEYS) == {"id", "created_utc"}


@pytest.mark.parametrize("key", REQUIRED_POST_KEYS)
def test_missing_required_post_key_rejects_and_preserves_raw(key: str) -> None:
    raw = load("post_link.json")
    del raw[key]
    rej = reject_post(raw)
    assert key in rej.error
    assert rej.raw == raw  # the exact input is preserved for raw_rejects


@pytest.mark.parametrize("key", REQUIRED_POST_KEYS)
def test_null_required_post_key_rejects(key: str) -> None:
    raw = load("post_link.json")
    raw[key] = None
    assert key in reject_post(raw).error


@pytest.mark.parametrize("key", REQUIRED_COMMENT_KEYS)
def test_missing_required_comment_key_rejects(key: str) -> None:
    raw = load("comment.json")
    del raw[key]
    rej = reject_comment(raw)
    assert key in rej.error and rej.raw == raw


def test_empty_id_rejects() -> None:
    raw = load("post_link.json")
    raw["id"] = ""
    assert "id" in reject_post(raw).error


def test_not_a_mapping_rejects_instead_of_raising() -> None:
    assert isinstance(normalize_post(["not", "a", "dict"], source="x"), Reject)  # type: ignore[arg-type]
    assert isinstance(normalize_comment(None, source="x", post_reddit_id="a"), Reject)  # type: ignore[arg-type]


# --- typed coercion ----------------------------------------------------------------------


def test_created_utc_float_becomes_int() -> None:
    raw = load("post_link.json")
    raw["created_utc"] = 1757649600.7
    assert post(raw).created_utc == 1757649600


@pytest.mark.parametrize("bad", ["1757649600", True, [1], {"x": 1}, float("nan"), float("inf")])
def test_created_utc_wrong_shape_rejects(bad: Any) -> None:
    raw = load("post_link.json")
    raw["created_utc"] = bad
    assert "created_utc" in reject_post(raw).error


@pytest.mark.parametrize(
    ("wire", "expected"),
    [
        (False, None),
        (True, None),
        (None, None),
        (1757653200.0, 1757653200),
        (1757653200, 1757653200),
    ],
)
def test_edited_maps_to_edited_utc(wire: Any, expected: int | None) -> None:
    raw = load("post_link.json")
    raw["edited"] = wire
    assert post(raw).edited_utc == expected


def test_edited_wrong_shape_rejects() -> None:
    raw = load("post_link.json")
    raw["edited"] = "yesterday"
    assert "edited" in reject_post(raw).error


@pytest.mark.parametrize("wire", ["[deleted]", None])
def test_deleted_or_null_author_is_none(wire: Any) -> None:
    raw = load("post_link.json")
    raw["author"] = wire
    assert post(raw).author is None


def test_absent_author_and_author_fullname_are_none() -> None:
    raw = load("post_link.json")
    del raw["author"]
    del raw["author_fullname"]
    row = post(raw)
    assert row.author is None and row.author_fullname is None


@pytest.mark.parametrize(
    ("key", "bad"),
    [("score", "128"), ("score", 12.5), ("over_18", 1), ("title", 7), ("upvote_ratio", "0.9")],
)
def test_wrong_typed_optional_value_rejects_loudly_instead_of_becoming_none(
    key: str, bad: Any
) -> None:
    """Shape drift must surface as a reject naming the field, never as a silently NULL column."""
    raw = load("post_link.json")
    raw[key] = bad
    assert key in reject_post(raw).error


def test_integral_float_is_accepted_for_int_columns() -> None:
    raw = load("post_link.json")
    raw["score"] = 128.0
    assert post(raw).score == 128


def test_int_is_accepted_for_float_columns() -> None:
    raw = load("post_link.json")
    raw["upvote_ratio"] = 1
    assert post(raw).upvote_ratio == 1.0


def test_subreddit_is_lowercased() -> None:
    raw = load("post_link.json")
    raw["subreddit"] = "PrEmIeRe"
    assert post(raw).subreddit == "premiere"


def test_fullname_is_derived_when_name_is_absent() -> None:
    raw = load("post_link.json")
    del raw["name"]
    assert post(raw).fullname == "t3_1abc2de"
    craw = load("comment.json")
    del craw["name"]
    assert comment(craw).fullname == "t1_k1m2n3o"


def test_fullname_disagreeing_with_id_rejects() -> None:
    raw = load("post_link.json")
    raw["name"] = "t3_other"
    assert "name" in reject_post(raw).error


def test_source_is_passed_through_verbatim() -> None:
    assert post(load("post_link.json"), source="info").source == "info"


def test_empty_source_rejects() -> None:
    assert "source" in reject_post(load("post_link.json"), source="").error


# --- crosspost parent: id + subreddit only -----------------------------------------------


def test_crosspost_parent_list_is_reduced_to_id_and_subreddit() -> None:
    raw = load("post_link.json")
    raw["crosspost_parent"] = "t3_zzz111"
    raw["crosspost_parent_list"] = [
        {
            "id": "zzz111",
            "subreddit": "Premiere",
            "title": "PARENT TITLE MUST NOT LEAK",
            "selftext": "PARENT BODY MUST NOT LEAK",
            "author": "parent_author",
        }
    ]
    row = post(raw)
    assert row.crosspost_parent == CrosspostParent(id="zzz111", subreddit="premiere")
    dumped = row.model_dump_json()
    assert "MUST NOT LEAK" not in dumped and "parent_author" not in dumped


def test_crosspost_parent_fullname_alone_gives_id_without_subreddit() -> None:
    raw = load("post_link.json")
    raw["crosspost_parent"] = "t3_zzz111"
    assert post(raw).crosspost_parent == CrosspostParent(id="zzz111", subreddit=None)


def test_empty_crosspost_parent_list_falls_back_to_fullname() -> None:
    raw = load("post_link.json")
    raw["crosspost_parent"] = "t3_zzz111"
    raw["crosspost_parent_list"] = []
    assert post(raw).crosspost_parent == CrosspostParent(id="zzz111", subreddit=None)


def test_canonical_raw_keeps_only_the_parent_pointer_of_a_crosspost() -> None:
    """KI-016: the canonical dict is what ``posts.raw_json`` stores, so the parent's text
    and author must already be gone here, not only on the normalized row."""
    raw = load("post_self.json")
    raw["crosspost_parent"] = "t3_zzz111"
    raw["crosspost_parent_list"] = [
        {
            "id": "zzz111",
            "subreddit": "premiere",
            "title": "parent-title-zq7",
            "selftext": "parent-body-zq7",
            "selftext_html": "<p>parent-body-zq7</p>",
            "author": "parent-author-zq7",
        }
    ]
    out = canonicalize(raw)
    assert out["crosspost_parent_list"] == [{"id": "zzz111", "subreddit": "premiere"}]
    assert "zq7" not in repr(out)
    assert post(raw).crosspost_parent == CrosspostParent(id="zzz111", subreddit="premiere")


def test_a_rejected_crosspost_keeps_no_parent_text_either() -> None:
    raw = load("post_self.json")
    del raw["created_utc"]  # a required field missing: the item becomes a reject
    raw["crosspost_parent_list"] = [
        {"id": "zzz111", "subreddit": "premiere", "selftext": "parent-body-zq7"}
    ]
    reject = reject_post(raw)
    assert "zq7" not in repr(reject.raw)
    assert reject.raw["crosspost_parent_list"] == [{"id": "zzz111", "subreddit": "premiere"}]


def test_crosspost_parent_list_of_wrong_shape_rejects() -> None:
    raw = load("post_link.json")
    raw["crosspost_parent_list"] = "t3_zzz111"
    assert "crosspost_parent_list" in reject_post(raw).error


# --- text hygiene ------------------------------------------------------------------------


def test_control_characters_are_stripped_but_whitespace_kept() -> None:
    assert clean_text("a\x00b\x07c\x0bd\x0ce\x1ff\ttab\nnl\rcr") == "abcdef\ttab\nnl\rcr"
    assert clean_text("\x00x\x08\x0b\x0c\x0e\x1f y\t\n\r") == "x y\t\n\r"
    assert clean_text("plain") == "plain"


def test_lone_surrogates_are_replaced_so_downstream_encoders_never_fail() -> None:
    out = clean_text("ok \ud800 bad")
    assert out == "ok � bad"
    out.encode("utf-8")  # must not raise


def test_control_characters_stripped_from_post_and_comment_text_fields() -> None:
    raw = load("post_link.json")
    raw["title"] = "Crash\x00 on\x07 export"
    raw["selftext"] = "line\x0b1\nline 2"
    raw["link_flair_text"] = "Bu\x01g"
    row = post(raw)
    assert row.title == "Crash on export"
    assert row.selftext == "line1\nline 2"
    assert row.link_flair_text == "Bug"
    craw = load("comment.json")
    craw["body"] = "fix\x00ed"
    assert comment(craw).body == "fixed"


# --- markdown rendering / sanitization ---------------------------------------------------

ADVERSARIAL_MARKDOWN = [
    "<script>alert(1)</script>",
    "<SCRIPT SRC=//evil.example/x.js></SCRIPT>",
    "<img src=x onerror=alert(1)>",
    '<a href="javascript:alert(1)">x</a>',
    "[click](javascript:alert(1))",
    "[click](JaVaScRiPt:alert(1))",
    "[click](vbscript:msgbox(1))",
    "[click](data:text/html;base64,PHNjcmlwdD5hbGVydCgxKTwvc2NyaXB0Pg==)",
    "[click](  javascript:alert(1))",
    '<iframe src="https://evil.example"></iframe>',
    "<style>body{display:none}</style>",
    '<div style="background:url(javascript:alert(1))">x</div>',
    '<b onmouseover="alert(1)">hover</b>',
    "<svg onload=alert(1)>",
    '<math><mi xlink:href="javascript:alert(1)">x</mi></math>',
    '<object data="x"></object><embed src="x">',
    '<form action="https://evil.example"><input name=q></form>',
    '<a href="  javascript:alert(1)">sp</a>',
    '<a href="java&#09;script:alert(1)">ent</a>',
    "<!-- comment --><p>x</p>",
    '<a href="//evil.example/x">protocol relative</a>',
    "[prot](//evil.example/x)",
    "&lt;script&gt;text&lt;/script&gt;",
    "```html\n<script>alert(1)</script>\n```",
    "<details open ontoggle=alert(1)>",
    '<meta http-equiv=refresh content="0;url=javascript:alert(1)">',
    '<base href="javascript:alert(1)//">',
    "<link rel=stylesheet href=//evil.example/x.css>",
    "![img](https://evil.example/track.png)",
    "* item\n\n> quote <script>1</script>\n\n# head",
    "| a | b |\n|---|---|\n| <script>x</script> | y |",
]

# In sanitized output every literal "<" opens a real tag (text "<" is always "&lt;"), so tags can
# be pulled out with a regex and inspected one by one; text content is deliberately ignored.
TAG_RE = re.compile(r"<[^>]*>")
TAG_NAME_RE = re.compile(r"^</?\s*([a-zA-Z][a-zA-Z0-9]*)")
ATTR_RE = re.compile(r'\s([a-zA-Z:_-]+)(?:\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^\s>]+)))?')
FORBIDDEN_TAGS = {
    "script", "iframe", "style", "object", "embed", "form", "input", "svg", "math",
    "meta", "base", "link", "img",
}  # fmt: skip
ALLOWED_ATTRIBUTE_NAMES = {"rel", *(a for attrs in ALLOWED_ATTRIBUTES.values() for a in attrs)}


def assert_safe_html(out: str) -> None:
    assert isinstance(out, str)
    assert "<!--" not in out, out
    for tag in TAG_RE.findall(out):
        name_match = TAG_NAME_RE.match(tag)
        assert name_match is not None, tag
        name = name_match.group(1).lower()
        assert name not in FORBIDDEN_TAGS, tag
        assert name in ALLOWED_TAGS, tag
        if tag.startswith("</"):
            continue
        for attr, dq, sq, bare in ATTR_RE.findall(tag[len(name) + 1 :]):
            attr = attr.lower()
            value = (dq or sq or bare).strip().lower()
            assert not attr.startswith("on"), tag
            assert attr in ALLOWED_ATTRIBUTE_NAMES, tag
            assert attr != "style", tag
            if attr in {"href", "src"}:
                assert not value.startswith(("javascript:", "vbscript:", "data:", "//")), tag


@pytest.mark.parametrize("payload", ADVERSARIAL_MARKDOWN)
def test_render_markdown_neutralizes_adversarial_input(payload: str) -> None:
    assert_safe_html(render_markdown(payload))


def test_render_markdown_keeps_ordinary_formatting() -> None:
    out = render_markdown(
        '**bold** _it_ `code` ~~gone~~ [r](https://example.com/a "t") /r/premiere'
    )
    assert "<strong>bold</strong>" in out
    assert "<em>it</em>" in out
    assert "<code>code</code>" in out
    assert "<s>gone</s>" in out
    assert 'href="https://example.com/a"' in out and 'title="t"' in out
    assert "noopener" in out and "noreferrer" in out
    assert_safe_html(out)


def test_render_markdown_keeps_site_relative_links_but_drops_protocol_relative_ones() -> None:
    out = render_markdown("[sub](/r/premiere) [evil](//evil.example/x)")
    assert 'href="/r/premiere"' in out
    assert "evil.example" not in out or 'href="//' not in out
    assert_safe_html(out)


def test_render_markdown_strips_inline_styles_and_classes() -> None:
    out = render_markdown("| a | b |\n|:--|--:|\n| 1 | 2 |\n\n```python\nx = 1\n```")
    assert "style=" not in out and "class=" not in out
    assert "<table>" in out and "<pre><code>" in out


def test_render_markdown_edge_values() -> None:
    assert render_markdown("") == ""
    assert render_markdown("[deleted]") == "<p>[deleted]</p>\n"
    assert render_markdown("[removed]") == "<p>[removed]</p>\n"


def test_render_markdown_strips_control_characters_first() -> None:
    assert render_markdown("a\x00b") == "<p>ab</p>\n"


# --- bots --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("author", "distinguished", "stickied", "expected"),
    [
        ("AutoModerator", None, False, True),
        ("automoderator", None, None, True),
        ("RemindMeBot", None, False, True),
        ("sneakpeekbot", None, False, True),
        ("SaveVideo", None, False, True),  # known-bot list, does not end in "bot"
        ("editorguy", None, False, False),
        ("editorguy", "moderator", True, True),  # moderator-distinguished sticky
        ("editorguy", "moderator", False, False),
        ("editorguy", "admin", True, False),
        ("editorguy", None, True, False),
        (None, None, False, False),
        (None, "moderator", True, True),
        ("robotics_fan", None, False, False),  # "bot" inside the name is not a suffix
    ],
)
def test_is_bot_author_heuristic(
    author: str | None, distinguished: str | None, stickied: bool | None, expected: bool
) -> None:
    assert is_bot_author(author, distinguished, stickied) is expected


def test_author_is_bot_is_per_item_never_inherited() -> None:
    automod = load("comment.json")
    automod.update(
        author="AutoModerator", author_fullname="t2_6l4z3", id="aaa111", name="t1_aaa111"
    )
    human_reply = load("comment.json")
    human_reply.update(id="bbb222", name="t1_bbb222", parent_id="t1_aaa111", depth=1)
    assert comment(automod).author_is_bot is True
    assert comment(human_reply).author_is_bot is False
    sticky = load("post_link.json")
    sticky.update(distinguished="moderator", stickied=True)
    assert post(sticky).author_is_bot is True
    reply_under_sticky = load("comment.json")
    reply_under_sticky.update(distinguished=None, stickied=False)
    assert comment(reply_under_sticky).author_is_bot is False


# --- comments ----------------------------------------------------------------------------


def test_comment_link_id_disagreeing_with_post_id_rejects() -> None:
    raw = load("comment.json")
    rej = reject_comment(raw, post_id="different")
    assert "link_id" in rej.error


def test_comment_without_link_id_trusts_the_caller() -> None:
    raw = load("comment.json")
    del raw["link_id"]
    assert comment(raw, post_id="whatever").post_reddit_id == "whatever"


def test_comment_from_info_endpoint_has_no_depth() -> None:
    raw = load("comment.json")
    del raw["depth"]
    assert comment(raw).depth is None


def test_comment_empty_post_id_rejects() -> None:
    assert "post_reddit_id" in reject_comment(load("comment.json"), post_id="").error


# --- canonicalize: PRAW shape and wire shape produce identical rows ------------------------


def praw_shape(wire: dict[str, Any]) -> dict[str, Any]:
    """What ``vars(praw_obj)`` looks like after PRAW objectifies author/subreddit."""
    shaped = dict(wire)
    shaped["author"] = (
        None if wire.get("author") in (None, "[deleted]") else {"name": wire["author"]}
    )
    shaped["subreddit"] = {"display_name": wire["subreddit"]}
    shaped["_reddit"] = object()
    shaped["_fetched"] = True
    shaped["_comments_by_id"] = {}
    shaped["comment_limit"] = 2048
    shaped["comment_sort"] = "confidence"
    return shaped


@pytest.mark.parametrize("name", ["post_link.json", "post_self.json", "post_deleted_link.json"])
def test_praw_shaped_post_normalizes_identically(name: str) -> None:
    wire = load(name)
    assert post(praw_shape(wire)) == post(wire)


@pytest.mark.parametrize("name", ["comment.json", "comment_deleted.json"])
def test_praw_shaped_comment_normalizes_identically(name: str) -> None:
    wire = load(name)
    shaped = praw_shape(wire)
    shaped["_replies"] = object()
    del shaped["replies"]
    assert comment(shaped) == comment(wire)


def test_canonicalize_unwraps_listing_envelope() -> None:
    wire = load("post_link.json")
    assert canonicalize({"kind": "t3", "data": wire}) == canonicalize(wire)
    assert post({"kind": "t3", "data": wire}) == post(wire)


def test_canonicalize_drops_private_praw_only_and_replies_keys() -> None:
    out = canonicalize(praw_shape(load("comment.json")) | {"_replies": 1})
    assert not any(k.startswith("_") for k in out)
    assert "comment_limit" not in out and "comment_sort" not in out
    assert "replies" not in out
    assert out["author"] == "helper_hank" and out["subreddit"] == "premiere"


def test_canonicalize_leaves_wire_shape_untouched_apart_from_replies() -> None:
    wire = load("post_link.json")
    assert canonicalize(wire) == wire
    assert canonicalize(wire) is not wire


class _Footgun:
    """Stands in for a lazy PRAW object: any attribute access would fire an HTTP request."""

    touched = 0

    def __getattr__(self, name: str) -> Any:
        type(self).touched += 1
        raise RuntimeError(name)  # not AttributeError: getattr(..., default) must not swallow it


def test_objectified_values_are_never_probed_with_getattr() -> None:
    raw = load("post_link.json")
    raw["author"] = _Footgun()
    rej = reject_post(raw)
    assert "author" in rej.error
    assert _Footgun.touched == 0


# --- hypothesis: key deletion, never raises, adversarial markdown -----------------------

# wire key -> row fields that must read None when the key is absent
OPTIONAL_POST_KEYS: dict[str, tuple[str, ...]] = {
    "subreddit_id": ("subreddit_id",),
    "author": ("author",),
    "author_fullname": ("author_fullname",),
    "author_flair_text": ("author_flair_text",),
    "title": ("title",),
    "selftext": ("selftext", "selftext_html"),
    "url": ("url",),
    "domain": ("domain",),
    "permalink": ("permalink",),
    "edited": ("edited_utc",),
    "score": ("score",),
    "upvote_ratio": ("upvote_ratio",),
    "num_comments": ("num_comments",),
    "link_flair_text": ("link_flair_text",),
    "over_18": ("over_18",),
    "spoiler": ("spoiler",),
    "is_self": ("is_self",),
    "is_video": ("is_video",),
    "is_gallery": ("is_gallery",),
    "post_hint": ("post_hint",),
    "locked": ("locked",),
    "stickied": ("stickied",),
    "archived": ("archived",),
    "distinguished": ("distinguished",),
    "num_crossposts": ("num_crossposts",),
    "removed_by_category": ("removed_by_category",),
}

OPTIONAL_COMMENT_KEYS: dict[str, tuple[str, ...]] = {
    "parent_id": ("parent_fullname",),
    "author": ("author",),
    "author_fullname": ("author_fullname",),
    "body": ("body", "body_html"),
    "edited": ("edited_utc",),
    "score": ("score",),
    "depth": ("depth",),
    "permalink": ("permalink",),
    "is_submitter": ("is_submitter",),
    "stickied": ("stickied",),
    "distinguished": ("distinguished",),
}

BASE_POST = load("post_self.json") | {"is_gallery": True}  # every optional key present and non-null
BASE_POST["author_flair_text"] = "flair"
BASE_POST["distinguished"] = "moderator"
BASE_POST["removed_by_category"] = "moderator"
BASE_COMMENT = load("comment.json") | {"edited": 1757657400.0, "distinguished": "moderator"}


def test_optional_key_tables_cover_every_optional_wire_key_in_the_fixtures() -> None:
    post_keys = set(BASE_POST) - set(REQUIRED_POST_KEYS)
    assert set(OPTIONAL_POST_KEYS) <= post_keys
    assert set(OPTIONAL_COMMENT_KEYS) <= set(BASE_COMMENT) - set(REQUIRED_COMMENT_KEYS)


@settings(max_examples=200, deadline=None)
@given(st.sets(st.sampled_from(sorted(OPTIONAL_POST_KEYS))))
def test_deleting_any_optional_post_keys_yields_a_row_with_those_fields_none(
    deleted: set[str],
) -> None:
    raw = {k: v for k, v in BASE_POST.items() if k not in deleted}
    row = post(raw)
    baseline = post(BASE_POST).model_dump()
    for key, fields in OPTIONAL_POST_KEYS.items():
        for field in fields:
            if key in deleted:
                assert getattr(row, field) is None, field
            else:
                assert getattr(row, field) == baseline[field], field


@settings(max_examples=100, deadline=None)
@given(st.sets(st.sampled_from(sorted(OPTIONAL_COMMENT_KEYS))))
def test_deleting_any_optional_comment_keys_yields_a_row_with_those_fields_none(
    deleted: set[str],
) -> None:
    raw = {k: v for k, v in BASE_COMMENT.items() if k not in deleted}
    row = comment(raw)
    baseline = comment(BASE_COMMENT).model_dump()
    for key, fields in OPTIONAL_COMMENT_KEYS.items():
        for field in fields:
            if key in deleted:
                assert getattr(row, field) is None, field
            else:
                assert getattr(row, field) == baseline[field], field


@given(st.sets(st.sampled_from(REQUIRED_POST_KEYS), min_size=1))
def test_deleting_any_required_post_key_rejects(deleted: set[str]) -> None:
    raw = {k: v for k, v in BASE_POST.items() if k not in deleted}
    rej = reject_post(raw)
    assert any(key in rej.error for key in deleted)


@given(st.sets(st.sampled_from(REQUIRED_COMMENT_KEYS), min_size=1))
def test_deleting_any_required_comment_key_rejects(deleted: set[str]) -> None:
    raw = {k: v for k, v in BASE_COMMENT.items() if k not in deleted}
    rej = reject_comment(raw)
    assert any(key in rej.error for key in deleted)


json_scalars = st.none() | st.booleans() | st.integers() | st.floats() | st.text(max_size=40)
json_values = st.recursive(
    json_scalars,
    lambda children: (
        st.lists(children, max_size=3) | st.dictionaries(st.text(max_size=8), children, max_size=3)
    ),
    max_leaves=8,
)
random_dicts = st.dictionaries(st.text(max_size=20), json_values, max_size=12)
mutated_posts = st.dictionaries(st.sampled_from(sorted(BASE_POST)), json_values, max_size=8).map(
    lambda overrides: {**BASE_POST, **overrides}
)
mutated_comments = st.dictionaries(
    st.sampled_from(sorted(BASE_COMMENT)), json_values, max_size=8
).map(lambda overrides: {**BASE_COMMENT, **overrides})


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(random_dicts | mutated_posts)
def test_normalize_post_never_raises(raw: dict[str, Any]) -> None:
    result = normalize_post(raw, source="fuzz")
    assert isinstance(result, PostRow | Reject)
    if isinstance(result, Reject):
        assert result.error


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(random_dicts | mutated_comments)
def test_normalize_comment_never_raises(raw: dict[str, Any]) -> None:
    result = normalize_comment(raw, source="fuzz", post_reddit_id=POST_ID)
    assert isinstance(result, CommentRow | Reject)


@settings(max_examples=300, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(st.text(max_size=400))
def test_render_markdown_never_raises_and_is_always_safe(text: str) -> None:
    assert_safe_html(render_markdown(text))


@settings(max_examples=150, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    st.lists(st.sampled_from(ADVERSARIAL_MARKDOWN), min_size=1, max_size=4), st.text(max_size=30)
)
def test_render_markdown_is_safe_for_adversarial_combinations(parts: list[str], glue: str) -> None:
    assert_safe_html(render_markdown(glue.join(parts)))
