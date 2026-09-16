"""Tests for ``threaddigest.core.themes``: rule compilation and matching with regex timeouts."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from threaddigest.core.models import PostRow
from threaddigest.core.normalize import normalize_post
from threaddigest.core.themes import (
    MATCH_TIMEOUT_SECONDS,
    MAX_PATTERN_LENGTH,
    Candidate,
    CompiledTheme,
    MatchResult,
    Rule,
    RuleError,
    base_rate,
    compile_theme,
    match,
    rules_hash,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures" / "json" / "synthetic"


def kw(pattern: str, **overrides: Any) -> Rule:
    return Rule(kind="keyword", pattern=pattern, **overrides)


def rx(pattern: str, **overrides: Any) -> Rule:
    return Rule(kind="regex", pattern=pattern, **overrides)


def theme(*rules: Rule, timeout: float = MATCH_TIMEOUT_SECONDS) -> CompiledTheme:
    return compile_theme(list(rules), timeout=timeout)


def run(
    compiled: CompiledTheme,
    *,
    title: str = "",
    body: str = "",
    comments: str | None = None,
    subreddit: str = "premiere",
    flair: str | None = None,
) -> MatchResult:
    fields = {"title": title, "body": body}
    if comments is not None:
        fields["comments"] = comments
    return match(compiled, fields, subreddit, flair)


# --- Rule model --------------------------------------------------------------------------


def test_rule_defaults_are_match_any_case_insensitive_whole_word() -> None:
    rule = kw("crash")
    assert (rule.group, rule.scope, rule.case_sensitive, rule.whole_word) == (
        "match",
        "any",
        False,
        True,
    )


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "glob", "pattern": "x"},
        {"kind": "keyword", "pattern": "x", "group": "maybe"},
        {"kind": "keyword", "pattern": "x", "scope": "author"},
        {"kind": "keyword", "pattern": ""},
        {"kind": "keyword", "pattern": "x", "enabled": True},  # DB-only column, strip before use
    ],
)
def test_rule_rejects_unknown_kinds_groups_scopes_and_extras(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        Rule(**bad)


def test_rule_is_frozen() -> None:
    with pytest.raises(ValidationError):
        kw("x").pattern = "y"  # type: ignore[misc]


# --- keywords ----------------------------------------------------------------------------


def test_whole_word_keyword_does_not_match_inside_a_longer_word() -> None:
    t = theme(kw("crash"))
    assert run(t, title="Premiere crash on export").matched
    assert not run(t, title="Premiere crashes on export").matched
    assert not run(t, title="autocrash").matched


def test_substring_keyword_matches_inside_a_longer_word() -> None:
    t = theme(kw("crash", whole_word=False))
    assert run(t, title="Premiere crashes on export").matched
    assert run(t, title="autocrash").matched


def test_keyword_is_case_insensitive_by_default_and_exact_when_asked() -> None:
    assert run(theme(kw("crash")), title="CRASH on export").matched
    assert not run(theme(kw("crash", case_sensitive=True)), title="CRASH on export").matched
    assert run(theme(kw("crash", case_sensitive=True)), title="a crash").matched


def test_multi_word_keyword_is_a_phrase_tolerant_of_whitespace_runs() -> None:
    t = theme(kw("export failed"))
    assert run(t, title="The export failed twice").matched
    assert run(t, title="the export  failed").matched
    assert run(t, body="export\nfailed again").matched
    assert not run(t, title="export never failed").matched
    assert not run(t, title="exports failed").matched


def test_whole_word_keyword_with_punctuation_edges_still_matches() -> None:
    """A naive ``\\b`` implementation would miss ``C++`` followed by a space."""
    t = theme(kw("c++"))
    assert run(t, title="I love C++ so much").matched
    assert run(t, title="C++!").matched
    assert not run(t, title="xc++y").matched


def test_keyword_of_only_whitespace_is_a_rule_error() -> None:
    with pytest.raises(RuleError):
        theme(kw("   "))


# --- groups: exclude / only_in -----------------------------------------------------------


def test_exclude_rule_vetoes_a_match() -> None:
    t = theme(kw("crash"), kw("after effects", group="exclude"))
    assert run(t, title="Premiere crash").matched
    assert not run(t, title="Premiere crash", body="happens in After Effects too").matched


def test_exclude_alone_never_matches() -> None:
    t = theme(kw("after effects", group="exclude"))
    assert not run(t, title="anything").matched


def test_only_in_restricts_to_listed_subreddits_case_insensitively() -> None:
    t = theme(kw("crash"), Rule(kind="subreddit", pattern="premiere", group="only_in"))
    assert run(t, title="crash", subreddit="premiere").matched
    assert run(t, title="crash", subreddit="Premiere").matched
    assert not run(t, title="crash", subreddit="videoediting").matched


def test_only_in_accepts_r_slash_prefixes_and_several_subreddits() -> None:
    t = theme(
        kw("crash"),
        Rule(kind="subreddit", pattern="r/Premiere", group="only_in"),
        Rule(kind="subreddit", pattern="/r/editors/", group="only_in"),
    )
    assert run(t, title="crash", subreddit="premiere").matched
    assert run(t, title="crash", subreddit="editors").matched
    assert not run(t, title="crash", subreddit="videoediting").matched


def test_only_in_generalizes_to_a_required_any_group() -> None:
    t = theme(kw("crash"), Rule(kind="flair", pattern="Bug", group="only_in"))
    assert run(t, title="crash", flair="bug").matched
    assert not run(t, title="crash", flair="Help").matched
    assert not run(t, title="crash", flair=None).matched


def test_subreddit_rule_in_match_group_matches_the_subreddit() -> None:
    t = theme(Rule(kind="subreddit", pattern="premiere"))
    assert run(t, subreddit="premiere").matched
    assert not run(t, subreddit="editors").matched


# --- flair --------------------------------------------------------------------------------


def test_flair_rule_is_exact_or_substring_by_whole_word() -> None:
    exact = theme(Rule(kind="flair", pattern="Bug"))
    assert run(exact, flair="bug").matched
    assert not run(exact, flair="Bug report").matched
    assert not run(exact, flair=None).matched
    loose = theme(Rule(kind="flair", pattern="Bug", whole_word=False))
    assert run(loose, flair="Bug report").matched
    strict = theme(Rule(kind="flair", pattern="Bug", case_sensitive=True))
    assert not run(strict, flair="bug").matched


# --- scope / attribution -----------------------------------------------------------------


def test_scope_limits_which_field_is_searched() -> None:
    assert not run(theme(kw("crash", scope="title")), body="crash").matched
    assert run(theme(kw("crash", scope="body")), body="crash").matched
    assert not run(theme(kw("crash", scope="comments")), body="crash").matched
    assert run(theme(kw("crash", scope="comments")), comments="crash").matched
    assert run(theme(kw("crash")), comments="crash").matched


def test_match_result_reports_first_matching_rule_and_field() -> None:
    t = theme(kw("stutter"), kw("crash"), kw("export"))
    result = run(t, title="export crash", body="stutter")
    assert result == MatchResult(matched=True, rule_index=0, field="body", timed_out=False)
    result = run(t, title="export crash")
    assert (result.rule_index, result.field) == (1, "title")


def test_non_match_has_no_rule_attribution() -> None:
    result = run(theme(kw("crash")), title="fine")
    assert result == MatchResult(matched=False, rule_index=None, field=None, timed_out=False)


def test_excluded_match_has_no_rule_attribution() -> None:
    result = run(theme(kw("crash"), kw("crash", group="exclude")), title="crash")
    assert result == MatchResult(matched=False, rule_index=None, field=None, timed_out=False)


def test_unknown_fields_are_ignored_and_missing_fields_tolerated() -> None:
    t = theme(kw("crash"))
    assert not match(t, {"author": "crash"}, "premiere", None).matched
    assert not match(t, {}, "premiere", None).matched


def test_empty_theme_never_matches() -> None:
    assert not run(theme(), title="anything").matched


# --- regex --------------------------------------------------------------------------------


def test_regex_rule_matches_and_is_case_insensitive_by_default() -> None:
    t = theme(rx(r"error\s+\d{3,}"))
    result = run(t, body="Export stopped with ERROR 1609")
    assert result.matched and result.field == "body"
    assert not run(theme(rx(r"error", case_sensitive=True)), body="ERROR").matched


def test_regex_rule_leaves_word_boundaries_to_the_author() -> None:
    assert run(theme(rx("crash")), title="crashes").matched


def test_invalid_regex_raises_rule_error_naming_the_rule() -> None:
    with pytest.raises(RuleError) as info:
        theme(kw("ok"), rx("(unclosed"))
    assert info.value.rule_index == 1
    assert "(unclosed" in str(info.value)
    assert "regex" in str(info.value)


def test_over_long_pattern_raises_rule_error() -> None:
    assert MAX_PATTERN_LENGTH == 300
    theme(rx("a" * MAX_PATTERN_LENGTH))
    with pytest.raises(RuleError) as info:
        theme(rx("a" * (MAX_PATTERN_LENGTH + 1)))
    assert "300" in str(info.value)
    with pytest.raises(RuleError):
        theme(kw("a" * (MAX_PATTERN_LENGTH + 1)))


def test_catastrophic_regex_times_out_within_about_a_second() -> None:
    assert MATCH_TIMEOUT_SECONDS == 1.0
    t = theme(rx(r"(a+)+$"))
    started = time.perf_counter()
    result = run(t, body="a" * 30_000 + "!")
    elapsed = time.perf_counter() - started
    assert result.timed_out is True
    assert result.matched is False
    assert 0.5 < elapsed < 3.0, elapsed


def test_timeout_is_configurable_per_compiled_theme() -> None:
    t = theme(rx(r"(a+)+$"), timeout=0.1)
    started = time.perf_counter()
    result = run(t, body="a" * 30_000 + "!")
    assert result.timed_out and time.perf_counter() - started < 1.0


def test_timeout_in_one_rule_does_not_poison_the_others() -> None:
    t = theme(rx(r"(a+)+$"), kw("hello"), timeout=0.1)
    result = run(t, body="a" * 30_000 + "! hello")
    assert result == MatchResult(matched=True, rule_index=1, field="body", timed_out=True)


def test_timed_out_exclude_rule_does_not_veto() -> None:
    t = theme(kw("hello"), rx(r"(a+)+$", group="exclude"), timeout=0.1)
    result = run(t, body="a" * 30_000 + "! hello")
    assert result.matched and result.timed_out


# --- rules_hash --------------------------------------------------------------------------

GOLDEN_RULES = [kw("crash"), rx(r"error\s+\d+", scope="body"), kw("after effects", group="exclude")]
GOLDEN_HASH = "3bc059d4a067de3c2bc5d6869ae36c37a55e3cc82ff1353e08a9085d5dbc4796"


def test_rules_hash_is_a_stable_sha256_hex_digest() -> None:
    digest = rules_hash(GOLDEN_RULES)
    assert len(digest) == 64 and int(digest, 16) >= 0
    assert digest == rules_hash(list(GOLDEN_RULES))
    assert digest == GOLDEN_HASH  # pinned: a change here means every theme must re-tag


def test_rules_hash_ignores_rule_order() -> None:
    assert rules_hash(GOLDEN_RULES) == rules_hash(list(reversed(GOLDEN_RULES)))


@pytest.mark.parametrize(
    "changed",
    [
        [kw("crashes"), *GOLDEN_RULES[1:]],
        [kw("crash", case_sensitive=True), *GOLDEN_RULES[1:]],
        [kw("crash", whole_word=False), *GOLDEN_RULES[1:]],
        [kw("crash", scope="title"), *GOLDEN_RULES[1:]],
        [kw("crash", group="exclude"), *GOLDEN_RULES[1:]],
        [Rule(kind="regex", pattern="crash"), *GOLDEN_RULES[1:]],
        GOLDEN_RULES[:2],
    ],
)
def test_rules_hash_changes_when_any_semantic_attribute_changes(changed: list[Rule]) -> None:
    assert rules_hash(changed) != rules_hash(GOLDEN_RULES)


def test_rules_hash_of_no_rules_is_still_a_digest() -> None:
    assert len(rules_hash([])) == 64


def test_compiled_theme_carries_its_hash_and_rules() -> None:
    t = theme(*GOLDEN_RULES)
    assert t.rules_hash == rules_hash(GOLDEN_RULES)
    assert t.rules == tuple(GOLDEN_RULES)


# --- base_rate / Candidate ---------------------------------------------------------------


def test_base_rate_returns_hits_and_total() -> None:
    t = theme(kw("crash"))
    corpus = [
        Candidate({"title": "crash on export"}, "premiere", None),
        Candidate({"title": "fine"}, "premiere", None),
        Candidate({"title": "another CRASH"}, "editors", "Bug"),
        Candidate({"body": "crashes"}, "premiere", None),
        Candidate({}, "premiere", None),
    ]
    assert base_rate(t, corpus) == (2, 5)
    assert base_rate(t, iter(corpus)) == (2, 5)


def test_base_rate_of_an_empty_corpus_is_zero_over_zero() -> None:
    assert base_rate(theme(kw("crash")), []) == (0, 0)


def load_post(name: str) -> PostRow:
    with (FIXTURES / name).open(encoding="utf-8") as fh:
        row = normalize_post(json.load(fh), source="test")
    assert isinstance(row, PostRow)
    return row


def test_candidate_from_post_uses_title_selftext_flair_and_subreddit() -> None:
    row = load_post("post_self.json")
    cand = Candidate.from_post(row, comments=["first reply", "second reply"])
    assert cand.subreddit == "videoediting"
    assert cand.flair == "Help"
    assert cand.text_fields["title"] == row.title
    assert cand.text_fields["body"] == row.selftext
    assert cand.text_fields["comments"] == "first reply\nsecond reply"
    assert base_rate(theme(kw("stutters")), [cand]) == (1, 1)
    assert base_rate(theme(kw("reply", scope="comments")), [cand]) == (1, 1)


def test_candidate_from_post_turns_missing_text_into_empty_strings() -> None:
    row = load_post("post_deleted_link.json")
    cand = Candidate.from_post(row)
    assert cand.text_fields == {"title": row.title, "body": "", "comments": ""}
    assert cand.flair is None
