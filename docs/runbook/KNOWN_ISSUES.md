# Known issues — fixed bugs and their regression tests

> Policy (plan § Reference corpus, working agreement): every bug fix starts with a failing test, and every fixed bug lands one row here pointing at that test. The `Regression test` column must resolve to a collected pytest node id; the doc-currency test checks it. Rows are never deleted; a regressed issue gets a new row citing the old id. Open issues that have no fix yet may be listed with status `open` and an empty test column until the failing test exists.
>
> Status vocabulary: `open` (reproduced, no fix), `fixed` (test green on `main`), `regressed` (re-opened; cite the new row), `wontfix` (reason in root cause).

| ID | Date | Symptom | Root cause | Regression test (node id) | Status |
|---|---|---|---|---|---|
| | | | | | |

<!-- First row goes here when the first bug is fixed. Format example (do not count as a row):
| KI-001 | 2026-10-01 | Post page 500 on a scrubbed post with no permalink | template built the deep link from `permalink` instead of `reddit_id` | tests/web/test_post_page.py::test_tombstone_deep_link_uses_id | fixed |
-->
