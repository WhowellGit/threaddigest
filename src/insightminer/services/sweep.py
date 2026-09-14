"""Step 1 of the collector algorithm: forward ``after`` paging over ``/r/<name>/new``, one
transaction per page, the per-subreddit status machine and the retry ladder
(design-round5 §6).

Four rules decide almost everything in here, and none of them is a detail:

* **The stop rule.** ``core.paging.plan_stop`` owns the cap; the *port* owns the end of the
  listing. ``CAP`` is terminal immediately and is tested first; ``EXHAUSTED`` from
  ``plan_stop`` is terminal only when ``page.complete`` or ``page.after is None`` agrees,
  because an empty page in the middle of a live listing (a run of deleted posts) is not the
  end of the listing (§6.2).
* **Counters are folded after a commit, never inside one.** :func:`write_page` mutates no
  counter: if its :class:`PageWriteResult` does not reach :func:`_page_loop`, nothing was
  committed and nothing must be counted (§6.4.2, P0-2).
* **Two grains, one row.** Each committed page writes a ``run_subreddits`` row with
  ``stop_reason=NULL`` (the progress a crash leaves behind); one terminal transaction (T6)
  then carries the final ``stop_reason`` *and* that subreddit's ``subreddits`` writes, so a
  source's outcome and its status can never disagree (§6.3, §7).
* **Announcements follow the commit.** ``ctx.warn`` for the disable and the gap, and every
  ``notifier.notify``, run after T6 returns, so nothing is announced that did not happen
  (§6.9). The one deliberate exception is the per-source failure warning, which is recorded
  before the dry-run branch so that ``run --dry-run`` reports a 403 instead of exiting 0
  (round5-findings.json, ``P1-dry-run-swallows-failures``).

Heartbeats sit **outside** every per-source handler -- at the top of the loop's iteration and
inside :func:`fetch_page` before a sleep, which is why the loop's ``try`` is split in two: a
failing ``runs.heartbeat`` means this process cannot write the run row at all and must never
be recorded as the swept source's fault (§6.2 note 8, §7, round5-findings.json,
``P1-heartbeat-inside-per-source-try``).
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, replace
from types import MappingProxyType
from typing import Any, Final

from sqlalchemy.exc import DatabaseError, IntegrityError, OperationalError

from insightminer.core.deletion import AuthorState, ContentState, Observation, decide
from insightminer.core.milestones import next_check
from insightminer.core.models import PostRow, Reject, count_unknown
from insightminer.core.normalize import canonicalize, normalize_post
from insightminer.core.paging import (
    DEFAULT_CAP,
    PageItem,
    StopReason,
    SweepState,
    gap_suspected,
    plan_stop,
)
from insightminer.core.retry import (
    ExitCode,
    Outcome,
    RetryPolicy,
    RunStatus,
    classify,
    plan_rate_limit_wait,
)
from insightminer.db import repo
from insightminer.db.ownership import IngestPath
from insightminer.ports import (
    AuthFailed,
    GatewayError,
    HtmlBlocked,
    Notifier,
    Page,
    RateLimited,
    RedditGateway,
    SubredditForbidden,
    SubredditNotFound,
    SubredditQuarantined,
    SubredditRedirected,
    TransientError,
)
from insightminer.services import runs
from insightminer.services.runs import RunContext, RunTerminalError

__all__ = [
    "MAX_PAGES_PER_SUBREDDIT",
    "PAGES_PER_CALL",
    "QUARANTINE_DISABLE_AFTER",
    "REDIRECT_DISABLE_AFTER",
    "PageWriteResult",
    "PreparedPage",
    "SubredditFailure",
    "SubredditIdentityError",
    "SubredditSweep",
    "SweepResult",
    "fetch_page",
    "preflight",
    "sweep_all",
    "sweep_subreddit",
    "write_page",
]

#: SS-03, Wes's Q3/Q10 answer. Provisional, with a GUARDS.md row saying so (§19.14); the
#: test reads this constant rather than restating 3, so changing it is a one-line change.
REDIRECT_DISABLE_AFTER: Final = 3
#: SS-04: a quarantined source is disabled the first time it is seen.
QUARANTINE_DISABLE_AFTER: Final = 1
#: One page per ``iter_new_pages`` call: the iterator is lazy, so a failure raised
#: mid-iteration cannot be retried without re-creating it. The sweep keeps the cursor
#: itself, which makes the retry ladder a plain retry of one call and makes "crash between
#: pages" resume at exactly the right cursor (§6.1).
PAGES_PER_CALL: Final = 1

#: Fail-closed ceiling on pages fetched for ONE subreddit in ONE run (§6.2). Reddit's listing
#: cap is 1,000 items at 100 a page, i.e. 10 pages; 120 is far above any healthy listing and
#: far below "forever". Reaching it means the gateway or this loop is misbehaving, so it
#: warns, stops that subreddit with ``stop_reason`` NULL (interrupted), and lets the run go on.
MAX_PAGES_PER_SUBREDDIT: Final = 120

#: ``posts.source`` for everything this module writes, and the ``source`` argument
#: ``core.normalize.normalize_post`` records on the row (§6.4.1). Spelled from the ownership
#: declaration so the value the upsert is generated for and the value written cannot drift.
_INGEST_SOURCE: Final = IngestPath.SUBREDDIT_NEW.value

#: ``post_sources.source_type`` for a ``/new`` sweep; one of ``db.schema.SOURCE_TYPES``.
_SOURCE_TYPE: Final = "subreddit"


class SubredditIdentityError(RuntimeError):
    """The listing's ``subreddit_id`` disagrees with the stored one (SS-05).

    Aborts THAT SUBREDDIT, never the run, and **before anything from that source is
    written**: it is raised inside :func:`_page_loop` between :func:`_prepare_page` and
    :func:`write_page` (§6.2). :func:`sweep_subreddit` then sets ``status='error'``,
    increments ``consecutive_failures``, notifies at level ``error`` and records
    ``stop_reason='error'``.

    The message is built here, so call sites pass fields and never a string (TRY003).
    """

    def __init__(self, *, name_lower: str, stored: str, observed: str) -> None:
        super().__init__(f"r/{name_lower}: stored {stored}, listing returned {observed}")
        self.name_lower = name_lower
        self.stored = stored
        self.observed = observed


@dataclass(frozen=True, slots=True)
class SubredditFailure:
    """What one per-source failure means.

    PURE: built by :func:`_classify_failure` from the §8 table with no DB access, no clock
    and no notifier, so the decision is unit-testable and the transaction that applies it is
    the only thing that touches the database (§6.3).
    """

    #: A ``subreddits.status`` value: forbidden | not_found | redirect | quarantined | error.
    status: str
    #: Goes to ``subreddits.last_error`` and ``run_subreddits.error``.
    message: str
    #: ``consecutive_failures`` at which the source is disabled; None = never.
    disable_at: int | None
    #: The failure itself notifies (SS-01/SS-04/SS-05), separately from the disable, which
    #: always notifies (§6.9).
    notify: bool


@dataclass(frozen=True, slots=True)
class PageWriteResult:
    """What one COMMITTED page changed. Folded into ``Counters`` by :func:`_page_loop` (§6.2).

    :func:`write_page` mutates no counter: if this object does not reach the caller, nothing
    was committed and nothing must be counted (P0-2).
    """

    items_seen: int
    new_posts: int
    updated_posts: int
    rejects: int
    snapshots: int
    source_links: int
    #: ``"<reddit_id>|<field>=<value>"`` for every unknown enum occurrence on this page.
    unknown_enum_keys: frozenset[str]
    #: Rows whose ``core.deletion.Decision.scrub`` is True.
    scrub_transitions: int


@dataclass(frozen=True, slots=True)
class PreparedPage:
    """One fetched page after normalization and **before** any DB access (§6.4.1).

    Pure: built by :func:`_prepare_page` from ``ports.Page`` with no connection, no clock and
    no settings, so it is unit-testable on its own and so ``plan_stop`` is never handed a raw
    wire dict. ``page_items`` covers the accepted rows only; ``rejects`` are the items
    ``core.normalize`` refused, which still occupied listing slots (§6.2).
    """

    #: The port's page, kept for ``after`` / ``complete`` and for the raw items ``raw_json``
    #: is built from.
    page: Page
    rows: tuple[PostRow, ...]
    rejects: tuple[Reject, ...]
    page_items: tuple[PageItem, ...]
    unknown_enum_keys: frozenset[str]
    #: First non-null ``subreddit_id`` on the page (SS-05).
    observed_subreddit_id: str | None

    @property
    def slots(self) -> int:
        """Listing positions this page occupied: accepted rows plus rejects."""
        return len(self.rows) + len(self.rejects)


@dataclass(frozen=True, slots=True)
class SubredditSweep:
    """What one subreddit's sweep did, as ``collect`` and the CLI summary read it (§3.3)."""

    subreddit_pk: int
    name_lower: str
    #: Pages **fetched** (one HTTP request each). Can exceed ``SweepState.pages``, which
    #: counts only *absorbed* pages and so skips an empty one; never the other way round.
    pages: int
    items_seen: int
    new_items: int
    updated_items: int
    #: None = interrupted (§19.4).
    stop_reason: StopReason | None
    #: ``subreddits.status`` after this sweep.
    status: str
    error: str | None
    gap_suspected: bool
    #: The source left collection in THIS sweep (§6.9).
    disabled: bool


@dataclass(frozen=True, slots=True)
class SweepResult:
    """Every subreddit's outcome, plus the terminal state when the whole run must end."""

    subreddits: tuple[SubredditSweep, ...]
    terminal_status: RunStatus | None
    terminal_error: str | None
    #: 78 for an ``AuthFailed`` (§9); None means ``core.retry.exit_code`` applies.
    exit_code_override: int | None


@dataclass(frozen=True, slots=True)
class _LoopOutcome:
    """What :func:`_page_loop` got through, whether or not it ended cleanly."""

    state: SweepState
    #: HTTP pages; >= ``state.pages``, never fewer (§3.3).
    pages_fetched: int
    new_items: int
    updated_items: int
    #: None = interrupted (ceiling, budget, page ceiling, stalled cursor).
    stop_reason: StopReason | None
    observed_subreddit_id: str | None


@dataclass(frozen=True, slots=True)
class _FinishResult:
    """What T6 committed, read back so the caller can be loud about it (§6.9)."""

    status: str
    consecutive_failures: int
    #: The source left collection in THIS transaction.
    disabled: bool
    #: ``gap_suspected_at`` was stamped by THIS transaction.
    gap_suspected: bool
    #: What went on the terminal ``run_subreddits`` row.
    stop_reason: StopReason | None


#: The §8 error table as data: exception class -> (subreddits.status, disable_at, notify).
#: Keyed on the exact class, because every entry is a leaf of ``ports``' hierarchy and a
#: subclass would be a new row of §8 rather than an inherited one. Anything absent is the
#: table's last row: ``error``, ``+1``, no auto-disable, no notification.
_FAILURE_TABLE: Final[Mapping[type[Exception], tuple[str, int | None, bool]]] = MappingProxyType(
    {
        SubredditForbidden: ("forbidden", None, False),
        SubredditNotFound: ("not_found", None, True),
        SubredditRedirected: ("redirect", REDIRECT_DISABLE_AFTER, False),
        SubredditQuarantined: ("quarantined", QUARANTINE_DISABLE_AFTER, False),
        SubredditIdentityError: ("error", None, True),
    }
)
_DEFAULT_FAILURE: Final[tuple[str, int | None, bool]] = ("error", None, False)


# --- normalization, pure (§6.4.1) -----------------------------------------------------------


def _prepare_page(page: Page, *, source_name: str) -> PreparedPage:
    """Normalize one page: split rows from rejects, build ``PageItem``s, collect the unknown
    enum occurrences and the observed ``t5_`` identity. No DB, no clock, no settings.

    ``normalize_post`` never raises -- its ``_guarded`` wrapper turns any failure into a
    ``Reject``, which is the whole reason ``raw_rejects`` exists -- so this function is total
    and a wire-shape change can never take a run down.

    ``source_name`` is accepted for call-site symmetry with the rest of the per-source
    functions and never read: ``posts.source`` is the *ingest path* (:data:`_INGEST_SOURCE`),
    not the subreddit, and the subreddit is carried by ``posts.subreddit_pk``.
    """
    del source_name
    rows: list[PostRow] = []
    rejects: list[Reject] = []
    page_items: list[PageItem] = []
    unknown: set[str] = set()
    observed: str | None = None
    for item in page.items:
        result = normalize_post(item, source=_INGEST_SOURCE)
        if isinstance(result, Reject):
            rejects.append(result)
            continue
        rows.append(result)
        page_items.append(PageItem(result.reddit_id, result.created_utc, result.stickied or False))
        # Occurrence KEYS, not a running integer: overlapping pages re-deliver the same post
        # and a per-item counter would double-count it (SW-03, §13.1).
        unknown.update(f"{result.reddit_id}|{key}" for key in count_unknown(result))
        if observed is None and result.subreddit_id is not None:
            observed = result.subreddit_id
    return PreparedPage(
        page=page,
        rows=tuple(rows),
        rejects=tuple(rejects),
        page_items=tuple(page_items),
        unknown_enum_keys=frozenset(unknown),
        observed_subreddit_id=observed,
    )


def _check_identity(source: repo.SubredditRow, prepared: PreparedPage) -> None:
    """SS-05. A no-op until a page carries a non-null ``subreddit_id``, and a no-op while the
    stored identity is NULL (adoption happens in T6). Its own function so the ``raise`` is
    not a raise-inside-a-try (ruff TRY301).
    """
    observed = prepared.observed_subreddit_id
    if observed is not None and source.subreddit_id is not None and observed != source.subreddit_id:
        raise SubredditIdentityError(
            name_lower=source.name_lower, stored=source.subreddit_id, observed=observed
        )


# --- the page loop (§6.2) -------------------------------------------------------------------


def _outcome(
    state: SweepState,
    pages: int,
    new_items: int,
    updated_items: int,
    stop_reason: StopReason | None,
    observed_subreddit_id: str | None,
) -> _LoopOutcome:
    """Build the loop's outcome from its locals; called on both the success and the failure
    return, which is the whole reason it exists."""
    return _LoopOutcome(
        state=state,
        pages_fetched=pages,
        new_items=new_items,
        updated_items=updated_items,
        stop_reason=stop_reason,
        observed_subreddit_id=observed_subreddit_id,
    )


def _interrupted_before_page(ctx: RunContext, name: str, pages: int) -> bool:
    """The three boundaries that stop a subreddit **without** a stop reason (§19.4).

    All three record a ``RunWarning`` -- so the run is ``partial``, never ``ok`` -- and leave
    ``stop_reason`` NULL, i.e. interrupted, so none of them can fake complete coverage. The
    page ceiling is fail-closed guard 1: with the §6.2 stop rule an adversarial gateway that
    always returns an empty page with a fresh cursor would otherwise never stop, because
    ``items_seen`` never grows and the cap can never fire.

    It lives outside :func:`_page_loop`'s handlers by construction: none of the three is a
    property of the subreddit being swept.
    """
    if ctx.over_ceiling:
        ctx.warn("wall_clock_ceiling", f"r/{name}: stopped after {pages} pages")
        return True
    if not ctx.budget.can_afford(1):
        ctx.warn("budget_exhausted", f"r/{name}: stopped after {pages} pages")
        return True
    if pages >= MAX_PAGES_PER_SUBREDDIT:
        ctx.warn("page_ceiling", f"r/{name}: {pages} pages without an end of listing")
        return True
    return False


def _page_loop(
    ctx: RunContext, source: repo.SubredditRow, *, gateway: RedditGateway
) -> tuple[_LoopOutcome, Exception | None]:
    """Page one subreddit forward until the port or the cap says stop.

    Returns the PARTIAL outcome alongside the per-source exception, so the terminal row
    always carries the pages that really committed (P0-3). It never catches
    ``RunTerminalError`` (a run-level abort propagates to :func:`sweep_all`) and never
    ``CrashInjected`` (SW-04's crash must escape).

    The ``try`` is split in two on purpose (round5-findings.json,
    ``P1-heartbeat-inside-per-source-try``): the fetch/normalize/identity half catches the
    gateway's own classes, the write half catches the database's. The heartbeat, the budget
    sync and the three loop guards sit outside both, because none of them is a property of
    the subreddit being swept.
    """
    state = SweepState()
    cursor: str | None = None
    stop_reason: StopReason | None = None
    pages = 0
    new_items = updated_items = 0
    observed_t5: str | None = None
    name = source.name_lower

    while True:
        # --- boundary work, OUTSIDE both per-source handlers (§6.2 note 8) ---
        runs.heartbeat(ctx, stage=f"sweep:{name}:p{pages + 1}")
        runs.sync_budget(ctx, gateway)
        if _interrupted_before_page(ctx, name, pages):
            break

        try:
            page = fetch_page(ctx, gateway=gateway, name=name, after=cursor, policy=RetryPolicy())
            pages += 1
            ctx.counters.pages += 1
            prepared = _prepare_page(page, source_name=name)
            _check_identity(source, prepared)  # SS-05, BEFORE any write
        except (SubredditIdentityError, GatewayError) as exc:
            return _outcome(state, pages, new_items, updated_items, None, observed_t5), exc

        observed_t5 = observed_t5 or prepared.observed_subreddit_id
        items_before = state.items_seen
        # `plan_stop` cannot see the rejects, so the slots they occupied are pre-loaded into
        # the state it is handed. Only `items_seen` moves: a reject has no id and no
        # timestamp, and guessing one would move the gap detector's window (§6.2).
        state_in = replace(state, items_seen=items_before + len(prepared.rejects))
        decision = plan_stop(prepared.page_items, state_in, cap=DEFAULT_CAP)
        state = decision.state

        if not ctx.dry_run:
            try:
                result = write_page(
                    ctx,
                    source,
                    prepared,
                    progress_before=repo.SweepProgress(
                        pages=pages,
                        items_seen=items_before,
                        new_items=new_items,
                        updated_items=updated_items,
                        stop_reason=None,
                        error=None,
                    ),
                )
            except (OperationalError, IntegrityError) as exc:
                return _outcome(state, pages, new_items, updated_items, None, observed_t5), exc
            # EVERY counter is folded HERE, after the transaction committed (P0-2).
            new_items += result.new_posts
            updated_items += result.updated_posts
            ctx.counters.posts_new += result.new_posts
            ctx.counters.posts_updated += result.updated_posts
            ctx.counters.rejects += result.rejects
            ctx.counters.scrubs_pending += result.scrub_transitions
            ctx.unknown_enum_keys |= result.unknown_enum_keys

        if decision.stop and decision.reason is StopReason.CAP:  # route 1: the cap
            stop_reason = StopReason.CAP
            break
        if page.complete or page.after is None:  # route 2: the port
            stop_reason = StopReason.EXHAUSTED
            break
        if page.after == cursor:  # fail-closed guard 2
            # `stop_reason` is left NULL exactly as guard 1 leaves it: a gateway whose cursor
            # stopped advancing has proved nothing, and `exhausted` here would let
            # `_coverage_proven` stamp complete coverage over a truncated window
            # (round5-findings.json, `P0-cursor-stalled`).
            ctx.warn("cursor_stalled", f"r/{name}: after did not advance past {cursor}")
            break
        cursor = page.after
        # A `decision.stop` of EXHAUSTED with a live cursor falls through on purpose: an
        # empty or all-rejected page in the middle of a listing is not the end of it.

    return _outcome(state, pages, new_items, updated_items, stop_reason, observed_t5), None


# --- one page's transaction (T5, §6.4.2) ----------------------------------------------------


def _post_write(
    row: PostRow,
    prior: repo.PriorPost | None,
    *,
    subreddit_pk: int,
    raw: Mapping[str, Any],
    now: int,
    ladder: Sequence[int],
) -> tuple[repo.PostWrite, bool]:
    """One row's columns, decided against the prior row. Returns the write and whether this
    observation is a transition INTO a scrub state.

    The sweep stores **exactly what the wire returned**: ``selftext`` keeps the literal
    ``[deleted]`` / ``[removed]`` marker and ``removed_by_category`` is stored raw. Redacting
    content is the scrub service's job at M1c, and tranche A never writes ``scrubbed_at``.

    ``check_stage`` is 0 and ``next_check_at`` is ``next_check(created_utc, 0, ...)``: stage 0
    means "discovered", and the returned ``next_stage`` is what to pass back *after* that
    check has run. Writing 1 here would skip the first rung of the ladder for every post ever
    ingested. Both columns are insert-only; the revisit service owns them from M1b.
    """
    prior_state = ContentState.LIVE if prior is None else ContentState(prior.content_state)
    prior_author = AuthorState.KNOWN if prior is None else AuthorState(prior.author_state)
    observation = Observation(
        body=row.selftext,
        author=row.author,
        author_fullname_present=row.author_fullname is not None,
        removed_by_category=row.removed_by_category,
        is_link_post=not (row.is_self or False),
        returned_by_info=None,
    )
    decision = decide(prior_state, prior_author, observation, 0 if prior is None else prior.misses)
    next_check_at, _next_stage = next_check(row.created_utc, 0, ladder)
    write = repo.PostWrite(
        row=row,
        subreddit_pk=subreddit_pk,
        first_seen_at=now if prior is None else prior.first_seen_at,
        last_fetched_at=now,
        next_check_at=next_check_at,
        check_stage=0,
        content_state=decision.content_state.value,
        author_state=decision.author_state.value,
        misses=decision.misses,
        raw_json=json.dumps(raw, sort_keys=True, separators=(",", ":"), default=str),
    )
    return write, decision.scrub


def _snapshot_needed(row: PostRow, prior: repo.PriorPost | None) -> bool:
    """One ``item_snapshots`` row per post per run would be ~9,000 rows a day for three
    subreddits; "changed or new" keeps the history meaningful and small (§19.7).

    The numbers are coalesced the way ``repo.post_values`` coalesces them, so a post whose
    wire ``score`` is absent does not look changed on every single run.
    """
    if prior is None:
        return True
    score = 0 if row.score is None else row.score
    num_comments = 0 if row.num_comments is None else row.num_comments
    return (score, num_comments, row.upvote_ratio) != (
        prior.score,
        prior.num_comments,
        prior.upvote_ratio,
    )


def _snapshots(
    writes: Sequence[repo.PostWrite],
    priors: Mapping[str, repo.PriorPost],
    pks: Mapping[str, int],
    now: int,
) -> list[repo.SnapshotWrite]:
    """Numeric-only history rows for the posts that are new or whose numbers moved."""
    return [
        repo.SnapshotWrite(
            item_pk=pks[write.row.reddit_id],
            kind="post",
            fetched_at=now,
            score=write.row.score,
            num_comments=write.row.num_comments,
            upvote_ratio=write.row.upvote_ratio,
        )
        for write in writes
        if _snapshot_needed(write.row, priors.get(write.row.reddit_id))
    ]


def _author_writes(rows: Sequence[PostRow]) -> list[repo.AuthorWrite]:
    """Identity rows for the page's authors, keyed on the newest item each one appears on.

    A row whose author Reddit shows as ``[deleted]`` carries neither a name nor a fullname,
    so it contributes no ``authors`` row at all: the account's identity is exactly what is no
    longer knowable.
    """
    latest: dict[str, repo.AuthorWrite] = {}
    for row in rows:
        if row.author is None or row.author_fullname is None:
            continue
        seen = latest.get(row.author_fullname)
        if seen is None or row.created_utc > seen.seen_at:
            latest[row.author_fullname] = repo.AuthorWrite(
                author_fullname=row.author_fullname, name=row.author, seen_at=row.created_utc
            )
    return list(latest.values())


def write_page(
    ctx: RunContext,
    source: repo.SubredditRow,
    prepared: PreparedPage,
    *,
    progress_before: repo.SweepProgress,
) -> PageWriteResult:
    """One page, ONE transaction (T5): rejects, posts, provenance, snapshots, authors and the
    per-page ``run_subreddits`` progress row -- all of it or none of it (§7).

    Takes the PREPARED page, so it never sees a raw wire dict, and **mutates no counter and
    no ``ctx`` state at all** (P0-2): round 3 incremented ``counters.rejects`` before the
    upsert, so a rolled-back page left the counter raised and made
    ``counters_equal_table_deltas`` -- a FAILURE invariant -- fire against the collector
    itself on what is really lock contention.

    ``progress_before`` is uniform -- every count in it is the total *before* this page --
    with one documented exception: ``pages`` already counts this fetch, because the page has
    been fetched by the time this is called (§6.2 note 6).
    """
    now = ctx.clock.now()
    # The canonical wire item behind each accepted row, for `posts.raw_json`. Every accepted
    # row came from an item whose canonical `id` is a non-empty string equal to its
    # `reddit_id` (`core.normalize` rejects anything else), so the lookup below cannot miss.
    raw_by_id = {
        str(data.get("id")): data for data in (canonicalize(item) for item in prepared.page.items)
    }
    ladder = ctx.settings.static.revisit_ladder_days
    with ctx.engine.begin() as conn:
        # A malformed item must never cost the other 99: the rejects are stored and the page
        # still commits (NM-01).
        rejects = repo.insert_rejects(conn, run_pk=ctx.run_pk, rejects=prepared.rejects, now=now)
        priors = repo.prior_posts(conn, [row.reddit_id for row in prepared.rows])
        decided = [
            _post_write(
                row,
                priors.get(row.reddit_id),
                subreddit_pk=source.pk,
                raw=raw_by_id[row.reddit_id],
                now=now,
                ladder=ladder,
            )
            for row in prepared.rows
        ]
        writes = [write for write, _ in decided]
        scrub_transitions = sum(1 for _, scrub in decided if scrub)
        outcome = repo.upsert_posts(conn, writes, path=IngestPath.SUBREDDIT_NEW)
        post_pks = list(outcome.pks.values())
        source_links = repo.insert_post_sources(
            conn, post_pks=post_pks, source_type=_SOURCE_TYPE, source_pk=source.pk, now=now
        )
        snapshots = repo.insert_item_snapshots(conn, _snapshots(writes, priors, outcome.pks, now))
        authors = _author_writes(prepared.rows)
        repo.upsert_authors(conn, authors)
        repo.recount_authors(conn, [author.author_fullname for author in authors])
        repo.upsert_run_subreddit(
            conn,
            run_pk=ctx.run_pk,
            subreddit_pk=source.pk,
            progress=replace(
                progress_before,
                items_seen=progress_before.items_seen + prepared.slots,
                new_items=progress_before.new_items + len(outcome.new_ids),
                updated_items=progress_before.updated_items + len(outcome.updated_ids),
            ),
        )
    return PageWriteResult(
        items_seen=prepared.slots,
        new_posts=len(outcome.new_ids),
        updated_posts=len(outcome.updated_ids),
        rejects=rejects,
        snapshots=snapshots,
        source_links=source_links,
        unknown_enum_keys=prepared.unknown_enum_keys,
        scrub_transitions=scrub_transitions,
    )


# --- per-source failures and the terminal transaction (§6.3, §6.5) --------------------------


def _classify_failure(exc: Exception, source: repo.SubredditRow) -> SubredditFailure:
    """The §8 table as a pure function: no DB, no notifier, no clock.

    ``source`` is accepted so the signature reads as a per-source decision and so the caller
    never has to thread the row separately; today the mapping is a property of the exception
    alone, which is what makes :data:`_FAILURE_TABLE` assertable against
    ``db.schema.SUBREDDIT_STATUSES`` on its own (round5-findings.json,
    ``P2-stop-reasons-pinned``).
    """
    del source
    status, disable_at, notify = _FAILURE_TABLE.get(type(exc), _DEFAULT_FAILURE)
    return SubredditFailure(
        status=status,
        message=f"{type(exc).__name__}: {exc}",
        disable_at=disable_at,
        notify=notify,
    )


def _coverage_proven(stop_reason: StopReason, source: repo.SubredditRow, *, gap: bool) -> bool:
    """Did THIS sweep prove it reached known territory, i.e. may ``last_complete_poll_at`` be
    stamped? (§6.5, round-5 P1-4.)

    ``EXHAUSTED`` always did -- including an empty or sticky-only listing, where coverage of
    nothing is still complete coverage. ``CAP`` did only when there WAS known territory to
    reach (``watermark_created_utc IS NOT NULL``) and the window reached it (``not gap``): a
    FIRST capped sweep proves nothing, because ``core.paging.gap_suspected`` returns False for
    a NULL watermark by contract, so ``not gap`` alone would claim coverage over a listing
    truncated at 1,000 items.
    """
    if stop_reason is StopReason.EXHAUSTED:
        return True
    return stop_reason is StopReason.CAP and source.watermark_created_utc is not None and not gap


def _finish_subreddit(
    ctx: RunContext,
    source: repo.SubredditRow,
    outcome: _LoopOutcome,
    *,
    failure: SubredditFailure | None,
) -> _FinishResult:
    """ONE transaction (T6): the TERMINAL ``run_subreddits`` row plus that subreddit's status,
    watermark, coverage, gap and identity writes.

    One transaction deliberately. Separate ones leave either ``status='ok'`` with
    ``stop_reason=NULL`` (freshness says the source was never fetched, so the run goes amber
    for no reason) or ``stop_reason='exhausted'`` with ``status='forbidden'`` (SS-06 says the
    source never recovered while freshness says it is fine). A source's outcome and its
    status are two halves of one claim and must commit or roll back together.

    TOTAL: it either commits and returns what it did, or it raises. The caller owns what a
    failed transaction means (§6.3, round-5 P0).
    """
    now = ctx.clock.now()
    stop_reason = StopReason.ERROR if failure is not None else outcome.stop_reason
    with ctx.engine.begin() as conn:
        repo.upsert_run_subreddit(
            conn,
            run_pk=ctx.run_pk,
            subreddit_pk=source.pk,
            progress=repo.SweepProgress(
                pages=outcome.pages_fetched,
                items_seen=outcome.state.items_seen,
                new_items=outcome.new_items,
                updated_items=outcome.updated_items,
                stop_reason=None if stop_reason is None else str(stop_reason),
                error=None if failure is None else failure.message,
            ),
        )
        if failure is not None:
            # `record_subreddit_failure` returns (consecutive_failures, DISABLED) -- §5.2 and
            # the repo docstring, both verified against the shipped function. §6.3's snippet
            # names the second value `enabled` and then negates it, which would report every
            # still-enabled source as disabled; §5.2's contract is the one that holds.
            failures, disabled = repo.record_subreddit_failure(
                conn,
                subreddit_pk=source.pk,
                status=failure.status,
                error=failure.message,
                now=now,
                disable_at=failure.disable_at,
            )
            return _FinishResult(
                status=failure.status,
                consecutive_failures=failures,
                disabled=disabled,
                gap_suspected=False,
                stop_reason=stop_reason,
            )

        # ---- success paths (§6.5) ----
        if outcome.observed_subreddit_id is not None and source.subreddit_id is None:
            repo.set_subreddit_identity(
                conn, subreddit_pk=source.pk, subreddit_id=outcome.observed_subreddit_id
            )
        gap = outcome.stop_reason is StopReason.CAP and gap_suspected(
            outcome.state.seen_min_created_utc, source.watermark_created_utc
        )
        if outcome.stop_reason in {StopReason.EXHAUSTED, StopReason.CAP}:
            repo.advance_watermark(
                conn,
                subreddit_pk=source.pk,
                seen_max_created_utc=outcome.state.seen_max_created_utc,
            )
            if _coverage_proven(outcome.stop_reason, source, gap=gap):
                repo.stamp_complete_poll(conn, subreddit_pk=source.pk, at=now)
            repo.clear_subreddit_error(conn, subreddit_pk=source.pk, now=now)
        if outcome.stop_reason is StopReason.EXHAUSTED:
            repo.set_gap_suspected(conn, subreddit_pk=source.pk, at=None)
        elif gap:
            repo.set_gap_suspected(conn, subreddit_pk=source.pk, at=now)
        return _FinishResult(
            status="ok" if outcome.stop_reason is not None else source.status,
            consecutive_failures=0,
            disabled=False,
            gap_suspected=gap,
            stop_reason=outcome.stop_reason,
        )


def _sweep_row(
    source: repo.SubredditRow,
    outcome: _LoopOutcome,
    failure: SubredditFailure | None,
    finish: _FinishResult | None,
) -> SubredditSweep:
    """Build the public row from the three results.

    ``finish=None`` means *no terminal transaction committed* -- the dry-run early return and
    the failed-T6 handler -- so ``status`` is ``source.status`` (**unchanged**, which is the
    claim the T6 test asserts), ``disabled`` and ``gap_suspected`` are False, and
    ``stop_reason`` is the loop's own, because nothing was written that could have changed
    them. With a committed T6 the row reports what that transaction recorded, which on a
    failure is ``error``.
    """
    return SubredditSweep(
        subreddit_pk=source.pk,
        name_lower=source.name_lower,
        pages=outcome.pages_fetched,
        items_seen=outcome.state.items_seen,
        new_items=outcome.new_items,
        updated_items=outcome.updated_items,
        stop_reason=outcome.stop_reason if finish is None else finish.stop_reason,
        status=source.status if finish is None else finish.status,
        error=None if failure is None else failure.message,
        gap_suspected=finish is not None and finish.gap_suspected,
        disabled=finish is not None and finish.disabled,
    )


def sweep_subreddit(
    ctx: RunContext,
    source: repo.SubredditRow,
    *,
    gateway: RedditGateway,
    notifier: Notifier,
) -> SubredditSweep:
    """Page one subreddit, then close it out: the terminal transaction and the announcements
    that transaction earned (§6.3).

    The per-source failure warning is recorded **above** the dry-run branch
    (round5-findings.json, ``P1-dry-run-swallows-failures``): a 403 is a fact about the fetch,
    which a dry run really did perform, so ``run --dry-run`` must exit 3 rather than reporting
    a clean ``ok``. Everything a *commit* earns -- the notification, the disable, the gap --
    still follows the commit.
    """
    outcome, exc = _page_loop(ctx, source, gateway=gateway)
    failure = None if exc is None else _classify_failure(exc, source)
    if failure is not None:
        ctx.warn("subreddit_error", f"r/{source.display_name}: {failure.message}")

    if ctx.dry_run:  # no engine write of any kind, and no notification either (§11.4)
        return _sweep_row(source, outcome, failure, finish=None)

    try:
        finish = _finish_subreddit(ctx, source, outcome, failure=failure)  # T6 commits here
    except (OperationalError, IntegrityError) as db_exc:  # NOT `exc`: that name is the loop's
        # A locked terminal transaction, or a status / stop_reason the CHECK constraints
        # reject, must cost this SOURCE and not the run: the last per-page progress row
        # stands with stop_reason NULL (interrupted, §19.4), the source's status is
        # unchanged, and the loop moves on. Without this the exception reaches `sweep_all`,
        # where both classes are `DatabaseError` subclasses and would be reported to the
        # operator as database corruption (§6.8).
        ctx.warn(
            "subreddit_finish_failed",
            f"r/{source.display_name}: terminal transaction failed: {db_exc}",
        )
        return _sweep_row(source, outcome, failure, finish=None)

    # --- everything below runs AFTER the commit, so nothing is announced that did not happen
    if failure is not None and failure.notify:
        notifier.notify("error", f"r/{source.display_name}: {failure.message}")
    if finish.disabled:
        ctx.warn(
            "source_auto_disabled",
            f"r/{source.display_name}: disabled after {finish.consecutive_failures} "
            f"consecutive {finish.status} results",
        )
        notifier.notify("error", f"r/{source.display_name} left collection: {finish.status}")
    if finish.gap_suspected:
        ctx.warn("gap_suspected", f"r/{source.display_name}: cap reached above the watermark")
    return _sweep_row(source, outcome, failure, finish)


# --- fetching: the retry ladder, the preflight, and the one catch site (§6.7, §6.8) ---------


def fetch_page(
    ctx: RunContext,
    *,
    gateway: RedditGateway,
    name: str,
    after: str | None,
    policy: RetryPolicy,
) -> Page:
    """One page, with the transient ladder and the 429 rule around it.

    The one-retry rule for 429 is deliberate: a second 429 on the same page means Reddit is
    not honouring the window, and the run ends ``rate_limited`` (exit 4) rather than burning
    the wall-clock ceiling. ``HtmlBlocked`` is converted here, so ``_page_loop``'s
    ``except GatewayError`` can never swallow a run-level abort (§6.2 note 7).
    """
    attempt = 1
    rate_limited_once_already = False
    while True:
        try:
            return next(iter(gateway.iter_new_pages(name, max_pages=PAGES_PER_CALL, after=after)))
        except RateLimited as exc:
            wait = plan_rate_limit_wait(exc.retry_after, ctx.remaining_ceiling_seconds)
            if not wait.should_wait:
                raise RunTerminalError(RunStatus.RATE_LIMITED, detail=str(exc)) from exc
            runs.heartbeat(ctx, stage=wait.stage)  # written BEFORE the sleep (§12.4)
            ctx.clock.sleep(wait.seconds)
            if rate_limited_once_already:
                raise RunTerminalError(RunStatus.RATE_LIMITED, detail=str(exc)) from exc
            rate_limited_once_already = True
        except HtmlBlocked as exc:
            raise RunTerminalError(RunStatus.FAILED, detail=f"html 403: {exc}") from exc
        except GatewayError as exc:
            outcome = classify(exc)
            if outcome is Outcome.AUTH:
                raise RunTerminalError(
                    RunStatus.FAILED, detail=f"auth: {exc}", exit_code=ExitCode.CONFIG
                ) from exc
            if outcome not in {Outcome.TRANSIENT, Outcome.NETWORK_DOWN}:
                raise  # per-source fatal; `_page_loop` handles it
            delay = policy.next_delay(attempt)
            if delay is None:
                if outcome is Outcome.NETWORK_DOWN:
                    raise RunTerminalError(RunStatus.NETWORK, detail=str(exc)) from exc
                raise  # transient give-up: this subreddit only
            runs.heartbeat(ctx, stage=f"retry:{name}:{int(delay)}s")
            ctx.clock.sleep(delay)
            attempt += 1
        finally:
            runs.sync_budget(ctx, gateway)  # §6.6: a give-up, a 429, a 403 and a crash all pay


def preflight(ctx: RunContext, *, gateway: RedditGateway, source: repo.SubredditRow) -> None:
    """One ``about()`` call per run on the first enabled source: the cheap auth ping that makes
    ``AuthFailed`` and ``HtmlBlocked`` surface before any paging (§6.7).

    Nothing is swallowed silently: two branches return after recording a ``RunWarning`` (so
    the run is ``partial``, never ``ok``); the per-source 4xx branch returns with a written
    reason, because that source's own sweep sets its status a moment later; the rest re-raise.
    The transient ladder is deliberately **not** run here -- paying 450 s at the ping and then
    again per source is how a transient outage turns into a wall-clock ceiling.

    The ping does not write ``subreddits``: ``subreddit_type`` / ``subscribers`` / ``over18``
    land with the PRAW adapter in tranche B.
    """
    try:
        gateway.about(source.name_lower)
    except AuthFailed as exc:
        raise RunTerminalError(
            RunStatus.FAILED, detail=f"auth: {exc}", exit_code=ExitCode.CONFIG
        ) from exc
    except HtmlBlocked as exc:
        raise RunTerminalError(RunStatus.FAILED, detail=f"html 403: {exc}") from exc
    except RateLimited as exc:
        raise RunTerminalError(RunStatus.RATE_LIMITED, detail=str(exc)) from exc
    except (SubredditForbidden, SubredditNotFound, SubredditRedirected, SubredditQuarantined):
        # A per-source 403/404/3xx proves the credentials work. This source's own sweep sets
        # its status a moment later (§6.3), so there is nothing to record here.
        return
    except TransientError as exc:
        ctx.warn("preflight_transient", f"auth ping to r/{source.display_name} failed: {exc}")
        return
    except GatewayError as exc:
        if classify(exc) is Outcome.NETWORK_DOWN:
            raise RunTerminalError(RunStatus.NETWORK, detail=str(exc)) from exc
        ctx.warn("preflight_error", f"auth ping to r/{source.display_name} failed: {exc}")
        return
    finally:
        runs.sync_budget(ctx, gateway)  # §6.6


def _enabled_sources(ctx: RunContext) -> list[repo.SubredditRow]:
    """The run's source list.

    A ``DatabaseError`` HERE is a run-level failure with a message rather than a traceback:
    nothing has been swept yet, so ``failed`` with ``error="database: ..."`` is the honest
    record. Its own function so the ``raise`` is not a raise-inside-a-try (ruff TRY301).
    """
    try:
        with ctx.engine.connect() as conn:
            return repo.enabled_subreddits(conn, repo.default_workspace_pk(conn))
    except DatabaseError as exc:
        raise RunTerminalError(RunStatus.FAILED, detail=f"database: {exc}") from exc


def sweep_all(ctx: RunContext, *, gateway: RedditGateway, notifier: Notifier) -> SweepResult:
    """Sweep every enabled source, and be the ONE catch site for ``RunTerminalError`` (§6.8).

    Clause order below is load-bearing and ruff will not save anyone who reverses it:
    ``except DatabaseError`` placed first would catch ``OperationalError`` and
    ``IntegrityError`` too and re-create the round-4 defect -- lock contention reported to
    the operator as database corruption, with the remaining sources never swept.
    ``tests/services/test_sweep_errors.py::test_a_locked_terminal_transaction_warns_and_leaves_the_run_partial``
    is the test that goes red if it is.

    This function **returns**, never re-raises a terminal status: ``collect`` finishes the run
    row from ``SweepResult``, and work already committed by earlier subreddits stays committed.
    """
    sweeps: list[SubredditSweep] = []
    try:
        sources = _enabled_sources(ctx)  # a locked/unreadable DB fails the run cleanly
        if sources:
            preflight(ctx, gateway=gateway, source=sources[0])
        for source in sources:
            if ctx.over_ceiling or not ctx.budget.can_afford(1):
                ctx.warn("run_budget_or_ceiling", f"stopped before r/{source.display_name}")
                break
            sweeps.append(sweep_subreddit(ctx, source, gateway=gateway, notifier=notifier))
    except RunTerminalError as exc:
        return SweepResult(tuple(sweeps), exc.status, exc.detail, exc.exit_code)
    except (OperationalError, IntegrityError):
        # Handled everywhere they can legitimately arise: inside the page loop (§6.2), around
        # T6 (§6.3) and around the source read above. Arriving here means a call site outside
        # all three -- today only `runs.heartbeat`, which sits outside the loop's handlers on
        # purpose (§6.2 note 8), because a run row this process cannot write is not a
        # per-source problem. Reporting it as corruption would be a lie, so it propagates: the
        # row is left `running` and the next run stamps it `crashed` (§8's last row, §12.2).
        raise
    except DatabaseError as exc:
        # Corruption / disk I/O ONLY. The clause above is what makes that claim true.
        return SweepResult(tuple(sweeps), RunStatus.FAILED, f"database: {exc}", None)
    return SweepResult(tuple(sweeps), None, None, None)
