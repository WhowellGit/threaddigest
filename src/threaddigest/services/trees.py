"""Step 2 of the collector algorithm: the comment trees of the posts the ladder makes due
(M1b design memo § C; docs/PLAN.md § Collector algorithm step 2).

The stage sits between two landed halves -- ``core/trees.py`` plans one fetch and
``db/repo.py`` writes one tree -- and adds only what needs the world: the queue, the budget,
the retry ladder and the transaction boundary. Four rules decide almost everything here:

* **One transaction per tree, and it bounds the write, not the fetch.** Everything one tree
  leaves behind -- its comments, its authors, the stubs it could not expand, the stamp on its
  post -- commits together or not at all (memo § C.6). When a bound stops expansion
  *mid-tree*, what was already paid for is still committed, with the unexpanded stubs
  recorded and ``more_skipped_reason`` naming the bound: discarding fetched comments would
  spend requests for nothing, and the rows are honest (§ C.4).
* **Counters are folded from a committed result, never before it.** :func:`_commit` mutates
  no counter; if its :class:`TreeWriteResult` does not reach the caller, nothing was
  committed and nothing may be counted. ``comments_new`` is tied to the ``comments`` table's
  delta by a FAILURE invariant, so a counter raised before the commit reports the collector
  as broken on what is really lock contention (P0-2, and finding A9's qualification of it:
  the rule is about counters folded from a write's result).
* **The budget is the gateway's own counter, never local arithmetic.**
  ``runs.sync_budget`` is called at the top of every post and inside the ladder, because the
  reserve exists for the requests this stage never planned -- prawcore's retries and token
  refreshes (memo § E.2). The hard cap bounds the limit on construction, so no flag and no
  path can spend past it (N-06).
* **The ladder derives from ``created_utc``, and only a fetch that succeeded advances it.**
  A post whose tree failed transiently stays due, so the next run retries it; a post with no
  comments at all still advances, or the queue never drains (§ C.2).

What this stage deliberately does **not** write: the refreshed post a tree fetch returns.
``OWNERSHIP[("posts", COMMENTS)]`` owns the eight coverage and ladder columns and nothing
else, so the post's own numbers stay the sweep's to record.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Final, Literal

from sqlalchemy.exc import IntegrityError, OperationalError

from threaddigest.core.milestones import next_check
from threaddigest.core.models import CommentRow, Reject
from threaddigest.core.normalize import canonicalize, normalize_comment
from threaddigest.core.retry import RetryPolicy, RunStatus
from threaddigest.core.trees import TreePlan, flatten, is_complete, plan_fetch, stop_reason
from threaddigest.db import repo
from threaddigest.db.ownership import IngestPath
from threaddigest.ports import GatewayError, MoreStub, RedditGateway, TreeResult
from threaddigest.services import runs
from threaddigest.services.runs import RunContext, RunTerminalError
from threaddigest.settings import Settings

__all__ = [
    "PreparedTree",
    "TreeOutcome",
    "TreeStageResult",
    "TreeWriteResult",
    "collect_trees",
]

#: ``comments.source`` for everything this module writes, and the ``source`` argument
#: ``core.normalize.normalize_comment`` records on the row. Spelled from the ownership
#: declaration so the value the upsert is generated for and the value written cannot drift.
_INGEST_SOURCE: Final = IngestPath.COMMENTS.value

#: Why the stage stopped before the queue was empty. ``None`` means it drained.
StageStop = Literal["budget", "ceiling", "dry_run"]

#: The budget stopped tree work: it bound one tree's expansion, or it left nothing for the
#: next tree. Recorded once per run, with the first occurrence's detail (see :func:`_warn_once`).
WARN_BUDGET: Final = "tree_budget_exhausted"
#: One post's tree could not be fetched: the ladder was exhausted, or the failure was fatal
#: for that post. One per post, with its id in the detail, so the operator knows what is due.
WARN_FETCH_FAILED: Final = "tree_fetch_failed"
#: One post's tree was fetched but its transaction was refused. One per post, for the sweep's
#: reason (``subreddit_finish_failed``): a caught database error is recorded, never swallowed.
WARN_WRITE_FAILED: Final = "tree_write_failed"
#: A per-post bound (the expansion cap or the replace-more limit) left a tree incomplete.
#: Recorded once per run: a backfill of a thousand trees must not write a thousand warnings
#: into ``warnings_json``, and the per-tree record is the post's own ``more_skipped_reason``.
WARN_INCOMPLETE: Final = "tree_incomplete_cap"


@dataclass(frozen=True, slots=True)
class TreeOutcome:
    """What one post's tree attempt did, as ``collect`` and the CLI summary read it.

    ``skipped`` is a post with no comments (no request spent); ``error`` is set when the
    fetch or the write failed, in which case the post is still due. ``captured`` is the
    comments **this fetch** wrote, which is what ``posts.comments_captured`` records.
    """

    post_pk: int
    reddit_id: str
    skipped: bool
    captured: int
    complete: bool
    more_stubs: int
    more_skipped_reason: str | None
    error: str | None


@dataclass(frozen=True, slots=True)
class TreeStageResult:
    """Every tree's outcome, why the stage stopped, and the terminal state when the whole run
    must end -- the shape :class:`~threaddigest.services.sweep.SweepResult` has, so ``collect``
    reads both stages the same way.
    """

    trees: tuple[TreeOutcome, ...]
    #: Posts read from the due queue this stage, i.e. the denominator of what it harvested.
    queued: int
    stop_reason: StageStop | None
    terminal_status: RunStatus | None
    terminal_error: str | None
    #: 78 for an ``AuthFailed`` (§9); None means ``core.retry.exit_code`` applies.
    exit_code_override: int | None


@dataclass(frozen=True, slots=True)
class PreparedTree:
    """One fetched tree after normalization and **before** any database access.

    Pure: built by :func:`_prepare_tree` from a ``ports.TreeResult`` with no connection, no
    clock and no settings, so it is unit-testable on its own and so the write never sees a
    raw wire dict. ``rejects`` are the items ``core.normalize`` refused, which are stored and
    counted rather than dropped (NM-01): a malformed comment must never cost the other 99.
    """

    writes: tuple[repo.CommentWrite, ...]
    rejects: tuple[Reject, ...]
    stubs: tuple[repo.MoreWrite, ...]
    authors: tuple[repo.AuthorWrite, ...]
    complete: bool

    @property
    def captured(self) -> int:
        """Comments this fetch wrote, for ``posts.comments_captured``."""
        return len(self.writes)

    @property
    def more_skipped_count(self) -> int:
        """Comments left behind the unexpanded stubs (the sum of their counts, per the DDL)."""
        return sum(stub.count for stub in self.stubs)


@dataclass(frozen=True, slots=True)
class TreeWriteResult:
    """What one COMMITTED tree changed. Folded into ``Counters`` by :func:`_fold` (P0-2)."""

    new_comments: int
    updated_comments: int
    rejects: int
    stubs: int
    captured: int
    complete: bool


# --- the queue and the ladder ----------------------------------------------------------------


def _queue_limit(ctx: RunContext, limit: int | None) -> int:
    """How many due posts to read: what the budget can afford, plus one.

    Every tree costs at least its own base request, so ``spendable`` bounds the trees this
    run can fetch. The extra row is what lets the stage tell a *drained* queue from a
    *truncated* one, and therefore whether to warn: without it, a budget that stopped the
    stage exactly at the end of the rows it read would look like a queue that ran out.
    """
    affordable = ctx.budget.spendable + 1
    return affordable if limit is None else max(min(limit, affordable), 0)


def _ladder(due: repo.DuePost, ladder_days: Sequence[int]) -> tuple[int, int]:
    """The ``(next_check_at, check_stage)`` a completed check leaves on its post.

    ``posts.check_stage`` counts the checks performed and ``next_check_at`` is the rung that
    count schedules -- the invariant the sweep's insert establishes (``sweep._post_write``
    writes stage 0 with rung 0 pending, deliberately not stage 1). A check performed at
    ``check_stage`` therefore leaves ``check_stage + 1`` checks done and rung
    ``check_stage + 1`` pending. The increment is ``next_check``'s own ``next_stage`` rather
    than arithmetic here, and the timestamp is that new stage's rung: taking both from one
    call would re-schedule the rung just checked, leaving ``next_check_at`` where it already
    was (memo § C.2 reads that way, and this is the resolution).

    Past the last rung ``core.milestones.next_check`` keeps climbing, so the result is always
    a real timestamp and never a far-future sentinel.
    """
    _rung_just_checked, next_stage = next_check(due.created_utc, due.check_stage, ladder_days)
    next_check_at, _following = next_check(due.created_utc, next_stage, ladder_days)
    return next_check_at, next_stage


def _warn_once(ctx: RunContext, name: str, detail: str) -> None:
    """Record ``name`` unless the run already carries it, keeping the first detail.

    The three stage-level warnings are facts about the *run* -- the budget ran out, a bound
    left trees incomplete, the ceiling was reached -- and a backfill of a thousand trees
    would otherwise write a thousand rows into ``warnings_json``, which every heartbeat
    re-writes. One warning still makes the run ``partial``, which is the whole signal; which
    trees it was is on their own posts, in ``more_skipped_reason``.
    """
    if not any(warning.name == name for warning in ctx.warnings):
        ctx.warn(name, detail)


# --- normalization, pure ---------------------------------------------------------------------


def _authors(rows: Sequence[CommentRow]) -> list[repo.AuthorWrite]:
    """Identity rows for the tree's commenters, keyed on the newest comment each appears on.

    A comment whose author Reddit shows as ``[deleted]`` carries neither a name nor a
    fullname, so it contributes no ``authors`` row: the account's identity is exactly what is
    no longer knowable. ``services/sweep.py::_author_writes`` does the same for a page's
    posts; the two are not one function because a shared one would need a structural protocol
    over two pydantic models and a home neither module owns. The third caller (reconcile, at
    M1c) is the moment to extract it.
    """
    newest: dict[str, repo.AuthorWrite] = {}
    for row in sorted(rows, key=lambda comment: comment.created_utc):
        if row.author is not None and row.author_fullname is not None:
            newest[row.author_fullname] = repo.AuthorWrite(
                author_fullname=row.author_fullname, name=row.author, seen_at=row.created_utc
            )
    return list(newest.values())


def _raw_json(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), default=str)


def _stub_writes(stubs: Sequence[MoreStub]) -> tuple[repo.MoreWrite, ...]:
    """The port's stubs as rows. ``count`` is Reddit's own count of what is hidden, not the
    length of ``children``, and a split stub's parts sum to the whole (KI-043)."""
    return tuple(
        repo.MoreWrite(parent_fullname=stub.parent_fullname, count=stub.count) for stub in stubs
    )


def _prepare_tree(result: TreeResult, *, post_pk: int, reddit_id: str) -> PreparedTree:
    """Normalize one fetched tree. No DB, no clock, no settings.

    ``core.trees.flatten`` puts every parent before its children, rebuilt from the items'
    own ``parent_id`` rather than trusted as delivered, so the write order is the tree's
    order whatever the gateway did. ``normalize_comment`` never raises -- its guard turns any
    failure into a ``Reject`` -- so this function is total and a wire-shape change can never
    take a run down.
    """
    writes: list[repo.CommentWrite] = []
    rejects: list[Reject] = []
    rows: list[CommentRow] = []
    for item in flatten(result):
        row = normalize_comment(item, source=_INGEST_SOURCE, post_reddit_id=reddit_id)
        if isinstance(row, Reject):
            rejects.append(row)
            continue
        rows.append(row)
        writes.append(
            repo.CommentWrite(row=row, post_pk=post_pk, raw_json=_raw_json(canonicalize(item)))
        )
    return PreparedTree(
        writes=tuple(writes),
        rejects=tuple(rejects),
        stubs=_stub_writes(result.more),
        authors=tuple(_authors(rows)),
        complete=is_complete(result),
    )


# --- one tree's transaction ------------------------------------------------------------------


def _commit(
    ctx: RunContext, due: repo.DuePost, prepared: PreparedTree, stamp: repo.TreeStamp
) -> TreeWriteResult:
    """One tree, ONE transaction: the rejects, the comments and their parents, the stubs, the
    authors and their counts, and the stamp on the post -- all of it or none of it (§7).

    **Mutates no counter and no ``ctx`` state** (P0-2). The order inside is load-bearing in
    one place: ``recount_authors`` recomputes from the ``comments`` table, so it must follow
    the upsert that wrote the rows it counts.

    The deletion decision is not taken here. ``repo.comment_values`` makes it against the
    prior row it has to read anyway, and the statement's own ``SET`` clause holds the content
    of a comment already ``deleted_by_author`` whatever this write passes
    (``docs/reference/reviews/2026-09-17-m1b-comment-writes.md``), so no tree re-fetch can
    write a body back over a deletion the store has honoured.
    """
    now = ctx.clock.now()
    with ctx.engine.begin() as conn:
        rejects = repo.insert_rejects(conn, run_pk=ctx.run_pk, rejects=prepared.rejects, now=now)
        outcome = repo.upsert_comments(conn, prepared.writes, now=now)
        stubs = repo.replace_comment_more(conn, post_pk=due.pk, stubs=prepared.stubs)
        repo.upsert_authors(conn, prepared.authors, path=IngestPath.COMMENTS)
        repo.recount_authors(conn, [author.author_fullname for author in prepared.authors])
        repo.stamp_tree_on_post(conn, post_pk=due.pk, stamp=stamp)
    return TreeWriteResult(
        new_comments=len(outcome.new_ids),
        updated_comments=len(outcome.updated_ids),
        rejects=rejects,
        stubs=stubs,
        captured=prepared.captured,
        complete=prepared.complete,
    )


def _fold(ctx: RunContext, written: TreeWriteResult) -> None:
    """Fold one committed tree into the run's counters, and nothing else (P0-2)."""
    ctx.counters.trees_fetched += 1
    ctx.counters.trees_complete += 1 if written.complete else 0
    ctx.counters.comments_new += written.new_comments
    ctx.counters.comments_updated += written.updated_comments
    ctx.counters.more_stubs += written.stubs
    ctx.counters.rejects += written.rejects


# --- one post ---------------------------------------------------------------------------------


def _skip(ctx: RunContext, due: repo.DuePost, ladder_days: Sequence[int]) -> TreeOutcome:
    """A post Reddit reports with no comments: no request, but the ladder still advances.

    ``comments_fetched_at`` stays NULL and ``comments_complete`` false, because "complete" is
    a claim that a whole tree was read and no tree was read (§ C.3). The skip is counted
    separately, so the digest's coverage denominator is *posts due* and nothing accumulates.
    """
    next_check_at, check_stage = _ladder(due, ladder_days)
    with ctx.engine.begin() as conn:
        repo.stamp_tree_on_post(
            conn,
            post_pk=due.pk,
            stamp=repo.TreeStamp(
                fetched_at=None,
                captured=0,
                complete=False,
                more_skipped=False,
                more_skipped_count=0,
                more_skipped_reason=None,
                next_check_at=next_check_at,
                check_stage=check_stage,
            ),
        )
    ctx.counters.trees_skipped_empty += 1
    return TreeOutcome(
        post_pk=due.pk,
        reddit_id=due.reddit_id,
        skipped=True,
        captured=0,
        complete=False,
        more_stubs=0,
        more_skipped_reason=None,
        error=None,
    )


def _failed(due: repo.DuePost, error: str) -> TreeOutcome:
    """The outcome of a post whose tree was not committed: still due, nothing written."""
    return TreeOutcome(
        post_pk=due.pk,
        reddit_id=due.reddit_id,
        skipped=False,
        captured=0,
        complete=False,
        more_stubs=0,
        more_skipped_reason=None,
        error=error,
    )


def _fetch_tree(
    ctx: RunContext, due: repo.DuePost, *, gateway: RedditGateway, more_limit: int
) -> TreeResult:
    """One tree, on the run's shared retry ladder (``runs.fetch_with_ladder``).

    A rate limit, an auth failure, an HTML block and a network outage that exhausts the
    ladder all leave as ``RunTerminalError``, which :func:`collect_trees` catches once: the
    stage stops rather than hammering a source that has told it to stop. Everything else --
    a transient that exhausts the ladder, or a failure fatal for this post -- is raised as
    itself and costs this post only.
    """
    return runs.fetch_with_ladder(
        ctx,
        lambda: gateway.fetch_tree(due.reddit_id, more_limit=more_limit),
        gateway=gateway,
        label=f"tree:{due.reddit_id}",
        policy=RetryPolicy(),
    )


def _bound_warning(ctx: RunContext, due: repo.DuePost, bound: str | None) -> None:
    """Name the bound that left a tree incomplete, once per run (see :func:`_warn_once`)."""
    if bound is None:
        return
    detail = f"post {due.reddit_id}: expansion stopped by the {bound}"
    if bound == "budget":
        _warn_once(ctx, WARN_BUDGET, detail)
        return
    _warn_once(ctx, WARN_INCOMPLETE, detail)


def _collect_one(
    ctx: RunContext,
    due: repo.DuePost,
    plan: TreePlan,
    *,
    gateway: RedditGateway,
    settings: Settings,
) -> TreeOutcome:
    """Fetch one post's tree and commit it, or record why neither happened.

    ``spendable`` is read once, **before** the fetch, and handed to
    ``core.trees.stop_reason`` with the same two configured bounds
    ``core.trees.more_limit_for`` computed the limit from: naming the bound afterwards from a
    budget this fetch has since spent would blame the budget for a limit's work.
    """
    spendable_before = ctx.budget.spendable
    try:
        result = _fetch_tree(ctx, due, gateway=gateway, more_limit=plan.more_limit)
    except GatewayError as exc:
        # Every caught exception is recorded on the run row; the post keeps its ladder, so
        # it is still due and the next run retries it (§ C.2).
        ctx.warn(WARN_FETCH_FAILED, f"post {due.reddit_id}: {type(exc).__name__}: {exc}")
        return _failed(due, f"{type(exc).__name__}: {exc}")

    prepared = _prepare_tree(result, post_pk=due.pk, reddit_id=due.reddit_id)
    bound = stop_reason(
        result,
        replace_more_limit=settings.static.comments.replace_more_limit,
        per_post_cap=settings.static.comments.per_post_expansion_cap,
        spendable_before=spendable_before,
    )
    next_check_at, check_stage = _ladder(due, settings.static.revisit_ladder_days)
    stamp = repo.TreeStamp(
        fetched_at=ctx.clock.now(),
        captured=prepared.captured,
        complete=prepared.complete,
        more_skipped=bool(prepared.stubs),
        more_skipped_count=prepared.more_skipped_count,
        more_skipped_reason=bound,
        next_check_at=next_check_at,
        check_stage=check_stage,
    )
    try:
        written = _commit(ctx, due, prepared, stamp)
    except (OperationalError, IntegrityError) as exc:
        ctx.warn(WARN_WRITE_FAILED, f"post {due.reddit_id}: transaction refused: {exc}")
        return _failed(due, f"{type(exc).__name__}: {exc}")

    _fold(ctx, written)  # EVERY counter is folded HERE, after the transaction committed
    _bound_warning(ctx, due, bound)
    return TreeOutcome(
        post_pk=due.pk,
        reddit_id=due.reddit_id,
        skipped=False,
        captured=written.captured,
        complete=written.complete,
        more_stubs=written.stubs,
        more_skipped_reason=bound,
        error=None,
    )


# --- the stage --------------------------------------------------------------------------------


def _stopped_before(
    ctx: RunContext, due: repo.DuePost, plan: TreePlan, left: int
) -> StageStop | None:
    """The two boundaries that stop the stage, both recorded so the run is never ``ok``.

    A skip is exempt from the budget: it spends no request, so refusing it would leave a
    post due that costs nothing to retire. The ceiling is not exempt, because it bounds the
    run's wall clock and a stamp is still work. The warning name for the ceiling is the
    sweep's own: one ceiling per run is one fact, and the first stop to reach it keeps the
    detail.
    """
    if ctx.over_ceiling:
        _warn_once(
            ctx,
            "wall_clock_ceiling",
            f"the tree stage stopped before post {due.reddit_id} with {left} due post(s) unread",
        )
        return "ceiling"
    if not plan.skip and not ctx.budget.can_afford(1):
        _warn_once(
            ctx,
            WARN_BUDGET,
            f"the tree stage stopped before post {due.reddit_id} with {left} due post(s) unread",
        )
        return "budget"
    return None


def collect_trees(
    ctx: RunContext,
    *,
    gateway: RedditGateway,
    settings: Settings,
    limit: int | None = None,
) -> TreeStageResult:
    """Drain the due queue newest first, within the budget, one transaction per tree.

    Called after the sweep and before the invariants, so the posts this run discovered are
    already stored and every counter is final before the invariant pass reads it.

    This function **returns**, never re-raises a terminal status: it is the one catch site
    for ``RunTerminalError`` in this stage (the sweep's §6.8 rule), so a rate limit or an
    outage ends the stage with the trees already committed left committed, and ``collect``
    closes the run row from the result.

    ``settings`` is the run's own resolved settings -- the same object ``ctx`` carries -- and
    is taken explicitly because the three values this stage reads from it
    (``comments.replace_more_limit``, ``comments.per_post_expansion_cap``,
    ``revisit_ladder_days``) are the whole of its configuration dependence.
    """
    if ctx.dry_run:
        # A dry run must not write, and a tree fetch that cannot be written is budget spent
        # for nothing -- unlike the sweep, whose dry run is the operator's "does this source
        # read" check (§11.4).
        return TreeStageResult((), 0, "dry_run", None, None, None)
    comments = settings.static.comments
    ladder_days = settings.static.revisit_ladder_days
    runs.sync_budget(ctx, gateway)
    with ctx.engine.connect() as conn:
        queue = repo.due_posts(conn, now=ctx.clock.now(), limit=_queue_limit(ctx, limit))
    outcomes: list[TreeOutcome] = []
    stop: StageStop | None = None
    try:
        for index, due in enumerate(queue):
            runs.heartbeat(ctx, stage=f"trees:{due.reddit_id}")
            runs.sync_budget(ctx, gateway)  # never trust local arithmetic (§ E.2)
            plan = plan_fetch(
                due.num_comments,
                replace_more_limit=comments.replace_more_limit,
                per_post_cap=comments.per_post_expansion_cap,
                spendable=ctx.budget.spendable,
            )
            stop = _stopped_before(ctx, due, plan, len(queue) - index)
            if stop is not None:
                break
            if plan.skip:
                outcomes.append(_skip(ctx, due, ladder_days))
                continue
            outcomes.append(_collect_one(ctx, due, plan, gateway=gateway, settings=settings))
    except RunTerminalError as exc:
        return TreeStageResult(
            tuple(outcomes), len(queue), stop, exc.status, exc.detail, exc.exit_code
        )
    return TreeStageResult(tuple(outcomes), len(queue), stop, None, None, None)
