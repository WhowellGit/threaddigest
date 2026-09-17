# Panel CP — Seat A: correctness and tests

## 1. What I was given

Brief `scratchpad/brief_CP_code_panel.md`, seat A only. Tree: detached worktree
`/Users/wesmax/repos/threaddigest-review-7528af9` at `main` **7528af9**. Read-only: I edited,
created and deleted nothing in any checkout (`git status` there is clean). Read first: `CLAUDE.md`,
`docs/OVERVIEW.md`, `docs/PLAN.md` (§ Data model, § Collector algorithm, § Silent-failure
controls, § Robustness), `docs/TEST_STRATEGY.md` § 3, `docs/runbook/KNOWN_ISSUES.md`.

Commands (all with `THREADDIGEST_DATA_DIR` in my scratchpad, gateway `fake`, no network):
`uv sync`; `uv run pytest -p no:randomly -q` (whole suite) and `--collect-only`; targeted runs of
the migration, alembic, run-lifecycle, report-service, deletion, budget, digest and
routing-pointer test files; `tools/make_demo_fixture.py`, `threaddigest db init`, `threaddigest
run --gateway fake --fixture …` and the same `--dry-run`; five scratchpad scripts.

Suite at 7528af9: **1311 collected, 1 failed** — A1.

## 2. Findings

**No P0.** Nothing here produces a wrong stored result or an unsafe write on a real run at the
shipped configuration. A2 is the nearest miss and is one config edit away. **P1 — four rows:**

| id | file:line | claim refuted | evidence | cost | smallest fix + enforcer |
|---|---|---|---|---|---|
| **A1** P1 | `tests/gates/test_routing_rows_resolve.py:299`, resolver `:169` | G44 "routing pointers resolve" is `shipped` and green. It is **red on the committed tree** wherever `.build/` has not been generated. | `uv run pytest tests/gates/test_routing_rows_resolve.py -q` → `AssertionError: routing pointers that resolve to nothing: memory/feedback-tooling-habits.md:11: \`.build/\`: no such file`. The gate reads the private memory home (outside the repo) and resolves its path tokens against the repo root; `.build/` is gitignored (`.gitignore:16`), and the memory line itself says so. | The project's own rule sends a second session into a **worktree**; every such session, and every fresh clone on this machine, opens with a red `make check` unrelated to its change — how an operator learns to read red as noise (KI-001's class). | Teach `resolve_path` a small set of generated-at-runtime tokens, or stop the memory line naming one. Enforcer: the gate + a positive control run with `.build/` absent. |
| **A2** P1 | `core/budget.py:57-62`; `services/sweep.py:381,1019`; `tests/gates/test_no_bypass.py:48` | Irreversible rule 3, "the hard cap holds". `hard_cap` bounds only the configured `limit`; nothing bounds what a run **spends**. | `can_afford` is `used + cost <= limit - reserve`, checked before a page; `fetch_page` then walks a 4-attempt ladder and, with the real adapter, buys a fresh token per retry (AD-02's `test_an_invalid_token_midrun_buys_a_fresh_token_for_every_retry`). `BudgetSettings.reserve` is `ge=0` and the validator only refuses `per_run_requests > hard_cap`, so `reserve: 0`/`per_run_requests: 5000` is legal. Ran `Budget(limit=5000, reserve=0, hard_cap=5000)`, `used=4999` → `can_afford(1) is True` → page costs 8 → `used=5007, past_hard_cap=7`. The CF-02 gate asserts only the recorded `limit`; its docstring records that the `api_requests <= 5000` assertion was dropped as "trivially true". | Shipped `reserve: 100` absorbs ~10 unplanned responses, so the cap holds today by ~90 — a coincidence of two editable numbers, not construction; `reserve: 0` retires the rule silently. | `can_afford` takes `min(limit - reserve, hard_cap)`, or a FAILURE-severity invariant `api_requests <= budget.hard_cap`. Enforcer: gate + positive control (a gateway whose counter jumps past the cap must fail the run). |
| **A3** P1 | `core/budget.py:3-5`; `services/runs.py:490-496` | Both docstrings say the adapter's Session hook "calls `record` for EVERY HTTP response", so `sync_budget`'s `max` "is a no-op" under PRAW. | `grep -rn "\.record(" src/` returns **no call site**. `adapters/reddit_praw.py:97` counts inside `CountingSession.request` into its own field (`requests_made`, `:435`); `services/runs.py:497` is the only writer of `Budget.used`. | The documented mechanism does not exist. A maintainer believes `used` tracks every response; it moves only at the four `sync_budget` call sites, so `can_afford` reads a stale value between them — the mechanism behind A2. | Say `used` is synced from `gateway.requests_made` at named points and that `max` is load-bearing (monotonicity). Enforcer: review-only (prose); A2's invariant is the mechanical half. |
| **A4** P1 | `docs/TEST_STRATEGY.md:99` (DB-64); `services/runs.py:268-276`; `tests/services/test_runs_lifecycle.py:426` | DB-64: "the counter and `warnings_json` stay the same length". The cited test asserts it on the in-memory `RunContext`, where one method mutates both fields — **no production change can make it red** — and on the row it has a counterexample. | Reproduced: start a run, `warn` twice, heartbeat (flushes `warnings_json`), die, let a later `sweep_stale` stamp it. Row: `status=crashed`, `counters_json=None`, two entries in `warnings_json`; via `runs_view.one`, `counters.warnings=0` against `recorded_warnings=2`. `repo.mark_runs` (`db/repo.py:854`) never writes `counters_json`. | Contained — `web/routes/runs.py:170` derives the denominator from the named list, so the page prints "2 of 2". But the crash case is what revision 0005 was built for, and the test cannot see it. | Assert the equality **on the row** after a stale sweep; positive control = remove the heartbeat flush. Correct `runs_view.unrecorded_warnings`'s docstring (`:115-124`), which claims zero for every run since 0005. |

**P2 (maintainability, clarity, dead paths).** Each: claim → evidence → fix/enforcer.

- **A5 `core/deletion.py:134-138`.** Rule 5's docstring line says the hold records
  "`gone_unconfirmed` with `misses + 1`"; the code (`:205`, `escalate=False`), the plan
  (§ Data model clause 5, "without counting a miss") and the same docstring's closing paragraph all
  say `misses` is unchanged — a stale pre-KI-021 line inside the function governing a compliance
  obligation. Delete the clause; review-only, the behaviour is pinned by
  `test_a_bodyless_return_then_one_omission_is_still_an_unconfirmed_hold`.
- **A6 `services/report.py:134-137`, `core/digest.py:236-241`.** The section renders "last 7 days
  against the trailing 4 weeks", but `baseline_since = at − 28 d` and
  `titles_baseline = posts_in_window(baseline_since)`, so the baseline **contains** the now-window:
  my seeded run printed `titles_now=75`, `titles_baseline=315` — containment, not contrast.
  Harmless while the phrase list is empty; at M1d every phrase's baseline will include its own
  now-count and "rising" will understate. Make the baseline `[at − 28 d, at − 7 d)` or rename the
  label; enforcer: a unit test asserting `titles_now + titles_baseline == posts_in_window(28 d)`
  (today's code is its own red control).
- **A7 `cli.py:534-545`.** The dry-run notice warrants two numbers ("posts_new and posts_updated
  are always 0 here") while `rejects` prints on the same line and is **also** structurally 0 —
  `sweep.py:461` folds it only inside `if not ctx.dry_run:`, as with `unknown_enum_values`.
  Reproduced: `posts_new: 0  posts_updated: 0  rejects: 0  warnings: 0`, then the two-name notice.
  An operator dry-running a new source reads "rejects: 0" as evidence it normalizes cleanly. Name
  or suppress them; enforcer: extend `test_dry_run_writes_nothing_anywhere` to derive the list from
  the code rather than type it.
- **A8 `tests/unit/test_normalize.py:646,652`.** Fixture coverage is a hand-typed list, not a
  directory walk; it covers all five files today (I confirmed all five normalize to rows), so a
  sixth would be silently untested. Parametrize from `sorted(FIXTURES.glob("*.json"))`; control =
  a malformed file in a tmp copy.
- **A9 `services/sweep.py:12-16` vs `:424`.** The docstring's blanket "counters are folded after a
  commit, never inside one" is contradicted by `ctx.counters.pages += 1`, which runs right after
  `fetch_page`, before any write; `pages` is outside `DELTA_COUNTER_FOR_TABLE`, so DB-54 cannot see
  it. Small today, but it is the rule a future counter will be added under. Qualify it ("every
  counter folded from a `PageWriteResult`"); review-only.
- **A10 `tools/code_health.py:69`.** `DEAD_CODE_PATHS = ("src","tests","tools")` means vulture
  scans `src` and `tests` in one pass, so an `src` symbol reached **only** from a test counts as
  used and `.ratchets/code_health.txt` still reads `dead_code=0`. Production uses only
  `Budget(...)`, `.limit`, `.reserve`, `.hard_cap`, `.used`, `.can_afford`; `record`, `remaining`,
  `spendable`, `overspent`, public `clamp` and `tree_cost` appear only in
  `tests/unit/test_budget.py`. Scan `src` only, with `tests`/`tools` as `--make-whitelist` input;
  enforcer: `tools/code_health.py` + a ratchet key with a birth relaxation.

## 3. Checks I re-ran that held

- **Whole suite**: 1311 collected, one failure (A1); every test file the in-scope `shipped` rows
  cite is green. **Every node id in `docs/TEST_STRATEGY.md` § 3 resolves**: 189 references parsed
  out of the tables, 0 unresolved — but **no gate enforces this**, since G40 covers
  `KNOWN_ISSUES.md` and `GUARDS.md` only, so it holds by hand.
- **Migration 0005**, independently, on a copy of `tests/fixtures/db/0004.sqlite`:
  `0004 → 0005 → 0004 → 0005`. Row counts unchanged across eight tables, **both `ON DELETE
  CASCADE` children (`run_subreddits`, `raw_rejects`) intact**, columns added and dropped as
  declared, `foreign_key_check` empty, `integrity_check` = `ok`. Fixture set complete: `0001–0004`,
  exactly the non-head revisions (DB-44/DB-45).
- **`deletion.decide` ordering** matches the plan's content-state machine clause for clause,
  rules 1–8, including rule 3 keying on `removed_by_category` before any body predicate, rule 7's
  link-post hold, and KI-021 (only an `info()` omission escalates); `scrub` is entry into
  `SCRUB_STATES` from outside it, so a re-observation never re-scrubs.
- **`normalize` on every synthetic fixture**: all five produce a row, none a `Reject`.
- **Digest denominators against a seeded temp database** (demo fixture, 316 posts / 6 sources,
  run `ok`): `posts_new 315 of 315 items seen`, `new_posts 315 of 315`, `untagged 0 of 75`,
  `titles_now 75`, `titles_baseline 315`. Direct SQL: 75 posts in 7 days, 315 in 28,
  `sum(items_seen)=315`, `sum(new_items)=315` — every denominator counts the population it names
  (subject to A6).
- **P0-2 holds**: `write_page` mutates no `ctx` counter and folds *this* page's contribution into
  the committed `run_subreddits` row (`replace(progress_before, items_seen=+slots, …)`), so the row
  is current, not one page behind; a write that raises counts nothing, and reject slots survive an
  all-rejected page.
- **`finish_run_from` is never reachable below head**: both below-head closings go through
  `db.migrate.finish_below_head_run` / `finish_restored_run`, and `record_run_settings` shares the
  insert's transaction, so a row carries its settings or NULL, never half.
- **`resolve_status`** precedence is as documented (FAILURE violation > terminal > any warning >
  ok), with the vocabulary pinned by `tests/services/test_invariants.py:106-107`; a late KI-013
  checkpoint warning re-resolves and re-closes the row. End-to-end, `api_requests: 8` for 7 pages
  plus the one preflight `about()` — exact.

**Weakest test in the tree: `tests/unit/test_budget.py`.** ~40 assertions plus a hypothesis
property, every one against an API **no production code calls** (A10). It cannot go red for any
defect a run could suffer, only if someone deletes code nothing uses — and it is what keeps
vulture's `dead_code=0` looking honest. Runner-up:
`tests/services/test_runs_lifecycle.py::test_the_counter_and_the_recorded_list_stay_the_same_length`
— tautological (A4).

## 4. Cut list

- `core/budget.py`: `record`, `remaining`, `spendable`, `overspent`, public `clamp` (~30 lines) and
  the ~100 lines of `tests/unit/test_budget.py` that exist only for them. `tree_cost` is genuinely
  M1b's — keep it with a milestone note, not a test implying it is live.
- `services/collect.py`: `_finish_cancelled`'s checkpoint-and-re-finish block duplicates
  `_collect_persisted`'s; one helper taking `(status, violations_json, error)`.
- `services/runs_view.py:124`: the `max(…, 0)` clamp exists only to hide the reverse direction A4
  demonstrates; deriving the count from the row removes clamp and ambiguity together.
- `services/runs.py`'s `SeverityCarrier` is **not** a cut — it keeps the import cycle out; noted so
  the next reader does not take it for ceremony.

## 5. Confidence

**High**: A1 (reproduced twice; the mechanism is in the resolver), A3 (no `.record(` call site in
`src/`), A5 and A9 (code read against its own docstring and the plan), A7, A8, A10 (reproduced or
read directly). **High mechanism, medium reach**: A2 — the demonstration is exact, but it needs
`reserve: 0` or a raised `per_run_requests`, neither shipped. **High counterexample, medium
severity**: A4 — every reader I checked derives around it. **High arithmetic, medium intent**:
A6 — whether M1d wants a disjoint baseline deserves one line from Wes.

The in-scope code is in better shape than the seat's remit assumed: every load-bearing path I was
sent to break held under independent re-checking. The failures concentrate in **claims** — two
docstrings describing a counting mechanism that does not exist (A3), one guarantee tested where it
cannot fail (A4), one stale rule line (A5), one gate green only on the machine that generated its
untracked prerequisite (A1).
