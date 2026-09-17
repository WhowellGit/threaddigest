# The second CI run, and the gate that was lying on this machine (2026-09-16) — record

Record for commit `737b615`. Surface touched: `tests/gates/` (`test_review_register.py`), which
is review-required. Seat: the session that made the change, under a bounded brief, working from
the failed run's logs and from a fresh clone. That is this record's weakness and it is stated
here rather than implied: no independent seat read it.

## What happened

The first CI run's three fixes landed and the second run went red in one place only, in both the
required job and the portability job: the review-register gate (G50) named six commits on
review-required surfaces with no register row. `make check` was green here on the same tree.

The brief's working hypothesis was that the history rewrite earlier the same day had left the
pre-rewrite commits in this machine's object store as unreachable objects, so register scopes
citing old hashes still resolved here through `git log` while a clone, which never received
those objects, resolved them to nothing. **That hypothesis is refuted.** A fresh single-branch
clone of `main` over `file://` (which negotiates a pack rather than hard-linking the object
store, so the unreachable objects stay behind) runs the gate green. The old hashes are indeed
absent from the clone, and the map carries every citation across the rewrite exactly as it was
built to.

What the clone did reproduce was the CI failure itself, and only with `TZ` set to what the
runner uses. That is the whole finding.

## The defect

The gate asked git for the commits it must police with `git log --since=2026-09-15`. Git's
approximate date parser fills the fields a bare date leaves out from the **current clock**, so
that cutoff means the baseline date *at the hour the suite happens to run*, in whatever timezone
the host is set to. Measured on this machine at 19:13 local:

```
$ git rev-list --count --since=2026-09-15 HEAD
46
$ git rev-list --count --since=2026-09-15T00:00:00-06:00 HEAD
67
$ TZ=UTC git rev-list --count --since=2026-09-15 HEAD
73
```

Three answers to one question. The cutoff slides through the day and moves between machines, so
the set of commits that need a review row was a property of the clock and the host rather than
of the commits. Six commits on `tools/hooks/` and `tests/gates/`, made in the early hours of
2026-09-15, were invisible to the gate here at every hour of every day after they were made, and
visible to a runner six zones away.

The fix reads each commit's own committer date (`%cs`, rendered in the zone the commit records)
and compares two `YYYY-MM-DD` strings. There is no clock in that and no host zone in it either.

## What the defect was hiding

The six commits were not a false alarm. They are the round-one fix panel's work, and the row
that reviewed them writes its scope as `a0d8e8a..HEAD`. A moving reference is not a range end:
the gate's range pattern does not match it, so the row fell back to the bare hash it names and
covered one commit instead of twenty-four. Nothing caught that in 2026-09-15 because the
clock-dependent baseline had already hidden the commits it should have failed over.

The register is append-only, so the row is not edited. A row restating the same panel's scope in
hashes that resolve — `ffa63f1..07bae16`, the same commits after the rewrite — is appended beside
it, carrying the same record and no verdict of its own.

No new guard is needed for the moving reference itself: with the baseline honest, a scope that
names one now leaves its commits uncovered and the gate is red on the spot. An assertion in the
existing control pins that, so the claim is machine-checked rather than argued.

## The third hole, found beside them

A range's two ends are each followed through the rewrite map on their own, so the pairs tried
include the start as written with the end as the rewrite left it. Those two sit on histories with
no commit in common, and `git rev-list` answers such a pair with the whole of the new history —
a row covering every commit before its own start. It is invisible on the machine that ran the
rewrite, because there the pair of old hashes resolves first and answers plausibly; only a
checkout without the pre-rewrite objects can see it. A pair is now a range only when the start is
an ancestor of the end, which is what `first..last` means.

## Evidence

Both new controls were watched red against the unfixed gate before it changed:

```
E           AssertionError: the set of commits needing a row moved with the host timezone UTC0
E           assert ['ceb47bc35b6...ebc69349fc38'] == ['ceb47bc35b6...b795fde6f30d']
E             Left contains one more item: '767586111dcba1fa5aae4d885aa0ebc69349fc38'

E       AssertionError: a row covered a commit that precedes its own start, through an old start
E       paired with a new end
E       assert not True
```

The fixed gate then went red on this machine with exactly the six commits CI had named, which is
the point: the machine stopped lying before anything was made green. `make check` green on the
branch tip, its block pasted in the pull request body, and the gate re-run green in a fresh clone
of the merged result.

## What an independent seat should attack

That appending a row to cover six commits is buying green rather than correcting a record — the
counter-argument is that the review happened, its record has existed since 2026-09-15, and only
the scope's spelling changed. That the ancestor requirement narrows what a range covers and so is
a weakening dressed as a correction. That a gate whose reach depended on the hour was, for two
days, evidence about nothing, and that every other gate reading a date or a commit list deserves
the same reading before it is trusted.
