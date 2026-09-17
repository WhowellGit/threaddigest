# Panel CP, seat C: adversarial, aimed at the previous rounds' conclusions

## 1. What I was given

Brief `scratchpad/brief_CP_code_panel.md`, seat C only. Tree: the detached worktree
`/Users/wesmax/repos/threaddigest-review-7528af9` at `7528af9`. I committed nothing; the three
staged violations of item (4) were reverted (`git checkout -- . && git clean -fd`), and
`git status` is empty at `7528af9`.

Commands: `uv sync`; `pytest -m "not live"` (full suite ×3); `ruff format --check`,
`ruff check`, `lint-imports`, `mypy src`; `code_health.py`, `doc_policy.py --check`,
`ratchet.py measure|compare` (reports written to my scratchpad, never `.build/`);
`make_demo_fixture.py` + `db init` + `run --gateway fake` against a temp
`THREADDIGEST_DATA_DIR` in the scratchpad; three probes under `scratchpad/seatC/` driving the
real adapter through `responses`, no network. Never `make check`, `make setup`, or
`pre-commit install`.

## 2. Findings

| id | file:line | claim refuted | evidence | cost | smallest fix / enforcer | conf. |
|---|---|---|---|---|---|---|
| **C-1** P0 | `adapters/reddit_praw.py:450-456` | Plan § failure matrix, row "429 with `Retry-After`": *sleep the bounded wait, retry once; a second 429 → run `rate_limited`*. `TEST_STRATEGY.md` AD-02 says **shipped**. | `seatC/probe_429_date.py`: a 429 whose `Retry-After` is the HTTP-date form RFC 9110 also allows → `GatewayError: the library could not describe Reddit's answer: could not convert string to float: 'Wed, 21 Oct 2026 07:28:00 GMT'`; `isinstance RateLimited = False`; `core.retry.classify = fatal`. Control: the seconds form → `RateLimited`, `classify = rate_limited`. Cause: `prawcore/exceptions.py::TooManyRequests.__init__` calls `float(retry_after)` while *building* the exception, so `_from_too_many_requests` is never reached. | No back-off. `fatal` → `fetch_page` re-raises → `_classify_failure` falls to `_DEFAULT_FAILURE` → the source is stamped `status='error'`, `+1` failure, and **the loop moves to the next source and keeps requesting while Reddit is rate-limiting us**. Run row: `partial`, exit 3, no notification; the operator is told his subreddits errored. | In `_get`, identify the raising frame (as `_raised_in_the_oauth_table` already does for `KeyError`) or parse with `email.utils.parsedate_to_datetime`, and raise `RateLimited`. Enforcer: a `responses` test on the date form asserting `RateLimited`, the pre-fix `GatewayError` as positive control; add the row to AD-02. | code: high. Reddit sending that form: unverified (probe day). |
| **C-2** P1 | `tests/gates/test_routing_rows_resolve.py:240-246, 299` | `CLAUDE.md`: routing pointers "name … paths that exist \| `tests/gates/test_routing_rows_resolve.py`". **The required suite is not deterministic on this commit.** | Three full `pytest -m "not live"` runs on an unmodified `7528af9`, same command: run 1 **exit 0**, runs 2 and 3 **exit 1**, always `FAILED … test_every_routing_pointer_resolves` — `memory/feedback-tooling-habits.md:11: '.build/': no such file`. `pytest tests/gates` alone is red; `mkdir .build` makes the isolated test pass. Two causes stack: `memory_snapshot.default_paths()` resolves to `~/repos/threaddigest-private/memory-snapshot`, i.e. **files outside the repository**, and `tests/gates/test_hooks.py:773` creates `.build/` in the real checkout, so the verdict turns on residue another test leaves. | A required gate that flips between runs on one commit. In CI (no private home) `memory_files()` returns `[]`, so the memory half of G44 checks nothing; here it goes red for reasons unrelated to the change. Same family as KI-032/KI-035: a gate asking about the machine, not the repository. `make check` masks it — its `\| $(BUILD_DIR)` prerequisite creates `.build/` first. | Resolve pointers against the *tracked* tree plus a declared allowlist of generated dirs; no test may create `.build/` in the real checkout. Enforcer: a positive control running the gate with `.build/` absent and with the snapshot absent, asserting the same verdict both ways. | high |
| **C-3** P1 | `tests/services/test_sweep_errors.py:137-139`; `services/collect.py` | Item (4): three violating changes, no guard edited. **All three passed every gate.** | (a) KI-007's regression assertions rewritten to `assert result.terminal_status is not None` / `assert isinstance(clock.sleeps, list)` — assert and collected counts unchanged. (b) `importlib.import_module("praw")` inside `services/collect.py`. (c) a live write to a path outside any resolved data directory from `_collect_persisted`. Results: `ruff format --check` ok; `ruff check` "All checks passed"; `lint-imports` "Contracts: 3 kept, 0 broken"; `mypy` "no issues found"; full pytest — only C-2's flapping gate; `ratchet compare` → "21 ok, 0 red". The out-of-tree file received **37 lines** from the test suite itself and G19 never fired. | Irreversible rule 1 has two halves and only the test-isolation half is enforced; G05 confines *static* praw imports only; nothing detects an assertion weakened in place. | (c) matters most: an autouse fixture failing any test that opens a path for writing outside `tmp_path`/`DATA_DIR`, with a positive control. (b) a ruff `TID251` ban on `importlib.import_module` outside `db/` and `cli`. (a) review-only — the PR-body "Tests changed" table is the only thing between this and `main`. | high |
| **C-4** P1 | `web/templates/report.html:1-4` vs `:19-22`; `core/digest.py:590-591`, `:806-807`; `db/repo.py:1582` | The template's own header: *"Every number is printed through the `count` filter … so no figure can reach this page without the population it came out of."* Plan: *"the digest and the UI never show a bare number"*; *"N comments on reddit (M captured)"*. | Lines 19-22 print `distinct_author_count`, `comment_count` and `score` as bare integers, not through `counted()`. The Markdown and standalone-HTML renderers do the same. `comment_count` is `posts.num_comments` — Reddit's count *including deleted items*, the field the plan singles out as needing its captured denominator; M captured is 0 for every row today. | The one list the digest exists for prints three undenominated numbers, one of them a foreign count presented as ours. | Give `PostItem` a `Count` for comments and print the ranked row through `counted()`. Enforcer: a web test asserting no `data-post` row holds a digit outside a `counted()` span, plus the same on the Markdown golden. | high |
| **C-5** P1 | `adapters/reddit_praw.py:342-356, 385-395` | Item (3). `TreeResult.comments` is *"every comment in depth-first order"*. | `seatC/probe_tree.py` (b): base fetch returns `t1_c1` + a `more` stub; the `morechildren` batch returns `t1_c2` **and `t1_c1` again** → `['t1_c1','t1_c2','t1_c1']`, 2 distinct ids in 3 entries, `complete=True`. `_TreeBuilder.add` indexes by `parent_id` with no de-duplication on `name`, so a repeated *parent* re-emits its whole subtree. The fake cannot produce this shape (each stored comment is emitted at most once), so the AD-04 contract suite as designed would never see it. | `morechildren` is called with `limit_children=0`, so overlap with the base fetch is the expected case. At M1b `comments_captured` over-counts; the upsert dedupes, so the planned invariant *"comments_captured equals the actual count per fetched post"* would fire against the collector for the adapter's fault. | De-duplicate in `_TreeBuilder.add` on `data["name"]`. Enforcer: the probe as an adapter test plus a fake scenario that re-delivers a comment, so the contract suite can express it. | high |
| **C-6** P2 | `reddit_praw.py:379-383` vs `adapters/reddit_fake/trees.py:86-90` | `MoreStub.count` is the number of hidden comments; `comment_more.count` renders as *"N replies not captured"*. | `probe_tree.py` (a): a stub whose wire `count` is 400 across 150 child ids splits into stubs carrying **100 and 50** — the adapter relabels Reddit's hidden-comment count as "ids in this chunk". The fake's replacement uses `sum(subtree_size(...))`, the true instance count. The two disagree by construction. | The UI understates "N replies not captured" on every split stub, and a test written against the fake asserts a number the adapter cannot produce. | Carry the remainder as `count - len(head)`. Enforcer: a contract-suite row comparing `MoreStub.count` after a split across both gateways. | high |
| **C-7** P2 | `services/migrate.py:410-424`; `tests/db/test_migrate_revisions.py::test_insert_run_and_touch_run_work_on_a_database_at_0001` | KI-039's landing record: the fix is guarded. | The guard is a **hand-maintained list of two functions**, while `db upgrade` issues four head-model statements against the not-yet-migrated file: those two plus `repo.table_counts` (via `_table_counts_json`) and `repo.insert_backup`. Latent only because `backups` and the tracked tables are unchanged since 0001. The project's own rule: *"scan a structural shape, never police a hand-maintained list"*. | The next revision touching `backups` reproduces KI-039 exactly — dying before the backup that makes `db upgrade` recoverable — and this test stays green. | Run the whole below-head prefix of `db upgrade` against a 0001 fixture (the shape, not the list). | high |
| **C-8** P2 | `db/repo.py:1181-1194`; `services/collect.py:286-291` | Plan: *"last successful run age against a threshold longer than the schedule's longest gap"*. | `last_successful_run` keys on `status == 'ok'`, and `ok` requires **zero** warnings. `wal_checkpoint_busy` (KI-013) is a warning any reader can cause, and `serve` is a reader by design (at M2 the runs page polls every two seconds). Any run that trips it is `partial`, so `doctor --alert-if-stale` sees no successful run at all. | If that warning becomes routine with the UI left open, the hourly staleness alarm goes permanently red on a healthy collector — the "train the operator to ignore the alert" failure the plan is avoiding. A proxy where the guard rules demand the invariant. | Key staleness on the newest run that swept a source successfully. Enforcer: a `doctor` test with a `partial`-but-collecting run asserting green. | medium |
| **C-9** P2 | `.ratchets/coverage.txt`, `tests.txt` | The ratchets backstop weakened tests. | `ratchet compare` on the **clean** tree: `OK coverage.line_percent floor=98.36 measured=98.13` (the floor has slack), `OK tests.asserts floor=3747 measured=3803`, `OK tests.collected floor=1290 measured=1307`. | ~56 assertions, 17 tests and 0.5 coverage points may go unnoticed — the headroom C-3(a) walks through. | `make ratchet-bump` after each green landing, so headroom is spent, not banked. | high |

## 3. Checks I re-ran that held

- 1,307 tests collected; apart from C-2's flapping gate every one passed on all three runs.
- `run` precondition order matches plan § Collector step 0 exactly: settings → DB file must
  exist → data tree → flock → `require_head` under the lock (`cli.py:308-324`, `448-456`).
- `services/invariants.py` INVARIANTS and severities match plan § Silent-failure controls one
  for one (three failures, four warnings); `resolve_status` implements the documented precedence.
- KI-039's other two doors are shut: the failed-backup and failed-migration paths close the run
  row through `db_migrate.finish_below_head_run` / `finish_restored_run` (`migrate.py:393`,
  `:538`), never `repo.finish_run`, each with a positive control.
- 403 private mid-run: `status='forbidden'`, `+1` failure, other sources continue, run
  `partial`, watermark and `last_complete_poll_at` untouched, `stop_reason='error'` recorded.
- 5xx storm: `TransientError` → the 30/120/300 ladder → that source only; committed pages stay.
- Demo end to end into a temp data dir: `status: ok (exit 0)`, 315 posts, 8 requests, 0 warnings.

## 4. What the demo hides (item 5)

316 posts, **0 comments**, `num_comments = 0` everywhere (`COMMENTS_PER_POST = 0`, stated in
the generator). Measured on the demo database:

- The digest's headline list is **ordered by `post_id` ascending**: every ranking key is
  constant (`100006q … 100006z | 0 authors | 0 comments | score 1`). The function the product
  is built around (D-09) is exercised by no demo run.
- `themes: []`, `theme_rules: 0`, `post_themes: 0` — `db init` seeds subreddits only, so
  `config/seed.yaml`'s 8 themes and ~50 patterns are read and validated by nothing until M1d.
- No title holds a character HTML must escape, a non-Latin script, an emoji, a newline, or more
  than ~45 characters; Reddit allows 300. Authors are 3-character synthetic names.
- No source approaches the 10-page cap, so `gap_suspected_at` / `stop_reason='cap'` (KI-018)
  never fire; no tombstone is ever *ingested* (the deleted post drops out of `/new` first), so
  tombstone rendering is untested by `make run`.
- `display_timezone: UTC` is shipped, so the seven M1d digests will be grouped by UTC days, a
  shape the demo never shows.

## 5. Cut list

- `new_head`: the port (`ports.py:164`), `PrawGateway` (`reddit_praw.py:468`), the fake
  (`listings.py:105`), plus `set_live_anchor`, `anchor_fullname`, `anchor_created_utc`,
  `_anchor_post` and both `NEW_HEAD_LIMIT` constants. The freshness anchor was cut (N-08) and
  **nothing calls it** — zero concrete uses, which N-20 forbids.
- `config/seed.yaml`'s `themes:` block: move it into the M1d change that reads it, or add a
  shape check now; today a typo there is silent.
