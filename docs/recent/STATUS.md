# STATUS (prune-stale; rewritten, never appended; capped at about fifty lines)

**As of the night of 2026-09-13.** M0 and M1a tranche A are built, reviewed, and green on `main`; the enforcement tranche landed the same night; the earlier project's material has been assessed, distilled, and pruned to three redacted files plus an archive outside the repo. No GitHub remote yet.

## Green on main
- `make check`: ruff, mypy strict, import-linter, 1,396 tests (923 collected), coverage floor 98.17, ratchets 10 ok, review-only rules ceiling 2, hooks-installed line printed at the end, memory check pending merge.
- The collector runs end to end against the generated fake corpus: `db init` → `run --gateway fake --fixture …` (240 posts) → rerun (0 new, 240 updated, primary keys unchanged) → `doctor --no-network` all ok except credentials not set.
- Gates: layering, network block, data-dir isolation, pragma chokepoint, schema golden, doc currency (G33), retired claims (G34), imported identifiers (G35), trailer refusal (G36), rules name enforcers (G39), register node ids (G40), planted-invariant controls, pk stability, counters-versus-deltas, no-bypass, sqlite confined, no sleep under pytest.

## In flight (branches, then fast-forward into main)
- Health command: no lock file created by a read-only check; stale-alert duration validated on every path; hooks-installed check in the report.
- Memory snapshot and integrity tool (`tools/memory_snapshot.py`, `memory-snapshot/`, `make memory-check`).
- Bookkeeping: test-strategy rows flipped to shipped; guards ledger rows G35/G36/G39/G40 and the empty positive-control cells; issue-register rows for the defects fixed tonight.
- After those merge: install the pre-commit hooks (`make hooks`), strip the attribution trailers from local history before any push, re-render the plan.

## Next
- Tranche B when credentials arrive: the real Reddit adapter probe-first, cassettes, `probe --save-fixture`.
- GitHub repository: push the rewritten history, CI, branch protection, one pull request per step through the review harness.
- M1b (comment trees), M1c (deletion compliance), M1d (themes, digest, schedule, the seven-digest reading week), each as a brief → bounded design rounds → build on a branch → panel.
- The 26 harness answers and the recommendations for the earlier repository (synthesis running); the harness catalogue re-scored from them.

## Waiting on Wes
Reddit credentials; the GitHub repository and its plan; the agent token scope; the pruning pass-one ruling and its three judgement calls (`~/repos/insightminer-desktop-archive/earlier-project/findings/from-build-2026-09-14/prune/removal-list.md` (moved out of the repo folder 2026-09-14 because it quotes the earlier project)); the day-zero items from the harness assessment (suppression statuses now ride with the expiry-date change). Full lists: `docs/decisions/DECISIONS.md` § "Moved from STATUS.md".

## Session hygiene
Sessions start in `~/repos/insightminer`; the single memory home is the repo-keyed directory; the old Desktop-keyed one is a pointer.
