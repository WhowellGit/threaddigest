# Incident record: a renumbered known-issue id left three citations behind (2026-09-17)

**Scope.** `807b27b`, which corrected three citations: the plan's collector step, the docstring on
the revisit-queue read in `db/repo.py`, and the query-plan test that asserts the ordering. The
repository layer is a review-required surface, which is why this record exists. No behaviour
changed; the commit rewrote one identifier in three places.

**What happened.** Two agents working in separate git worktrees on 2026-09-17 each appended a
known-issues row and each claimed the next free id, because neither could see the other's
uncommitted tree. One claimed it for a rate limit arriving in the HTTP-date form, the other for
the revisit queue draining oldest thread first. The main session renumbered the second when its
branch landed, moving the row in `docs/runbook/KNOWN_ISSUES.md` and the citation in
`docs/decisions/DECISIONS.md` that the register gate's failure had pointed at, and stopped there
because `make check` then passed. Three other citations still named the id that now belongs to the
rate limit, so each pointed a reader at the wrong incident: the plan's step 2, the docstring that
explains why the queue is ordered as it is, and the test that asserts that ordering.

**How it was found.** A later agent quoted the docstring back in its report and the id did not
match what the sentence described. Not a gate and not a test: a reading. The two places that were
corrected first were exactly the two a gate had named, which is what made the incomplete sweep
feel finished.

**Why no gate caught it.** The register gate checks that a row's cited commits resolve; the
known-issues gate checks that a row cites a test that exists. Neither can check that a citation
points at the row whose subject matches, and no cheap mechanical check can: the id existed, the
row existed, and only the meaning was wrong. This is the failure mode the working agreement names
as "every mirror in the same change", and the renumber was treated as a two-file edit rather than
as a mirrors sweep.

**What this record does not claim.** That the underlying collision is fixed. Three collisions
happened on 2026-09-17, all from parallel worktrees claiming the same id, and this record covers
only the citations left behind by one of the renumbers. The enforceable remedies are a tool that
performs a renumber as one pass over every citation in the tracked tree, refusing an id already in
use, and — the cheaper prevention — assigning the id when the work lands rather than while it is
being written. Both are queued; neither is built, and until the first exists a renumber remains a
hand sweep with this record as its warning.

**How reviewed.** In-family, the main session, which made the error and the correction; not an
independent seat, which is this record's weakness. Three things were checked rather than assumed:
that each of the three corrected citations describes the queue ordering rather than the rate limit,
read in context; that no fourth citation of the old id in those files remained; and that the
citations which legitimately name the rate limit, in the adapter, its tests, the decisions entry,
the status page and the test strategy, were left alone.
