# Review record: M1b's tree stage (2026-09-17)

**Scope.** `src/threaddigest/services/trees.py` (new), `src/threaddigest/services/runs.py`
(five counters and the shared fetch ladder), `src/threaddigest/services/sweep.py`
(`fetch_page` delegates to that ladder), `src/threaddigest/db/repo.py` (`due_posts` returns a
`DuePost` row), `tests/services/test_trees.py` (new), `tests/services/__init__.py` (new),
`tests/db/test_repo_comments.py` and `tests/db/test_repo_reads.py` (the widened read's
assertions), `docs/TEST_STRATEGY.md` (TR-01, TR-02, TR-04 flipped). `db/repo.py` is a
review-required surface, and a module was started and finished on a core surface, which is
why this record exists. No migration: every column this stage writes exists at revision 0001.

**Why now.** The pure planning half (`core/trees.py`) and the write half (the comment upsert,
the stub replacement, the tree stamp) landed first; this is the service between them, and the
last M1b commit that can be reviewed before the collector wires it (`services/collect.py`,
the next brief). The design is the M1b design memo § C, with the four rulings it rests on
recorded as D-41.

**How reviewed.** In-family, the session that built it under a bounded brief, tests before the
code; not an independent seat, which is this record's weakness. Thirteen service tests were
written and watched red before the module existed, and three mechanisms were then held out
one at a time so the tests that claim them could be seen failing against a stage that was
otherwise complete:

1. *The counters' commit rule.* Folding a tree's counters before its transaction, instead of
   from its committed result, turned `test_the_counters_are_folded_only_from_committed_writes`
   red with `assert 4 == (0 - 0)`: four comments counted against a `comments` delta of zero,
   which is exactly the shape that makes the FAILURE invariant
   `counters_equal_table_deltas` accuse the collector of a bug that is really lock contention.
2. *The ladder.* Writing `(next_check_at, next_stage)` from one `next_check` call — the
   memo's § C.2 sentence, read literally — turned TR-01 red with
   `assert 1757786400 == 1757700000 + 3 * 86400`: the rung just checked, re-written, leaving
   the post due at the same moment it was already due. The stage takes the timestamp from the
   *new* stage instead, which keeps the invariant the sweep's insert establishes
   (`check_stage` counts the checks performed; `next_check_at` is the rung that count
   schedules).
3. *The reserve.* Replacing `budget.can_afford(1)` with a bare "past the limit" test turned
   TR-04 and the hard-cap test red with `assert 6 <= 5`: six requests spent against a cap of
   five. The guard is what keeps the reserve for the requests the stage never plans
   (prawcore's retries, a token refresh).

**Decisions taken here, with what they cost.**

- *The due queue is one read, not three.* The stage must advance the ladder, which needs
  `created_utc` and `check_stage`, and must decide the skip, which needs `num_comments`;
  `due_posts` returned `(pk, reddit_id)` and `services/` may not build SQL (the rule
  `repo.floor_population`'s docstring states). Three candidates: widen `due_posts` to a
  `DuePost` row, add a second read beside it, or read two integers per post. The widening
  won: one statement for the whole queue, no second definition of the queue's order, and the
  range-plus-sort plan DB-08 asserts is unchanged (the test was re-run, not relaxed). The
  cost is that the brief's do-not-touch list named `db/repo.py`, so this is a deviation, and
  it is reported rather than buried.
- *One ladder, not two.* The 429 rule, the transient ladder, the auth and HTML aborts and the
  `finally: sync_budget` were `sweep.fetch_page`'s body. A second copy in the tree stage
  would have been a second rule and a ninth function over the cognitive-complexity ceiling,
  so the body moved to `runs.fetch_with_ladder` and both stages call it with their own unit
  of work and their own heartbeat label. `fetch_page` keeps its name, signature and the one
  thing that is genuinely the sweep's: re-creating the lazy `iter_new_pages` call per attempt.
  The sweep's own error suite (TE-01, TE-02, the locked-write and dry-run tests) passed
  unchanged, which is the evidence the move is behaviour-preserving.
- *`comments_captured` is what this fetch wrote.* The alternative — every comment row the
  store holds for that post — is what the memo's planned invariant § D.1 compares against,
  and it needs a per-post `COUNT(*)` that no repository read offers and this layer may not
  write. The two agree on a first fetch, which is all of the backfill; they diverge only when
  a re-fetch returns fewer comments than the store holds, which is the deleted-leaf case
  TR-05 and M1c's `info()` re-check own. Named here so the invariant brief inherits the
  question rather than the assumption.
- *Three stage-level warnings are recorded once per run.* `tree_budget_exhausted`,
  `tree_incomplete_cap` and the ceiling keep the first occurrence's detail, because a
  thousand-tree backfill would otherwise write a thousand entries into `warnings_json`, which
  every heartbeat re-writes. One warning already makes the run `partial`, which is the whole
  signal, and which trees were incomplete is on their own posts in `more_skipped_reason`.
  `tree_fetch_failed` stays one per post, with the id in the detail: that one names what is
  still due.
- *A fourth warning name, `tree_write_failed`.* The brief named three. A fetched tree whose
  transaction is refused is neither a fetch failure nor a budget stop, and "every caught
  exception is recorded on the run row" leaves no room for silence; the sweep has
  `subreddit_finish_failed` for the same shape. It is proven by the locked-write test.
- *The stage refuses to run in a dry run.* The sweep fetches in a dry run because "does this
  source read" is the operator's question; a tree fetched in a dry run cannot be written, so
  it is budget spent for nothing, and against the `mode=ro` engine every tree would have been
  recorded as a write failure. It returns `stop_reason="dry_run"` and spends nothing.

**Refutations attempted.**

- *That the queue read should be bounded by exactly what the budget can afford.* Refused: the
  stage then cannot tell a drained queue from a truncated one, and would fall silent in the
  one case that matters. It reads one row past what it can afford, which is what makes the
  `tree_budget_exhausted` warning honest.
- *That a skip should be refused when the budget is exhausted.* Refused: a zero-comment post
  costs no request, and refusing it leaves a post due that could have been retired for free.
  The ceiling still stops a skip, because a stamp is work and the ceiling bounds wall clock.
- *That `services/trees.py` should copy `sweep._author_writes` for its commenters.* Refused
  on duplication (eight similar lines is a finding against a ceiling of zero) and rewritten
  as a sort-and-last-wins fold, six lines, with the twin named in its docstring. Extracting
  one shared function needs a structural protocol over two pydantic models and a home neither
  module owns; reconcile at M1c is the third caller and the moment to do it.
- *That the refreshed post a tree fetch returns should be written.* Refused: the ownership row
  for `("posts", COMMENTS)` owns the eight coverage and ladder columns and nothing else, and
  the post's own numbers are the sweep's to record.
- *That the tree stage needs its own `wall_clock_ceiling` warning name.* Refused: one ceiling
  reached is one fact about the run, and the first stage to reach it keeps the detail.

**Left open, named here rather than papered over.**

- The `comment_more` clause of `counters_equal_table_deltas` still reads the old way. A
  re-fetch that completes a tree decreases that post's stub count, and until the invariant is
  narrowed as D-41 ruling 2 says, such a run would close `failed`. Nothing calls this stage
  yet (`collect.py` is the next brief) and the invariant changes in the brief after it, but
  the window exists and this is the second record to say so.
- A skip stamps the coverage columns as "never fetched". For a post Reddit reports with no
  comments that is exactly right, and `num_comments` counts deleted items so a post with a
  captured tree cannot reach the skip; if one ever did, its `comments_captured` would be
  zeroed while its comment rows stood. Reported to the main session as a widening candidate
  for the invariant brief rather than guessed at here.
- Unknown enum values on comments are not counted. `repo.unknown_enum_occurrences` reads the
  `posts` table only, so folding comment occurrences into `ctx.unknown_enum_keys` would make
  `unknown_enum_values_are_counted` fire against a DB side that cannot see them. Neither
  enum field the counter covers (`post_hint`, `removed_by_category`) exists on a comment
  today, so nothing is lost; widening both halves together is an M1c decision.
