# Known issues — fixed bugs and their regression tests

> Policy (plan § Reference corpus, working agreement): every bug fix starts with a failing test, and every fixed bug lands one row here pointing at that test. The `Regression test` column must resolve to a collected pytest node id; the doc-currency test checks it. Rows are never deleted; a regressed issue gets a new row citing the old id. Open issues that have no fix yet may be listed with status `open` and an empty test column until the failing test exists.
>
> Status vocabulary: `open` (reproduced, no fix), `fixed` (test green on `main`), `regressed` (re-opened; cite the new row), `wontfix` (reason in root cause).

| ID | Date | Symptom | Root cause | Regression test (node id) | Status |
|---|---|---|---|---|---|
| KI-001 | 2026-09-13 | A fresh clone's `make check` printed green while `dmypy` type-checked the *original* repo | `.dmypy.json` (daemon state holding the original tree's absolute path) was tracked in git, so the fresh clone's daemon attached to the wrong tree | tests/gates/test_no_tracked_daemon_state.py::test_dmypy_state_is_not_tracked_and_is_ignored | fixed |

<!-- Format example (do not count as a row):
| KI-0XX | 2026-10-01 | Post page 500 on a scrubbed post with no permalink | template built the deep link from `permalink` instead of `reddit_id` | tests/web/test_post_page.py::test_tombstone_deep_link_uses_id | fixed |
-->

## Swept: investigated, no issue found

A suspicion investigated and found not to be a bug is recorded here with how it was checked, so no later session re-investigates it (practice carried from the earlier project, 2026-09-13).

| Date | Question | How verified | Answer |
|---|---|---|---|
| 2026-09-13 | Does any code reference the per-run JSONL sidecar that was cut? | `grep -rn -i jsonl src/ tests/ tools/` | No; only documents did, and they were swept in commit `354a91d` |

