"""Theme rules: compile once, match many. Pure logic; ``regex`` with timeouts for UI-authored
patterns.

A theme is a list of :class:`Rule`\\ s in three groups. A post matches when::

    any(match rules) and not any(exclude rules) and (no only_in rules or any(only_in rules))

* ``keyword``: a literal word or phrase. ``whole_word`` (default) bounds it so ``crash`` does not
  hit ``crashes``; internal whitespace matches any whitespace run. Case-insensitive by default.
* ``regex``: compiled as written with the ``regex`` package (``re``-compatible syntax), capped at
  :data:`MAX_PATTERN_LENGTH` characters and searched with a per-call timeout so a catastrophic
  pattern authored in the UI cannot hang the collector. ``whole_word`` is not applied; the author
  controls boundaries.
* ``flair``: compared with the post's link flair; ``whole_word`` means exact (case-folded unless
  ``case_sensitive``), otherwise substring.
* ``subreddit``: exact match on the lowercase subreddit name (``r/`` prefixes tolerated). This is
  the kind the UI puts in the **Only in** group; the group semantics are general, so any kind
  works in any group.

Text rules search the fields the caller supplies (``title``, ``body``, ``comments``); ``scope``
``any`` searches all three in that order. A rule that times out counts as not matched and sets
``MatchResult.timed_out``; the other rules still decide the outcome.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Final, Literal, NamedTuple, Protocol, cast

import regex
from pydantic import BaseModel, ConfigDict, Field

from insightminer.core.models import PostRow

RuleKind = Literal["keyword", "regex", "flair", "subreddit"]
RuleGroup = Literal["match", "exclude", "only_in"]
RuleScope = Literal["title", "body", "comments", "any"]

#: Text fields a rule with ``scope="any"`` searches, in attribution order.
TEXT_SCOPES: Final[tuple[str, ...]] = ("title", "body", "comments")
MAX_PATTERN_LENGTH: Final = 300
MATCH_TIMEOUT_SECONDS: Final = 1.0
#: Folded into ``rules_hash`` so a semantic change to the matcher itself re-tags everything.
MATCHER_VERSION: Final = 1


class Rule(BaseModel):
    """One theme rule as stored in ``theme_rules`` (minus DB-only columns such as ``enabled``)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    kind: RuleKind
    pattern: str = Field(min_length=1)
    group: RuleGroup = "match"
    scope: RuleScope = "any"
    case_sensitive: bool = False
    whole_word: bool = True


class RuleError(ValueError):
    """A rule cannot be compiled. The message names the rule by index, kind and pattern."""

    def __init__(self, rule_index: int, rule: Rule, reason: str) -> None:
        super().__init__(f"rule {rule_index} ({rule.kind} {rule.pattern!r}): {reason}")
        self.rule_index = rule_index
        self.rule = rule
        self.reason = reason


class _Pattern(Protocol):
    """The slice of ``regex.Pattern`` we use (the package ships no type stubs)."""

    def search(self, string: str, *, timeout: float | None = None) -> object | None: ...


@dataclass(frozen=True, slots=True)
class _CompiledRule:
    index: int
    rule: Rule
    pattern: _Pattern | None  # keyword / regex
    literal: str | None  # flair / subreddit


@dataclass(frozen=True, slots=True)
class CompiledTheme:
    rules: tuple[Rule, ...]
    rules_hash: str
    timeout: float
    match_rules: tuple[_CompiledRule, ...]
    exclude_rules: tuple[_CompiledRule, ...]
    only_in_rules: tuple[_CompiledRule, ...]


@dataclass(frozen=True, slots=True)
class MatchResult:
    matched: bool
    rule_index: int | None  # index into ``CompiledTheme.rules`` of the first match rule that hit
    field: str | None  # "title" / "body" / "comments" / "flair" / "subreddit"
    timed_out: bool


class Candidate(NamedTuple):
    """One item to match: its text fields, lowercase subreddit and link flair."""

    text_fields: Mapping[str, str]
    subreddit: str
    flair: str | None

    @classmethod
    def from_post(cls, row: PostRow, comments: Iterable[str] = ()) -> Candidate:
        """Build from a normalized post; ``comments`` are bodies to search under ``comments``.

        Callers exclude ``author_is_bot`` rows *before* this by default (plan step 5).
        """
        fields = {
            "title": row.title or "",
            "body": row.selftext or "",
            "comments": "\n".join(comments),
        }
        return cls(fields, row.subreddit, row.link_flair_text)


# --- hashing ---------------------------------------------------------------------------------


def rules_hash(rules: Iterable[Rule]) -> str:
    """Order-independent SHA-256 over the rules' semantic attributes plus ``MATCHER_VERSION``."""
    serialized = sorted(
        json.dumps(rule.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        for rule in rules
    )
    digest = hashlib.sha256(f"matcher:{MATCHER_VERSION}\n".encode())
    for item in serialized:
        digest.update(item.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


# --- compilation -----------------------------------------------------------------------------


def _normalize_subreddit(name: str) -> str:
    name = name.strip().lower()
    name = name.removeprefix("/").removeprefix("r/")
    return name.strip("/")


def _compile_pattern(source: str, case_sensitive: bool) -> _Pattern:
    flags = 0 if case_sensitive else regex.IGNORECASE
    return cast("_Pattern", regex.compile(source, flags))


def _compile_rule(index: int, rule: Rule) -> _CompiledRule:
    if len(rule.pattern) > MAX_PATTERN_LENGTH:
        raise RuleError(
            index, rule, f"pattern is {len(rule.pattern)} chars; max {MAX_PATTERN_LENGTH}"
        )
    if rule.kind == "keyword":
        tokens = rule.pattern.split()
        if not tokens:
            raise RuleError(index, rule, "keyword is empty")
        body = r"\s+".join(regex.escape(token) for token in tokens)
        if rule.whole_word:
            body = rf"(?<!\w){body}(?!\w)"
        return _CompiledRule(index, rule, _compile_pattern(body, rule.case_sensitive), None)
    if rule.kind == "regex":
        try:
            pattern = _compile_pattern(rule.pattern, rule.case_sensitive)
        except regex.error as exc:
            raise RuleError(index, rule, f"invalid regex: {exc}") from exc
        return _CompiledRule(index, rule, pattern, None)
    if rule.kind == "subreddit":
        literal = _normalize_subreddit(rule.pattern)
        if not literal:
            raise RuleError(index, rule, "subreddit name is empty")
        return _CompiledRule(index, rule, None, literal)
    literal = rule.pattern.strip()
    if not literal:
        raise RuleError(index, rule, "flair is empty")
    return _CompiledRule(index, rule, None, literal if rule.case_sensitive else literal.casefold())


def compile_theme(
    rules: Sequence[Rule], *, timeout: float = MATCH_TIMEOUT_SECONDS
) -> CompiledTheme:
    """Compile every rule or raise :class:`RuleError` for the first bad one.

    ``timeout`` (seconds) bounds each regex search; the default is the production value.
    """
    compiled = [_compile_rule(index, rule) for index, rule in enumerate(rules)]
    return CompiledTheme(
        rules=tuple(rules),
        rules_hash=rules_hash(rules),
        timeout=timeout,
        match_rules=tuple(c for c in compiled if c.rule.group == "match"),
        exclude_rules=tuple(c for c in compiled if c.rule.group == "exclude"),
        only_in_rules=tuple(c for c in compiled if c.rule.group == "only_in"),
    )


# --- matching --------------------------------------------------------------------------------


def _hit(
    compiled: _CompiledRule,
    fields: Mapping[str, str],
    subreddit: str,
    flair: str | None,
    timeout: float,
) -> tuple[str | None, bool]:
    """Return ``(field_that_hit or None, timed_out)`` for one rule."""
    rule = compiled.rule
    if rule.kind == "subreddit":
        return ("subreddit" if _normalize_subreddit(subreddit) == compiled.literal else None, False)
    if rule.kind == "flair":
        if flair is None or compiled.literal is None:
            return None, False
        value = flair.strip() if rule.case_sensitive else flair.strip().casefold()
        hit = value == compiled.literal if rule.whole_word else compiled.literal in value
        return ("flair" if hit else None), False
    pattern = compiled.pattern
    assert pattern is not None  # keyword / regex always compile to a pattern
    scopes = TEXT_SCOPES if rule.scope == "any" else (rule.scope,)
    timed_out = False
    for scope in scopes:
        text = fields.get(scope)
        if text is None:
            continue
        try:
            if pattern.search(text, timeout=timeout) is not None:
                return scope, timed_out
        except TimeoutError:
            timed_out = True
    return None, timed_out


def match(
    theme: CompiledTheme,
    post_text_fields: Mapping[str, str],
    subreddit: str,
    flair: str | None,
) -> MatchResult:
    """Decide whether one item belongs to ``theme``.

    ``post_text_fields`` maps ``"title"`` / ``"body"`` / ``"comments"`` to text; unknown keys are
    ignored and missing keys are simply not searched. Evaluation short-circuits (only_in, then
    match, then exclude), so ``timed_out`` reflects the rules that actually ran.
    """
    timed_out = False

    def any_hit(group: tuple[_CompiledRule, ...]) -> tuple[int | None, str | None]:
        nonlocal timed_out
        for compiled in group:
            field, rule_timed_out = _hit(
                compiled, post_text_fields, subreddit, flair, theme.timeout
            )
            timed_out = timed_out or rule_timed_out
            if field is not None:
                return compiled.index, field
        return None, None

    if theme.only_in_rules and any_hit(theme.only_in_rules)[0] is None:
        return MatchResult(False, None, None, timed_out)
    index, field = any_hit(theme.match_rules)
    if index is None:
        return MatchResult(False, None, None, timed_out)
    if any_hit(theme.exclude_rules)[0] is not None:
        return MatchResult(False, None, None, timed_out)
    return MatchResult(True, index, field, timed_out)


def base_rate(theme: CompiledTheme, corpus_iter: Iterable[Candidate]) -> tuple[int, int]:
    """``(hits, total)`` over a corpus, for the "N of M posts" denominators in previews/digests."""
    hits = total = 0
    for candidate in corpus_iter:
        total += 1
        if match(theme, candidate.text_fields, candidate.subreddit, candidate.flair).matched:
            hits += 1
    return hits, total
