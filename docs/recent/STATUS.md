# STATUS (prune-stale; rewritten, never appended; contract enforced by `tests/gates/test_status_page.py`)

**As of 2026-09-14.** M0 and M1a tranche A are built and green on `main`; the enforcement tranche, the separation pass (the earlier project's residue abstracted or removed from the tree), and the routing, status-page, and ledger-completeness gates have landed. No remote yet: Wes intends a bare git remote on his QNAP as the first backup, GitHub later. Numbers live in the `make check` output, never here.

## In flight
- The third hook (read before touch) is built and tested, log-first; its registration in the hook settings is a human edit pending Wes. Nothing on the collector; the next code is tranche B (needs credentials).
- Harness inventory document with a generated block (shape decided, name and go awaiting Wes).

## Next
1. QNAP bare remote when the server is fixed: add the remote, first push runs `make check` through the pre-push hook, nightly `git bundle` to the same share as a second copy.
2. Tranche B when credentials arrive: the real Reddit adapter probe-first (`probe --save-fixture`), cassettes, the `doctor` auth ping.
3. M1b (comment trees), M1c (deletion compliance), M1d (themes, digest, schedule, the seven-digest reading week): brief → bounded design rounds → build on a branch → panel.
4. Milestone MB when the new QNAP arrives: bare repository over SSH, first push through the pre-push hook, nightly bundle, restore drill from the NAS copy.
5. The review runner and the first external review at tranche B's design freeze; the last two days' enforcement changes are that review's first job.
6. Score the first predictions in `docs/learnings/LEARNINGS_TRANSFER.md` §5 at the M1d retrospective.

## Do not undo
- Local history has been rewritten three times (retrospectives, trailers, identifiers; Wes ran the third on 2026-09-14 and the whole-history scan is clean outside the redacted retrospectives); never restore a bundle into `main` without re-running that scan, and never push a bundle's history anywhere.
- The memory home is the repo-keyed directory; the Desktop-keyed one holds a pointer only (its stale topic files moved to the archive on 2026-09-14) and `make check` goes red if a second home grows topic files again.
- Sessions start in `~/repos/insightminer`; a session started elsewhere runs without the two hard-block hooks.
- The three redacted retrospectives keep the earlier project's own register ids on purpose; the identifier gate excludes that folder and nothing else.
- The read-before-touch hook stays in `log` mode until its ledger is reviewed on 2026-09-28; flipping the mode is a reviewed commit, never a hand edit.

## Waiting on Wes
Reddit credentials (keys in `.env.example`, pasted into `.env` by Wes); the QNAP remote; the pruning pass-one ruling (the list now lives in the archive folder outside the repo); registering the third hook in the hook settings (snippet in `docs/decisions/DECISIONS.md` § 2026-09-14 (later)); the harness document's name; the ChatGPT data-controls opt-out before the first external packet; moving this session's transcript to the archive after it ends (command in the archive folder's README). Details and recommendations: `docs/decisions/DECISIONS.md` § 2026-09-14.
