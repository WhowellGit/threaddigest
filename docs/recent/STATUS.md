# STATUS (prune-stale; rewritten, never appended; contract enforced by `tests/gates/test_status_page.py`)

**As of 2026-09-14.** M0 and M1a tranche A are built and green on `main`; the enforcement tranche, the separation pass (the earlier project's residue abstracted or removed from the tree), and the routing, status-page, and ledger-completeness gates have landed. No remote yet: Wes intends a bare git remote on his QNAP as the first backup, GitHub later. Numbers live in the `make check` output, never here.

## In flight
- History rewrite for the earlier project's identifiers in old revisions: bundle taken, callback and verification scripts staged outside the repo; the command awaits Wes (the app's permission classifier refused it). Afterwards: remap cited hashes (`tests/gates/test_known_issues_cite_collected_tests.py` goes red on a dangling one), re-scan, refresh the memory snapshot.
- Harness inventory document with a generated block (shape decided, name and go awaiting Wes).

## Next
1. QNAP bare remote when the server is fixed: add the remote, first push runs `make check` through the pre-push hook, nightly `git bundle` to the same share as a second copy.
2. Tranche B when credentials arrive: the real Reddit adapter probe-first (`probe --save-fixture`), cassettes, the `doctor` auth ping.
3. M1b (comment trees), M1c (deletion compliance), M1d (themes, digest, schedule, the seven-digest reading week): brief → bounded design rounds → build on a branch → panel.
4. Score the first predictions in `docs/learnings/LEARNINGS_TRANSFER.md` §5 at the M1d retrospective.

## Do not undo
- Local history has been rewritten twice (retrospectives, trailers) and a third rewrite is staged; never restore a bundle into `main` without re-running the identifier scan over every commit.
- The memory home is the repo-keyed directory; the Desktop-keyed one holds a pointer only (its stale topic files moved to the archive on 2026-09-14) and `make check` goes red if a second home grows topic files again.
- Sessions start in `~/repos/insightminer`; a session started elsewhere runs without the two hard-block hooks.
- The three redacted retrospectives keep the earlier project's own register ids on purpose; the identifier gate excludes that folder and nothing else.

## Waiting on Wes
Reddit credentials (keys in `.env.example`, pasted into `.env` by Wes); the QNAP remote; running the staged history rewrite; the pruning pass-one ruling (the list now lives in the archive folder outside the repo); suppression statuses and review dates; the harness document's name; a third hard-block hook (read-before-touch) against the two-hook cut N-16; whether to move this project's session transcripts into the archive. Details and recommendations: `docs/decisions/DECISIONS.md` § 2026-09-14.
