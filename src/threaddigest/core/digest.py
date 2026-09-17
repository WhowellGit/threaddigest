"""Digest: the model of one run's report and its markdown and HTML renderings.

Pure: no I/O, no clock, no database. Services assemble a :class:`DigestModel` from the
run row, ``run_subreddits``, the theme tables and the reconcile counters; the web route
``/reports/{date}``, ``threaddigest report`` and the export all render that one model
through :func:`render_markdown` and :func:`render_html`, so a number can never disagree
between surfaces.

Two rules from docs/PLAN.md shape every field:

* **Show the denominator.** Every count is a :class:`Count` (``n`` of ``of`` *population*),
  so a template has nothing bare to print; the structural test in
  ``tests/unit/test_digest.py`` proves it on the rendered output, not on the model.
* **Rank by distinct authors, then comment count, then score** (DECISIONS.md D-09):
  :func:`rank_posts` is the one ranking function shared by the digest, the theme pages and
  the export.

The digest is computed from the database on demand and carries titles and links only,
never bodies, so a persisted copy can hold nothing of a later-deleted item beyond its
title. Both templates use ``StrictUndefined``: a field the template names but the model
lacks fails the render instead of printing an empty string.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from datetime import UTC, date, datetime, tzinfo
from enum import StrEnum
from typing import Any, Final, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from jinja2 import Environment, StrictUndefined
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from threaddigest.core.retry import RunStatus, exit_code

__all__ = [
    "STALE_AFTER_RUNS",
    "Backlog",
    "Compliance",
    "Count",
    "DigestModel",
    "PostItem",
    "Problem",
    "Rankable",
    "RisingPhrase",
    "RisingPhrasesSection",
    "RunSummary",
    "SettingChange",
    "SubredditLine",
    "SubredditStatus",
    "ThemeSection",
    "UnknownEnum",
    "UnknownEnumSection",
    "UntaggedSection",
    "WorkspaceSection",
    "duration",
    "rank_posts",
    "render_html",
    "render_markdown",
    "when",
]

#: A source not fetched for this many runs is reported stale (PLAN.md, Resilience: "the
#: freshness invariants say so in the digest when a source has not been fetched for two
#: runs").
STALE_AFTER_RUNS: Final = 2


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")


# ------------------------------------------------------------------------ counts


class Count(_Frozen):
    """A count with its denominator: ``12 of 60 new posts (20%)``.

    ``population`` names what ``of`` counts ("new posts", "items seen"); the templates print
    the whole object, so a number never appears without its population. ``n`` may exceed
    ``of`` (a budget overspent by unplanned responses) and ``of`` may be zero (no
    percentage is shown).
    """

    n: int = Field(ge=0)
    of: int = Field(ge=0)
    population: str = Field(min_length=1)

    @property
    def pct(self) -> int | None:
        """Whole percent, half rounded up; None when the population is empty."""
        if self.of == 0:
            return None
        return math.floor(100 * self.n / self.of + 0.5)

    @property
    def text(self) -> str:
        return f"{self.n:,} of {self.of:,} {self.population}"

    @property
    def pct_text(self) -> str:
        return "" if self.pct is None else f" ({self.pct}%)"

    def __str__(self) -> str:
        return f"{self.text}{self.pct_text}"


# ----------------------------------------------------------------------- ranking


class Rankable(Protocol):
    """Anything :func:`rank_posts` can order: a digest item, a theme-page row, an export row."""

    @property
    def distinct_author_count(self) -> int: ...

    @property
    def comment_count(self) -> int: ...

    @property
    def score(self) -> int: ...

    @property
    def post_id(self) -> str: ...


def _rank_key(item: Rankable) -> tuple[int, int, int, str]:
    return (-item.distinct_author_count, -item.comment_count, -item.score, item.post_id)


def rank_posts[T: Rankable](items: Iterable[T]) -> list[T]:
    """Order posts by distinct authors, then comment count, then score, all descending, then by
    ``post_id`` ascending.

    Never by raw post count or recency: one prolific poster cannot manufacture a trend
    (DECISIONS.md D-09). The final ``post_id`` key is a tie-break for determinism, not a ranking
    signal (KI, external round one, reviewer C-8): a stable sort left full ties in input order,
    so a change in the order the database returned rows reordered the visible list. ``post_id``
    is unique and stable, so the order is now fully determined by the row's own values; creation
    time is deliberately not used, because recency is not a signal here.
    """
    return sorted(items, key=_rank_key)


class PostItem(_Frozen):
    """One post as the digest shows it: title and deep link only, never a body."""

    post_id: str = Field(min_length=1)
    title: str
    permalink: str = Field(min_length=1)
    subreddit: str = Field(min_length=1)
    distinct_author_count: int = Field(ge=0)
    comment_count: int = Field(ge=0)
    score: int
    created_utc: int


# -------------------------------------------------------------------- sections


class ThemeSection(_Frozen):
    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    #: Posts matched this run, of the new posts in the workspace.
    matched: Count
    top_posts: list[PostItem]


class UntaggedSection(_Frozen):
    """Posts no theme matched, surfaced when several people are talking about them."""

    window_days: int = Field(default=7, ge=1)
    min_distinct_authors: int = Field(default=3, ge=1)
    #: Untagged posts in the window that reached ``min_distinct_authors``, of all untagged
    #: posts in the window.
    qualifying: Count
    posts: list[PostItem]

    @model_validator(mode="after")
    def _posts_qualify(self) -> UntaggedSection:
        for post in self.posts:
            if post.distinct_author_count < self.min_distinct_authors:
                msg = (
                    f"untagged post {post.post_id} has {post.distinct_author_count} distinct "
                    f"authors, below the section's threshold of {self.min_distinct_authors}"
                )
                raise ValueError(msg)
        if len(self.posts) > self.qualifying.n:
            msg = f"{len(self.posts)} untagged posts listed but only {self.qualifying.n} qualify"
            raise ValueError(msg)
        return self


class RisingPhrase(_Frozen):
    phrase: str = Field(min_length=1)
    count_now: int = Field(ge=0)
    count_baseline: int = Field(ge=0)


class RisingPhrasesSection(_Frozen):
    """Title phrases more frequent this window than in the trailing baseline.

    The phrases arrive already computed as ``(phrase, count_now, count_baseline)``; this
    section only adds the two populations so each line renders with its denominators.
    """

    window_days: int = Field(default=7, ge=1)
    baseline_weeks: int = Field(default=4, ge=1)
    titles_now: int = Field(ge=0)
    titles_baseline: int = Field(ge=0)
    phrases: list[RisingPhrase]

    @field_validator("phrases", mode="before")
    @classmethod
    def _accept_tuples(cls, value: object) -> object:
        if not isinstance(value, list | tuple):
            return value
        converted: list[object] = []
        for item in value:
            if isinstance(item, list | tuple) and len(item) == 3:
                phrase, now, baseline = item
                converted.append({"phrase": phrase, "count_now": now, "count_baseline": baseline})
            else:
                converted.append(item)
        return converted

    def now(self, phrase: RisingPhrase) -> Count:
        return Count(
            n=phrase.count_now,
            of=self.titles_now,
            population=f"titles in the last {self.window_days} days",
        )

    def baseline(self, phrase: RisingPhrase) -> Count:
        return Count(
            n=phrase.count_baseline,
            of=self.titles_baseline,
            population=f"titles in the trailing {self.baseline_weeks} weeks",
        )


class WorkspaceSection(_Frozen):
    """One workspace: its share of the run's new posts, its top posts, its themes."""

    name: str = Field(min_length=1)
    slug: str = Field(min_length=1)
    #: The discovery window ``top_posts`` is ranked over, in days. Declared here because the
    #: list is a window's top posts, not an all-time list, and a heading that does not say so
    #: invites a reader to take it as the latter; the untagged and rising sections carry the
    #: same field for the same reason.
    window_days: int = Field(default=7, ge=1)
    #: New posts visible in this workspace, of all new posts this run.
    new_posts: Count
    top_posts: list[PostItem]
    themes: list[ThemeSection]
    untagged: UntaggedSection
    rising_phrases: RisingPhrasesSection


class SubredditStatus(StrEnum):
    """Values of ``subreddits.status``."""

    OK = "ok"
    FORBIDDEN = "forbidden"
    NOT_FOUND = "not_found"
    REDIRECT = "redirect"
    QUARANTINED = "quarantined"
    ERROR = "error"


class SubredditLine(_Frozen):
    """One source's row in the digest: what this run did to it and how healthy it is."""

    name: str = Field(min_length=1)
    status: SubredditStatus
    enabled: bool = True
    pages: int = Field(default=0, ge=0)
    items_seen: int = Field(default=0, ge=0)
    new_posts: int = Field(default=0, ge=0)
    updated_posts: int = Field(default=0, ge=0)
    #: ``run_subreddits.stop_reason``; None when the sweep was not attempted this run.
    stop_reason: str | None = None
    last_error: str | None = None
    consecutive_failures: int = Field(default=0, ge=0)
    #: 0 when fetched successfully this run; grows by one per run without a fetch.
    runs_since_fetched: int = Field(default=0, ge=0)
    gap_suspected_at: int | None = None

    @property
    def new(self) -> Count:
        return Count(n=self.new_posts, of=self.items_seen, population="items seen")

    @property
    def updated(self) -> Count:
        return Count(n=self.updated_posts, of=self.items_seen, population="items seen")

    @property
    def healthy(self) -> bool:
        return self.status is SubredditStatus.OK and self.stop_reason != "error"

    @property
    def stale(self) -> bool:
        return self.runs_since_fetched >= STALE_AFTER_RUNS

    @property
    def facts(self) -> list[str]:
        """Plain-text facts after the status; the templates join and escape them."""
        facts: list[str] = []
        if not self.enabled:
            facts.append("disabled")
        if self.pages or self.items_seen:
            facts.extend(
                (
                    f"{self.pages:,} {_plural_noun(self.pages, 'page')}",
                    f"new {self.new}",
                    f"updated {self.updated}",
                )
            )
        if self.stop_reason is not None:
            facts.append(f"stop: {self.stop_reason}")
        if self.runs_since_fetched == 0:
            facts.append("fetched this run")
        else:
            runs = _plural_noun(self.runs_since_fetched, "run")
            stale = " (stale)" if self.stale else ""
            facts.append(f"last fetched {self.runs_since_fetched:,} {runs} ago{stale}")
        if self.consecutive_failures:
            failures = _plural_noun(self.consecutive_failures, "consecutive failure")
            facts.append(f"{self.consecutive_failures:,} {failures}")
        if self.gap_suspected_at is not None:
            facts.append("gap suspected")
        return facts


class Backlog(_Frozen):
    #: Due posts whose tree was collected this run, of all posts due (TR-04).
    due_posts_harvested: Count
    #: Trees left with unexpanded ``more`` stubs, of trees fetched this run.
    trees_with_more_skipped: Count

    @property
    def remaining_due(self) -> Count:
        harvested = self.due_posts_harvested
        remaining = max(harvested.of - harvested.n, 0)
        return Count(n=remaining, of=harvested.of, population=harvested.population)


class Compliance(_Frozen):
    """Reconcile cadence and scrub outcome, so compliance cannot lapse quietly."""

    #: Age of the last complete reconcile; None when none has completed yet.
    last_reconcile_age_hours: float | None = Field(default=None, ge=0)
    #: The tier whose limit applies, e.g. "items 30 days old or younger".
    reconcile_tier: str = Field(min_length=1)
    tier_max_age_hours: int = Field(ge=1)
    #: Stored items re-checked via ``info()`` this run, of all stored items.
    reconciled: Count
    tier_fallback: bool
    #: Posts scrubbed, of posts checked this run.
    scrubbed_posts: Count
    #: Comments scrubbed, of comments checked this run.
    scrubbed_comments: Count
    #: Authors whose account deletion was applied, of authors seen this run.
    account_deletions: Count

    @property
    def overdue(self) -> bool:
        age = self.last_reconcile_age_hours
        return age is None or age > self.tier_max_age_hours


class Problem(_Frozen):
    """An error or warning recorded on the run row, with the unit of work it hit."""

    where: str = Field(min_length=1)
    message: str = Field(min_length=1)


class UnknownEnum(_Frozen):
    field: str = Field(min_length=1)
    value: str
    occurrences: int = Field(ge=1)


class UnknownEnumSection(_Frozen):
    """Upstream enum values we do not know, stored raw and counted (never coerced)."""

    rows_written: int = Field(ge=0)
    values: list[UnknownEnum]

    @property
    def count(self) -> Count:
        total = sum(value.occurrences for value in self.values)
        return Count(n=total, of=self.rows_written, population="rows written")

    def share(self, value: UnknownEnum) -> Count:
        return Count(n=value.occurrences, of=self.rows_written, population="rows written")


class SettingChange(_Frozen):
    key: str = Field(min_length=1)
    previous: str
    current: str


class RunSummary(_Frozen):
    run_id: int = Field(ge=1)
    status: RunStatus
    #: ``runs.trigger``: cli, ui or schedule.
    trigger: str = Field(min_length=1)
    started_at: int
    finished_at: int
    #: Requests made, of the run's budget (may exceed it: unplanned responses still count).
    api_requests: Count
    #: New posts, of listing items seen across every sweep.
    posts_new: Count
    #: Posts refreshed, of listing items seen.
    posts_updated: Count
    #: New comments, of comments seen in the trees fetched.
    comments_new: Count
    settings_fingerprint: str = Field(min_length=1)
    #: None on the very first run, when there is nothing to compare with.
    previous_settings_fingerprint: str | None
    #: Number of resolved non-secret settings that go into the fingerprint.
    settings_total: int = Field(ge=1)
    settings_changes: list[SettingChange]

    @model_validator(mode="after")
    def _consistent(self) -> RunSummary:
        if self.finished_at < self.started_at:
            msg = f"finished_at {self.finished_at} is before started_at {self.started_at}"
            raise ValueError(msg)
        if len(self.settings_changes) > self.settings_total:
            msg = f"{len(self.settings_changes)} changes exceed {self.settings_total} settings"
            raise ValueError(msg)
        if self.previous_settings_fingerprint is None and self.settings_changes:
            msg = "settings_changes need a previous fingerprint to have changed from"
            raise ValueError(msg)
        return self

    @property
    def exit_code(self) -> int:
        return exit_code(self.status)

    @property
    def duration_seconds(self) -> int:
        return self.finished_at - self.started_at

    @property
    def settings_changed(self) -> Count:
        return Count(
            n=len(self.settings_changes),
            of=self.settings_total,
            population="non-secret settings",
        )


class DigestModel(_Frozen):
    """Everything one digest says, assembled by the report service from the database."""

    report_date: date
    #: IANA zone for displayed times ("daily" boundaries are local by decision).
    display_timezone: str = "UTC"
    generated_at: int
    summary: RunSummary
    workspaces: list[WorkspaceSection]
    subreddits: list[SubredditLine]
    backlog: Backlog
    compliance: Compliance
    errors: list[Problem]
    warnings: list[Problem]
    unknown_enums: UnknownEnumSection

    @field_validator("display_timezone")
    @classmethod
    def _known_zone(cls, value: str) -> str:
        _zone(value)
        return value

    @property
    def healthy_subreddits(self) -> Count:
        healthy = sum(1 for sub in self.subreddits if sub.healthy)
        return Count(n=healthy, of=len(self.subreddits), population="subreddits")

    @property
    def gaps(self) -> list[SubredditLine]:
        return [sub for sub in self.subreddits if sub.gap_suspected_at is not None]

    @property
    def gap_count(self) -> Count:
        return Count(n=len(self.gaps), of=len(self.subreddits), population="subreddits")

    @property
    def stale_subreddits(self) -> Count:
        stale = sum(1 for sub in self.subreddits if sub.stale)
        return Count(n=stale, of=len(self.subreddits), population="subreddits")


# ------------------------------------------------------------------- rendering


def _zone(name: str) -> tzinfo:
    if name == "UTC":
        return UTC
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        msg = f"unknown display_timezone {name!r} (use 'UTC' or an IANA name like America/New_York)"
        raise ValueError(msg) from exc


def known_display_timezone(name: str) -> str:
    """Return ``name`` if the digest can resolve it as a display zone, else raise ``ValueError``.

    Pure: ``UTC`` or a loadable IANA zone, no filesystem or environment lookup (core stays the
    pure layer). The settings layer calls this so an unresolvable zone fails at load rather
    than at the first digest render (KI-011). The literal ``local`` is deliberately not
    accepted here: resolving the host's own zone is an environment concern for the M1d digest
    service, not core's, and shipping it as a config value made the first digest fail."""
    _zone(name)
    return name


def when(epoch: int, zone_name: str) -> str:
    """``2026-09-13 06:30 UTC``: minute precision, zone abbreviation, no seconds.

    Public because the web templates need the same rendering the digest uses: two spellings
    of "when" would eventually disagree about a zone or a seconds field, and one page showing
    a different time from the digest of the same run is exactly the drift this project
    treats as a defect. The Jinja filter below keeps the name ``when``.
    """
    moment = datetime.fromtimestamp(epoch, tz=_zone(zone_name))
    return moment.strftime("%Y-%m-%d %H:%M %Z")


def duration(seconds: int) -> str:
    """``11 min`` / ``2 h 05 min`` / ``42 s``: the one spelling of an elapsed time."""
    if seconds < 60:
        return f"{seconds} s"
    minutes, _ = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours} h {minutes} min"
    return f"{minutes} min"


def _hours(value: float | None) -> str:
    if value is None:
        return "never"
    if value == int(value):
        return f"{int(value)} h"
    return f"{value:.1f} h"


def _plural_noun(n: int, noun: str) -> str:
    return noun if n == 1 else f"{noun}s"


def _plural(n: int, noun: str) -> str:
    return f"{n:,} {_plural_noun(n, noun)}"


_MD_SPECIAL: Final = "\\`*_[]<>|"


def _md_escape(text: str) -> str:
    """Backslash-escape the markdown that a title or name could otherwise inject."""
    return "".join(f"\\{char}" if char in _MD_SPECIAL else char for char in text)


def _md_post(post: PostItem) -> str:
    return (
        f"[{_md_escape(post.title)}]({post.permalink}) — r/{post.subreddit} · "
        f"{_plural(post.distinct_author_count, 'author')} · "
        f"{_plural(post.comment_count, 'comment')} · score {post.score:,}"
    )


def _environment(*, autoescape: bool) -> Environment:
    env = Environment(
        undefined=StrictUndefined,
        autoescape=autoescape,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters.update(
        {
            "when": when,
            "duration": duration,
            "hours": _hours,
            "plural": _plural,
            "md": _md_escape,
            "md_post": _md_post,
        }
    )
    return env


_MARKDOWN_TEMPLATE: Final = """\
# Thread Digest for {{ m.report_date.isoformat() }}

## Run summary

- Run #{{ s.run_id }} ({{ s.trigger }}): **{{ s.status.value }}**, exit code {{ s.exit_code }}
- Started {{ s.started_at|when(tz) }}, finished {{ s.finished_at|when(tz) }}
{{- " (" }}{{ s.duration_seconds|duration }})
- API requests: {{ s.api_requests }}
- New posts: {{ s.posts_new }}
- Updated posts: {{ s.posts_updated }}
- New comments: {{ s.comments_new }}
- Problems: {{ m.errors|length|plural("error") }}, {{ m.warnings|length|plural("warning") }}
{{- " this run" }}
{% if s.previous_settings_fingerprint is none %}
- Settings: first run, nothing to compare with (fingerprint `{{ s.settings_fingerprint }}`)
{% else %}
- Settings changed since last run: {{ s.settings_changed }}
{% for change in s.settings_changes %}
  - `{{ change.key }}`: `{{ change.previous }}` → `{{ change.current }}`
{% endfor %}
{% endif %}
{% for w in m.workspaces %}

## Workspace: {{ w.name|md }}

- New posts in this workspace: {{ w.new_posts }}

### Top posts of the last {{ w.window_days }} days (ranked by distinct authors, then
{{- " " }}comments, then score)

{% for p in w.top_posts %}
{{ loop.index }}. {{ p|md_post }}
{% else %}
_No new posts._
{% endfor %}
{% for t in w.themes %}

### Theme {{ t.name|md }}: {{ t.matched }}

{% for p in t.top_posts %}
{{ loop.index }}. {{ p|md_post }}
{% else %}
_No posts matched this run._
{% endfor %}
{% endfor %}
{% set u = w.untagged %}

### Untagged posts with at least {{ u.min_distinct_authors }} distinct authors: {{ u.qualifying }}

{% for p in u.posts %}
{{ loop.index }}. {{ p|md_post }}
{% else %}
_No untagged post reached the threshold._
{% endfor %}
{% set r = w.rising_phrases %}

### Rising title phrases (last {{ r.window_days }} days against the trailing
{{- " " }}{{ r.baseline_weeks }} weeks)

{% for ph in r.phrases %}
- "{{ ph.phrase|md }}": {{ r.now(ph) }} vs {{ r.baseline(ph) }}
{% else %}
_No phrase is rising._
{% endfor %}
{% endfor %}

## Subreddits: {{ m.healthy_subreddits.text }} swept without error
{{- m.healthy_subreddits.pct_text }}

{% for sub in m.subreddits %}
- r/{{ sub.name }}: {% if sub.healthy %}{{ sub.status.value }}{% else %}**{{ sub.status.value }}**
{%- endif %}{% for fact in sub.facts %} · {{ fact }}{% endfor %}
{%- if sub.last_error %} · error: `{{ sub.last_error }}`{% endif %}

{% endfor %}
- Stale sources (not fetched for at least {{ STALE_AFTER_RUNS }} runs): {{ m.stale_subreddits }}

## Backlog

- Due posts harvested: {{ b.due_posts_harvested }}; {{ b.remaining_due }} remain queued
- Trees with unexpanded "more" stubs: {{ b.trees_with_more_skipped }}

## Gaps: {{ m.gap_count }}

{% for sub in m.gaps %}
- r/{{ sub.name }}: listing cap reached before known territory
{{- " at " }}{{ sub.gap_suspected_at|when(tz) }} (`stop_reason=cap`)
{% else %}
_No gap suspected._
{% endfor %}

## Errors: {{ m.errors|length|plural("error") }} this run

{% for e in m.errors %}
- {{ e.where|md }}: `{{ e.message }}`
{% else %}
_None._
{% endfor %}

## Warnings: {{ m.warnings|length|plural("warning") }} this run

{% for wn in m.warnings %}
- {{ wn.where|md }}: `{{ wn.message }}`
{% else %}
_None._
{% endfor %}

## Unknown enum values: {{ m.unknown_enums.count }}

{% for v in m.unknown_enums.values %}
- `{{ v.field }}` = `{{ v.value }}`: {{ m.unknown_enums.share(v) }}
{% else %}
_None._
{% endfor %}

## Compliance

- Last complete reconcile: {{ c.last_reconcile_age_hours|hours }} ago
{{- " (limit " }}{{ c.tier_max_age_hours }} h for {{ c.reconcile_tier }});
{{- " overdue" if c.overdue else " on time" }}
- Reconciled this run: {{ c.reconciled }}
{%- if c.tier_fallback %}; fell back to tiers because the budget could not cover a full sweep
{%- endif %}

- Scrubbed posts: {{ c.scrubbed_posts }}
- Scrubbed comments: {{ c.scrubbed_comments }}
- Account deletions applied: {{ c.account_deletions }}

---

Generated from the database at {{ m.generated_at|when(tz) }}. Titles and links only;
bodies are never persisted in a report.
"""


_HTML_TEMPLATE: Final = """\
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Thread Digest for {{ m.report_date.isoformat() }}</title>
<style>
body { font-family: system-ui, sans-serif; max-width: 60rem; margin: 2rem auto; padding: 0 1rem; }
.bad { color: #b00020; font-weight: bold; }
</style>
</head>
<body>
<h1>Thread Digest for {{ m.report_date.isoformat() }}</h1>
<h2>Run summary</h2>
<ul>
<li>Run #{{ s.run_id }} ({{ s.trigger }}): <strong>{{ s.status.value }}</strong>,
{{- " exit code " }}{{ s.exit_code }}</li>
<li>Started {{ s.started_at|when(tz) }}, finished {{ s.finished_at|when(tz) }}
{{- " (" }}{{ s.duration_seconds|duration }})</li>
<li>API requests: {{ s.api_requests }}</li>
<li>New posts: {{ s.posts_new }}</li>
<li>Updated posts: {{ s.posts_updated }}</li>
<li>New comments: {{ s.comments_new }}</li>
<li>Problems: {{ m.errors|length|plural("error") }}, {{ m.warnings|length|plural("warning") }}
{{- " this run" }}</li>
{% if s.previous_settings_fingerprint is none %}
<li>Settings: first run, nothing to compare with
{{- " (fingerprint " }}<code>{{ s.settings_fingerprint }}</code>)</li>
{% else %}
<li>Settings changed since last run: {{ s.settings_changed }}
{% if s.settings_changes %}
<ul>
{% for change in s.settings_changes %}
<li><code>{{ change.key }}</code>: <code>{{ change.previous }}</code> →
{{- " " }}<code>{{ change.current }}</code></li>
{% endfor %}
</ul>
{% endif %}
</li>
{% endif %}
</ul>
{% macro posts(items, empty) %}
{% if items %}
<ol>
{% for p in items %}
<li><a href="{{ p.permalink }}">{{ p.title }}</a> — r/{{ p.subreddit }} ·
{{- " " }}{{ p.distinct_author_count|plural("author") }} ·
{{- " " }}{{ p.comment_count|plural("comment") }} · score {{ "{:,}".format(p.score) }}</li>
{% endfor %}
</ol>
{% else %}
<p><em>{{ empty }}</em></p>
{% endif %}
{% endmacro %}
{% for w in m.workspaces %}
<h2>Workspace: {{ w.name }}</h2>
<p>New posts in this workspace: {{ w.new_posts }}</p>
<h3>Top posts of the last {{ w.window_days }} days (ranked by distinct authors, then
{{- " " }}comments, then score)</h3>
{{ posts(w.top_posts, "No new posts.") }}
{% for t in w.themes %}
<h3>Theme {{ t.name }}: {{ t.matched }}</h3>
{{ posts(t.top_posts, "No posts matched this run.") }}
{% endfor %}
{% set u = w.untagged %}
<h3>Untagged posts with at least {{ u.min_distinct_authors }} distinct authors:
{{- " " }}{{ u.qualifying }}</h3>
{{ posts(u.posts, "No untagged post reached the threshold.") }}
{% set r = w.rising_phrases %}
<h3>Rising title phrases (last {{ r.window_days }} days against the trailing
{{- " " }}{{ r.baseline_weeks }} weeks)</h3>
{% if r.phrases %}
<ul>
{% for ph in r.phrases %}
<li>"{{ ph.phrase }}": {{ r.now(ph) }} vs {{ r.baseline(ph) }}</li>
{% endfor %}
</ul>
{% else %}
<p><em>No phrase is rising.</em></p>
{% endif %}
{% endfor %}
<h2>Subreddits: {{ m.healthy_subreddits.text }} swept without error
{{- m.healthy_subreddits.pct_text }}</h2>
<ul>
{% for sub in m.subreddits %}
<li>r/{{ sub.name }}: {% if sub.healthy %}{{ sub.status.value }}
{%- else %}<span class="bad">{{ sub.status.value }}</span>{% endif %}
{%- for fact in sub.facts %} · {{ fact }}{% endfor %}
{%- if sub.last_error %} · error: <code>{{ sub.last_error }}</code>{% endif %}</li>
{% endfor %}
<li>Stale sources (not fetched for at least {{ STALE_AFTER_RUNS }} runs): {{ m.stale_subreddits }}
{{- "" }}</li>
</ul>
<h2>Backlog</h2>
<ul>
<li>Due posts harvested: {{ b.due_posts_harvested }}; {{ b.remaining_due }} remain queued</li>
<li>Trees with unexpanded "more" stubs: {{ b.trees_with_more_skipped }}</li>
</ul>
<h2>Gaps: {{ m.gap_count }}</h2>
{% if m.gaps %}
<ul>
{% for sub in m.gaps %}
<li>r/{{ sub.name }}: listing cap reached before known territory at
{{- " " }}{{ sub.gap_suspected_at|when(tz) }} (<code>stop_reason=cap</code>)</li>
{% endfor %}
</ul>
{% else %}
<p><em>No gap suspected.</em></p>
{% endif %}
<h2>Errors: {{ m.errors|length|plural("error") }} this run</h2>
{% if m.errors %}
<ul>
{% for e in m.errors %}
<li>{{ e.where }}: <code>{{ e.message }}</code></li>
{% endfor %}
</ul>
{% else %}
<p><em>None.</em></p>
{% endif %}
<h2>Warnings: {{ m.warnings|length|plural("warning") }} this run</h2>
{% if m.warnings %}
<ul>
{% for wn in m.warnings %}
<li>{{ wn.where }}: <code>{{ wn.message }}</code></li>
{% endfor %}
</ul>
{% else %}
<p><em>None.</em></p>
{% endif %}
<h2>Unknown enum values: {{ m.unknown_enums.count }}</h2>
{% if m.unknown_enums.values %}
<ul>
{% for v in m.unknown_enums.values %}
<li><code>{{ v.field }}</code> = <code>{{ v.value }}</code>: {{ m.unknown_enums.share(v) }}</li>
{% endfor %}
</ul>
{% else %}
<p><em>None.</em></p>
{% endif %}
<h2>Compliance</h2>
<ul>
<li>Last complete reconcile: {{ c.last_reconcile_age_hours|hours }} ago
{{- " (limit " }}{{ c.tier_max_age_hours }} h for {{ c.reconcile_tier }});
{{- " overdue" if c.overdue else " on time" }}</li>
<li>Reconciled this run: {{ c.reconciled }}
{%- if c.tier_fallback %}; fell back to tiers because the budget could not cover a full sweep
{%- endif %}</li>
<li>Scrubbed posts: {{ c.scrubbed_posts }}</li>
<li>Scrubbed comments: {{ c.scrubbed_comments }}</li>
<li>Account deletions applied: {{ c.account_deletions }}</li>
</ul>
<hr>
<p>Generated from the database at {{ m.generated_at|when(tz) }}. Titles and links only;
bodies are never persisted in a report.</p>
</body>
</html>
"""

_MARKDOWN = _environment(autoescape=False).from_string(_MARKDOWN_TEMPLATE)
_HTML = _environment(autoescape=True).from_string(_HTML_TEMPLATE)


def _context(model: DigestModel) -> dict[str, Any]:
    return {
        "m": model,
        "s": model.summary,
        "b": model.backlog,
        "c": model.compliance,
        "tz": model.display_timezone,
        "STALE_AFTER_RUNS": STALE_AFTER_RUNS,
    }


def render_markdown(model: DigestModel) -> str:
    """The digest as CommonMark; deterministic for a given model."""
    return _MARKDOWN.render(_context(model))


def render_html(model: DigestModel) -> str:
    """The digest as a small self-contained HTML page (autoescaped)."""
    return _HTML.render(_context(model))
