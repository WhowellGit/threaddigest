"""Tests for the digest model, the shared ranking function and the two renderers.

The golden file ``golden/digest_example.md`` is the rendering of :func:`example_model`;
the structural test proves on that rendered output (never on the model) that no number
appears without its denominator or population, and the evidence tests prove that a
failed subreddit and a changed setting reach the output from the model, not from the
template.
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jinja2 import UndefinedError
from pydantic import BaseModel, ValidationError

from threaddigest.core import digest
from threaddigest.core.digest import (
    STALE_AFTER_RUNS,
    Backlog,
    Compliance,
    Count,
    DigestModel,
    PostItem,
    Problem,
    RisingPhrase,
    RisingPhrasesSection,
    RunSummary,
    SettingChange,
    SubredditLine,
    SubredditStatus,
    ThemeSection,
    UnknownEnum,
    UnknownEnumSection,
    UntaggedSection,
    WorkspaceSection,
    rank_posts,
    render_html,
    render_markdown,
)
from threaddigest.core.retry import RunStatus

GOLDEN = Path(__file__).parent / "golden" / "digest_example.md"


def _utc(hour: int, minute: int, day: int = 13) -> int:
    return int(datetime(2026, 9, day, hour, minute, tzinfo=UTC).timestamp())


def _post(
    number: int,
    title: str,
    subreddit: str,
    authors: int,
    comments: int,
    score: int,
) -> PostItem:
    return PostItem(
        post_id=f"1abc{number}",
        title=title,
        permalink=f"https://www.reddit.com/r/{subreddit}/comments/1abc{number}/x/",
        subreddit=subreddit,
        distinct_author_count=authors,
        comment_count=comments,
        score=score,
        created_utc=_utc(1, 0) + number,
    )


EXPORT_HANGS = _post(1, "Export hangs at 99% after the 26.1 update", "premiere", 14, 31, 88)
CRASH_ON_LAUNCH = _post(2, "Crash on launch [M4 Max] *every* time", "premiere", 9, 40, 120)
PROXIES = _post(3, "Proxies out of sync | anyone else?", "editors", 9, 12, 30)
QUIET = _post(4, "Quiet question", "premiere", 1, 0, 2)

FORBIDDEN_SUB = "editors"
CHANGED_KEY = "budget.per_run_requests"


def example_model(
    *,
    subreddit_status: SubredditStatus = SubredditStatus.FORBIDDEN,
    settings_changes: list[SettingChange] | None = None,
) -> DigestModel:
    """The DG-01 seed: two subs ok, one failed, a gap, a backlog, unknown enums, a changed
    budget and a reconcile tier fallback."""
    changes = (
        [SettingChange(key=CHANGED_KEY, previous="1500", current="500")]
        if settings_changes is None
        else settings_changes
    )
    failed = subreddit_status is not SubredditStatus.OK
    top = rank_posts([PROXIES, EXPORT_HANGS, CRASH_ON_LAUNCH])
    return DigestModel(
        report_date=date(2026, 9, 13),
        generated_at=_utc(6, 41),
        summary=RunSummary(
            run_id=42,
            status=RunStatus.PARTIAL,
            trigger="schedule",
            started_at=_utc(6, 30),
            finished_at=_utc(6, 41),
            api_requests=Count(n=1312, of=1500, population="budgeted requests"),
            posts_new=Count(n=42, of=612, population="items seen"),
            posts_updated=Count(n=388, of=612, population="items seen"),
            comments_new=Count(n=917, of=2140, population="comments seen"),
            settings_fingerprint="9f2c" * 4,
            previous_settings_fingerprint="0a1b" * 4,
            settings_total=14,
            settings_changes=changes,
        ),
        workspaces=[
            WorkspaceSection(
                name="Premiere",
                slug="premiere",
                new_posts=Count(n=42, of=42, population="new posts this run"),
                top_posts=top,
                themes=[
                    ThemeSection(
                        name="Crashes",
                        slug="crashes",
                        matched=Count(n=12, of=60, population="new posts"),
                        top_posts=top[:2],
                    ),
                    ThemeSection(
                        name="Export",
                        slug="export",
                        matched=Count(n=0, of=60, population="new posts"),
                        top_posts=[],
                    ),
                ],
                untagged=UntaggedSection(
                    qualifying=Count(n=4, of=38, population="untagged posts in the last 7 days"),
                    posts=[PROXIES],
                ),
                rising_phrases=RisingPhrasesSection(
                    titles_now=120,
                    titles_baseline=480,
                    phrases=[("export hangs", 9, 3), ("26.1", 7, 0)],
                ),
            )
        ],
        subreddits=[
            SubredditLine(
                name="premiere",
                status=SubredditStatus.OK,
                pages=3,
                items_seen=250,
                new_posts=12,
                updated_posts=200,
                stop_reason="exhausted",
            ),
            SubredditLine(
                name=FORBIDDEN_SUB,
                status=subreddit_status,
                pages=0 if failed else 2,
                items_seen=0 if failed else 150,
                new_posts=0 if failed else 5,
                updated_posts=0 if failed else 100,
                stop_reason="error" if failed else "exhausted",
                last_error="403 Forbidden: subreddit is private" if failed else None,
                consecutive_failures=3 if failed else 0,
                runs_since_fetched=2 if failed else 0,
            ),
            SubredditLine(
                name="videoediting",
                status=SubredditStatus.OK,
                pages=10,
                items_seen=1000,
                new_posts=30,
                updated_posts=188,
                stop_reason="cap",
                gap_suspected_at=_utc(6, 35),
            ),
        ],
        backlog=Backlog(
            due_posts_harvested=Count(n=30, of=42, population="due posts"),
            trees_with_more_skipped=Count(n=3, of=30, population="trees fetched"),
        ),
        compliance=Compliance(
            last_reconcile_age_hours=26,
            reconcile_tier="items 30 days old or younger",
            tier_max_age_hours=60,
            reconciled=Count(n=1900, of=5000, population="stored items"),
            tier_fallback=True,
            scrubbed_posts=Count(n=4, of=1200, population="posts checked"),
            scrubbed_comments=Count(n=11, of=700, population="comments checked"),
            account_deletions=Count(n=2, of=300, population="authors seen"),
        ),
        errors=(
            [
                Problem(
                    where=f"sweep r/{FORBIDDEN_SUB}", message="403 Forbidden: subreddit is private"
                )
            ]
            if failed
            else []
        ),
        warnings=[
            Problem(where="reconcile", message="fell back to tiers: budget exhausted"),
            Problem(
                where="sweep r/videoediting", message="listing cap reached before known territory"
            ),
        ],
        unknown_enums=UnknownEnumSection(
            rows_written=412,
            values=[
                UnknownEnum(field="post_hint", value="new_thing", occurrences=2),
                UnknownEnum(field="removed_by_category", value="future_ops", occurrences=1),
            ],
        ),
    )


# ------------------------------------------------------------------- golden


def test_markdown_matches_the_golden_byte_for_byte() -> None:
    rendered = render_markdown(example_model()).encode("utf-8")
    assert rendered == GOLDEN.read_bytes(), (
        "digest markdown drifted from tests/unit/golden/digest_example.md; if the change is "
        "intended, regenerate the golden and review the diff"
    )


def test_rendering_is_deterministic() -> None:
    model = example_model()
    assert render_markdown(model) == render_markdown(example_model())
    assert render_html(model) == render_html(example_model())


# --------------------------------------------------------------- structural

# A digit run is justified only by one of these shapes. Anything else on a line is a bare
# count and fails the test, which is the point: a new metric must arrive as a Count.
_JUSTIFIED = [
    # "12 of 60 new posts" (the population noun must follow the denominator)
    r"\d[\d,]*\s+of\s+\d[\d,]*\s+[A-Za-z]",
    # units and populations the prose uses: "14 authors", "3 distinct authors", "11 min"
    r"\d[\d,]*\s+(distinct\s+)?authors?\b",
    r"\d[\d,]*\s+(comments?|errors?|warnings?|pages?|days?|weeks?|min|h|s)\b",
    r"\d[\d,]*\s+runs?(\s+ago)?\b",
    r"\d[\d,]*\s+consecutive\s+failures?\b",
    r"\(\d+%\)",
    # labelled scalars that are not counts of a population
    r"\bscore\s+-?\d[\d,]*",
    r"\bexit code\s+\d+",
    r"#\d+",
    # dates, times and zone stamps
    r"\d{4}-\d{2}-\d{2}( \d{2}:\d{2}( [A-Z]{1,5})?)?",
    # ordered-list markers
    r"^\s*\d+\.\s",
]
_JUSTIFIED_RE = [re.compile(pattern, re.MULTILINE) for pattern in _JUSTIFIED]
_CODE_SPAN = re.compile(r"`[^`]*`")
# Link text may contain backslash-escaped brackets (`\[M4 Max\]`).
_LINK = re.compile(r"\[(?:\\.|[^\]\\])*\]\([^)]*\)")
# Rising title phrases are quoted content, like titles.
_QUOTED = re.compile(r'"[^"]*"')
_DIGITS = re.compile(r"-?\d[\d,]*(\.\d+)?")


def _unjustified_numbers(markdown: str) -> list[tuple[str, str]]:
    offenders: list[tuple[str, str]] = []
    for raw_line in markdown.splitlines():
        # Content, not metrics: code spans (settings values, error text, fingerprints),
        # link text plus URL (post titles, permalinks) and quoted phrases.
        line = _QUOTED.sub("", _LINK.sub("", _CODE_SPAN.sub("", raw_line)))
        justified: list[tuple[int, int]] = []
        for pattern in _JUSTIFIED_RE:
            justified.extend(match.span() for match in pattern.finditer(line))
        for number in _DIGITS.finditer(line):
            start, end = number.span()
            if not any(js <= start and end <= je for js, je in justified):
                offenders.append((number.group(), raw_line))
    return offenders


def test_every_number_in_the_markdown_carries_its_denominator_or_population() -> None:
    markdown = render_markdown(example_model())
    assert _unjustified_numbers(markdown) == []


def test_structural_check_catches_a_bare_count() -> None:
    # Positive control for the structural test: a bare number is reported.
    assert _unjustified_numbers("- New posts: 12\n") == [("12", "- New posts: 12")]
    assert _unjustified_numbers("- New posts: 12 of 60\n") == [
        ("12", "- New posts: 12 of 60"),
        ("60", "- New posts: 12 of 60"),
    ]
    assert _unjustified_numbers("- New posts: 12 of 60 new posts (20%)\n") == []


def _counts(value: object) -> list[Count]:
    if isinstance(value, Count):
        return [value]
    if isinstance(value, BaseModel):
        found: list[Count] = []
        for name in type(value).model_fields:
            found.extend(_counts(getattr(value, name)))
        return found
    if isinstance(value, list):
        return [count for item in value for count in _counts(item)]
    return []


def test_every_count_in_the_model_is_rendered_in_both_formats() -> None:
    model = example_model()
    counts = _counts(model)
    assert len(counts) >= 14
    markdown = render_markdown(model)
    html = render_html(model)
    for count in counts:
        assert str(count) in markdown, count
        assert str(count) in html, count


def test_derived_counts_are_rendered() -> None:
    model = example_model()
    markdown = render_markdown(model)
    assert str(model.healthy_subreddits) == "2 of 3 subreddits (67%)"
    assert "2 of 3 subreddits swept without error (67%)" in markdown
    assert str(model.gap_count) == "1 of 3 subreddits (33%)"
    assert "## Gaps: 1 of 3 subreddits (33%)" in markdown
    assert str(model.stale_subreddits) == "1 of 3 subreddits (33%)"
    assert str(model.backlog.remaining_due) == "12 of 42 due posts (29%)"
    assert str(model.unknown_enums.count) == "3 of 412 rows written (1%)"
    assert str(model.summary.settings_changed) == "1 of 14 non-secret settings (7%)"


# ------------------------------------------------------------------ evidence


def test_failed_subreddit_and_changed_setting_come_from_the_model() -> None:
    markdown = render_markdown(example_model())
    html = render_html(example_model())
    for output in (markdown, html):
        assert f"r/{FORBIDDEN_SUB}" in output
        assert "forbidden" in output
        assert "403 Forbidden: subreddit is private" in output
        assert "3 consecutive failures" in output
        assert "last fetched 2 runs ago (stale)" in output
        assert CHANGED_KEY in output
        assert "1500" in output
        assert "500" in output
    assert f"- r/{FORBIDDEN_SUB}: **forbidden**" in markdown
    assert '<span class="bad">forbidden</span>' in html
    assert f"`{CHANGED_KEY}`: `1500` → `500`" in markdown


def test_healthy_control_shows_neither_failure_nor_change() -> None:
    control = example_model(subreddit_status=SubredditStatus.OK, settings_changes=[])
    for output in (render_markdown(control), render_html(control)):
        assert "forbidden" not in output
        assert CHANGED_KEY not in output
        assert "consecutive failure" not in output
        assert "stale)" not in output
        assert "0 of 14 non-secret settings (0%)" in output
        assert "3 of 3 subreddits swept without error (100%)" in output
        assert "0 errors, 2 warnings this run" in output


def test_first_run_says_there_is_nothing_to_compare_with() -> None:
    model = example_model(settings_changes=[])
    first_run = model.model_copy(
        update={"summary": model.summary.model_copy(update={"previous_settings_fingerprint": None})}
    )
    markdown = render_markdown(first_run)
    assert "first run, nothing to compare with" in markdown
    assert "Settings changed since last run" not in markdown
    assert f"`{'9f2c' * 4}`" in markdown


def test_status_and_exit_code_are_derived_from_the_run_status() -> None:
    model = example_model()
    assert "**partial**, exit code 3" in render_markdown(model)
    failed = model.model_copy(
        update={"summary": model.summary.model_copy(update={"status": RunStatus.FAILED})}
    )
    assert "**failed**, exit code 1" in render_markdown(failed)


def test_gap_and_tier_fallback_are_reported() -> None:
    markdown = render_markdown(example_model())
    assert "listing cap reached before known territory at 2026-09-13 06:35 UTC" in markdown
    assert "fell back to tiers because the budget could not cover a full sweep" in markdown
    assert "- `post_hint` = `new_thing`: 2 of 412 rows written (0%)" in markdown


# ------------------------------------------------------------------- ranking


def test_rank_posts_key_is_distinct_authors_then_comments_then_score() -> None:
    a = _post(1, "a", "s", 5, 1, 1000)
    b = _post(2, "b", "s", 4, 99, 1)
    c = _post(3, "c", "s", 4, 50, 500)
    d = _post(4, "d", "s", 4, 50, 400)
    assert rank_posts([d, c, b, a]) == [a, b, c, d]


def test_rank_posts_breaks_full_ties_by_post_id_deterministically() -> None:
    """C-8 (external round one): a stable sort left full ties in input order, so the visible
    order followed whatever order the database returned. The order is now fixed by ``post_id``,
    the same whichever way the input arrives."""
    first = _post(1, "first", "s", 3, 3, 3)  # post_id 1abc1
    second = _post(2, "second", "s", 3, 3, 3)  # post_id 1abc2
    assert rank_posts([first, second]) == [first, second]
    assert rank_posts([second, first]) == [first, second]  # input order no longer decides


def test_rank_posts_accepts_any_rankable_and_returns_a_new_list() -> None:
    class Row:
        def __init__(self, authors: int, comments: int, score: int, post_id: str) -> None:
            self.distinct_author_count = authors
            self.comment_count = comments
            self.score = score
            self.post_id = post_id

    rows = [Row(1, 1, 1, "b"), Row(2, 0, 0, "a")]
    ranked = rank_posts(rows)
    assert ranked == [rows[1], rows[0]]
    assert ranked is not rows
    assert rank_posts(iter(rows)) == ranked
    assert rank_posts([]) == []


def test_never_ranks_by_raw_recency_or_post_count() -> None:
    older_but_discussed = _post(1, "old", "s", 6, 2, 0)
    newer_and_quiet = _post(2, "new", "s", 1, 0, 300)
    assert rank_posts([newer_and_quiet, older_but_discussed])[0] is older_but_discussed


# -------------------------------------------------------------------- Count


@pytest.mark.parametrize(
    ("n", "of", "expected"),
    [(12, 60, 20), (1, 8, 13), (1, 3, 33), (2, 3, 67), (0, 5, 0), (5, 5, 100), (7, 5, 140)],
)
def test_count_percent_rounds_half_up(n: int, of: int, expected: int) -> None:
    assert Count(n=n, of=of, population="things").pct == expected


def test_count_renders_with_population_and_thousands_separators() -> None:
    count = Count(n=1312, of=1500, population="budgeted requests")
    assert count.text == "1,312 of 1,500 budgeted requests"
    assert str(count) == "1,312 of 1,500 budgeted requests (87%)"


def test_count_with_empty_population_has_no_percentage() -> None:
    count = Count(n=0, of=0, population="items seen")
    assert count.pct is None
    assert str(count) == "0 of 0 items seen"


@pytest.mark.parametrize("kwargs", [{"n": -1, "of": 5}, {"n": 1, "of": -5}])
def test_count_rejects_negatives(kwargs: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        Count(population="x", **kwargs)


def test_count_requires_a_population() -> None:
    with pytest.raises(ValidationError):
        Count(n=1, of=2, population="")


# ---------------------------------------------------------------- sections


def test_untagged_section_rejects_posts_below_the_threshold() -> None:
    with pytest.raises(ValidationError, match="below the section's threshold"):
        UntaggedSection(qualifying=Count(n=1, of=5, population="untagged posts"), posts=[QUIET])


def test_untagged_section_rejects_more_posts_than_qualify() -> None:
    with pytest.raises(ValidationError, match="only 0 qualify"):
        UntaggedSection(qualifying=Count(n=0, of=5, population="untagged posts"), posts=[PROXIES])


def test_rising_phrases_accept_tuples_and_render_both_denominators() -> None:
    section = RisingPhrasesSection(titles_now=120, titles_baseline=480, phrases=[("x y", 9, 3)])
    assert section.phrases == [RisingPhrase(phrase="x y", count_now=9, count_baseline=3)]
    assert str(section.now(section.phrases[0])) == "9 of 120 titles in the last 7 days (8%)"
    assert str(section.baseline(section.phrases[0])) == (
        "3 of 480 titles in the trailing 4 weeks (1%)"
    )


def test_subreddit_line_facts() -> None:
    ok = SubredditLine(
        name="premiere",
        status=SubredditStatus.OK,
        pages=3,
        items_seen=250,
        new_posts=12,
        updated_posts=200,
        stop_reason="exhausted",
    )
    assert ok.healthy is True
    assert ok.stale is False
    assert ok.facts == [
        "3 pages",
        "new 12 of 250 items seen (5%)",
        "updated 200 of 250 items seen (80%)",
        "stop: exhausted",
        "fetched this run",
    ]
    failed = SubredditLine(
        name="editors",
        status=SubredditStatus.ERROR,
        stop_reason="error",
        consecutive_failures=1,
        runs_since_fetched=1,
        enabled=False,
        gap_suspected_at=1,
    )
    assert failed.healthy is False
    assert failed.stale is False
    assert failed.facts == [
        "disabled",
        "stop: error",
        "last fetched 1 run ago",
        "1 consecutive failure",
        "gap suspected",
    ]


def test_ok_status_with_an_error_stop_is_not_healthy() -> None:
    line = SubredditLine(name="x", status=SubredditStatus.OK, stop_reason="error")
    assert line.healthy is False


def test_stale_after_two_runs_without_a_fetch() -> None:
    assert STALE_AFTER_RUNS == 2
    assert SubredditLine(name="x", status=SubredditStatus.OK, runs_since_fetched=1).stale is False
    assert SubredditLine(name="x", status=SubredditStatus.OK, runs_since_fetched=2).stale is True


def test_backlog_remaining_never_negative() -> None:
    backlog = Backlog(
        due_posts_harvested=Count(n=50, of=42, population="due posts"),
        trees_with_more_skipped=Count(n=0, of=50, population="trees fetched"),
    )
    assert str(backlog.remaining_due) == "0 of 42 due posts (0%)"


def _compliance(age: float | None) -> Compliance:
    zero = Count(n=0, of=0, population="x")
    return Compliance(
        last_reconcile_age_hours=age,
        reconcile_tier="items 30 days old or younger",
        tier_max_age_hours=60,
        reconciled=zero,
        tier_fallback=False,
        scrubbed_posts=zero,
        scrubbed_comments=zero,
        account_deletions=zero,
    )


@pytest.mark.parametrize(
    ("age", "overdue"), [(None, True), (60, False), (60.5, True), (26, False), (0, False)]
)
def test_compliance_overdue(age: float | None, overdue: bool) -> None:
    assert _compliance(age).overdue is overdue


def test_compliance_rendering_says_overdue_or_never() -> None:
    model = example_model()
    never = model.model_copy(update={"compliance": _compliance(None)})
    markdown = render_markdown(never)
    assert "Last complete reconcile: never ago" in markdown
    assert "; overdue" in markdown
    late = model.model_copy(update={"compliance": _compliance(61.5)})
    assert "Last complete reconcile: 61.5 h ago" in render_markdown(late)


def test_unknown_enum_count_sums_occurrences() -> None:
    section = UnknownEnumSection(
        rows_written=10,
        values=[
            UnknownEnum(field="a", value="x", occurrences=2),
            UnknownEnum(field="b", value="", occurrences=3),
        ],
    )
    assert str(section.count) == "5 of 10 rows written (50%)"
    assert str(section.share(section.values[1])) == "3 of 10 rows written (30%)"


# ------------------------------------------------------------- run summary


def _summary(**overrides: object) -> RunSummary:
    base = example_model().summary.model_dump()
    base.update(overrides)
    return RunSummary.model_validate(base)


def test_run_summary_rejects_finish_before_start() -> None:
    with pytest.raises(ValidationError, match="before started_at"):
        _summary(finished_at=_utc(6, 29))


def test_run_summary_rejects_changes_without_a_previous_fingerprint() -> None:
    with pytest.raises(ValidationError, match="previous fingerprint"):
        _summary(previous_settings_fingerprint=None)


def test_run_summary_rejects_more_changes_than_settings() -> None:
    with pytest.raises(ValidationError, match="exceed"):
        _summary(
            settings_total=1, settings_changes=[{"key": "a", "previous": "1", "current": "2"}] * 2
        )


def test_run_summary_duration_and_exit_code() -> None:
    summary = example_model().summary
    assert summary.duration_seconds == 660
    assert summary.exit_code == 3


# -------------------------------------------------------------- rendering


def test_display_timezone_is_validated_and_applied() -> None:
    dumped = example_model().model_dump()
    with pytest.raises(ValidationError, match="unknown display_timezone"):
        DigestModel.model_validate({**dumped, "display_timezone": "Mars/Olympus"})
    local = DigestModel.model_validate({**dumped, "display_timezone": "America/Los_Angeles"})
    markdown = render_markdown(local)
    assert "Started 2026-09-12 23:30 PDT, finished 2026-09-12 23:41 PDT (11 min)" in markdown


def test_templates_are_strict_about_undefined_names() -> None:
    env = digest._environment(autoescape=False)
    with pytest.raises(UndefinedError):
        env.from_string("{{ m.no_such_field }}").render(m=example_model())
    with pytest.raises(UndefinedError):
        env.from_string("{{ missing }}").render()


def test_markdown_escapes_title_markup_and_html_escapes_tags() -> None:
    hostile = _post(9, "<script>alert(1)</script> *bold* [x] a|b", "premiere", 5, 5, 5)
    model = example_model()
    workspace = model.workspaces[0].model_copy(update={"top_posts": [hostile]})
    model = model.model_copy(update={"workspaces": [workspace]})
    markdown = render_markdown(model)
    assert "[\\<script\\>alert(1)\\</script\\> \\*bold\\* \\[x\\] a\\|b](" in markdown
    html = render_html(model)
    assert "<script>" not in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt; *bold* [x] a|b" in html


def test_html_is_a_complete_document_with_deep_links() -> None:
    html = render_html(example_model())
    assert html.startswith("<!doctype html>")
    assert html.rstrip().endswith("</html>")
    assert '<a href="https://www.reddit.com/r/premiere/comments/1abc1/x/">' in html
    assert "<h2>Workspace: Premiere</h2>" in html
    assert "<h3>Theme Crashes: 12 of 60 new posts (20%)</h3>" in html


def test_markdown_lists_posts_in_ranked_order_with_deep_links() -> None:
    markdown = render_markdown(example_model())
    top = markdown.index("### Top posts")
    section = markdown[top : markdown.index("### Theme Crashes")]
    lines = [line for line in section.splitlines() if re.match(r"^\d+\. ", line)]
    assert len(lines) == 3
    assert lines[0].startswith("1. [Export hangs at 99% after the 26.1 update](https://")
    assert "14 authors · 31 comments · score 88" in lines[0]
    assert lines[1].startswith("2. [Crash on launch")
    assert lines[2].startswith("3. [Proxies out of sync")


def test_empty_sections_say_so_instead_of_vanishing() -> None:
    model = example_model(subreddit_status=SubredditStatus.OK)
    workspace = model.workspaces[0]
    empty_workspace = workspace.model_copy(
        update={
            "top_posts": [],
            "untagged": workspace.untagged.model_copy(
                update={"posts": [], "qualifying": Count(n=0, of=38, population="untagged posts")}
            ),
            "rising_phrases": workspace.rising_phrases.model_copy(update={"phrases": []}),
        }
    )
    subs = [sub.model_copy(update={"gap_suspected_at": None}) for sub in model.subreddits]
    model = model.model_copy(
        update={
            "workspaces": [empty_workspace],
            "subreddits": subs,
            "warnings": [],
            "unknown_enums": UnknownEnumSection(rows_written=412, values=[]),
        }
    )
    markdown = render_markdown(model)
    assert "_No new posts._" in markdown
    assert "_No untagged post reached the threshold._" in markdown
    assert "_No phrase is rising._" in markdown
    assert "_No gap suspected._" in markdown
    assert "## Errors: 0 errors this run" in markdown
    assert "## Unknown enum values: 0 of 412 rows written (0%)" in markdown
    assert _unjustified_numbers(markdown) == []


def test_post_items_carry_titles_and_links_only() -> None:
    # Compliance: a report can hold nothing of a later-deleted item beyond its title.
    fields = set(PostItem.model_fields)
    assert not fields & {"selftext", "body", "selftext_html", "author", "author_fullname"}
    with pytest.raises(ValidationError):
        PostItem.model_validate({**EXPORT_HANGS.model_dump(), "selftext": "body text"})


def test_models_are_frozen_and_forbid_extras() -> None:
    with pytest.raises(ValidationError):
        Count(n=1, of=2, population="x", extra="no")
    count = Count(n=1, of=2, population="x")
    with pytest.raises(ValidationError):
        count.n = 5


# ---------------------------------------------------------------- hypothesis

post_items = st.builds(
    PostItem,
    post_id=st.text(min_size=1, max_size=6),
    title=st.text(max_size=20),
    permalink=st.just("https://www.reddit.com/x"),
    subreddit=st.just("s"),
    distinct_author_count=st.integers(min_value=0, max_value=50),
    comment_count=st.integers(min_value=0, max_value=500),
    score=st.integers(min_value=-1000, max_value=10_000),
    created_utc=st.integers(min_value=0, max_value=2_000_000_000),
)


@settings(max_examples=200)
@given(st.lists(post_items, max_size=25))
def test_rank_posts_is_a_stable_permutation_sorted_by_the_key(items: list[PostItem]) -> None:
    ranked = rank_posts(items)
    assert sorted(map(id, ranked)) == sorted(map(id, items))
    # Equal models compare equal, so track input positions by identity, not by value.
    position = {id(item): index for index, item in enumerate(items)}
    for earlier, later in zip(ranked, ranked[1:], strict=False):
        key_a = (
            -earlier.distinct_author_count,
            -earlier.comment_count,
            -earlier.score,
            earlier.post_id,
        )
        key_b = (-later.distinct_author_count, -later.comment_count, -later.score, later.post_id)
        assert key_a <= key_b
        if key_a == key_b:  # identical values AND post_id: only then does input order decide
            assert position[id(earlier)] < position[id(later)]


@settings(max_examples=200)
@given(st.integers(min_value=0, max_value=10_000), st.integers(min_value=0, max_value=10_000))
def test_count_percent_is_bounded_and_text_has_both_numbers(n: int, of: int) -> None:
    count = Count(n=n, of=of, population="things")
    text = str(count)
    assert text.startswith(f"{n:,} of {of:,} things")
    if of == 0:
        assert count.pct is None
        assert "%" not in text
    else:
        assert count.pct is not None
        assert 0 <= count.pct
        assert abs(count.pct - 100 * n / of) <= 0.5
        assert text.endswith(f"({count.pct}%)")
