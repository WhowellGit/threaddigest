# Review record: M1b's comment writes and the ownership rows (2026-09-17)

**Scope.** `src/threaddigest/db/repo.py` (four new writes, one read reordered, one generator
widened), `src/threaddigest/db/ownership.py` (three new rows and two new fields on the
declaration), `tests/db/test_repo_comments.py` (new), `tests/db/test_repo_ownership.py` and
`tests/db/test_query_plans.py`. Landed as `6f1ad4c`. `db/repo.py` is a review-required
surface and the ownership table is the enforcement declaration the upsert generator reads,
which is why this record exists. No migration and no fixture database: every column this
milestone writes exists at revision 0001.

**Why now.** M1b (comment trees) starts with its database layer, so the first commit of the
milestone carries its own rulings rather than inheriting them as assumptions (`DECISIONS.md`,
D-41). The design is the M1b design memo's § C.5 (the stub lifecycle) and § C.7 (parent
resolution), with the queue order from § C.1.

**How reviewed.** In-family, the session that built it under a bounded brief, tests before
the code; not an independent seat, which is this record's weakness. Five things were checked
rather than assumed:

1. *That the two load-bearing behaviours were red first.* The queue order was watched red
   with the read left at `ORDER BY next_check_at`
   (`assert ['oldest', 'middle', 'newest'] == ['newest', 'middle', 'oldest']`), and the
   terminal-content guard was watched red with `terminal_guard_columns` emptied on the
   `comments` row (`assert 'a reply' == '[deleted]'`) — the guard held out, which is the only
   way an already-written enforcement mechanism fails honestly. DB-08's new assertion was red
   against the shipped read before the order changed.
2. *Where the deletion decision belongs.* It is made inside `repo.comment_values`, not by the
   caller as `services/sweep.py::_post_write` does for posts. The reason is the read: the
   classification the upsert has to do anyway returns the prior state, so a tree is read once
   instead of twice, and a four-thousand-row tree is the case that makes the difference. The
   rules applied are `core.deletion.decide`'s, unchanged.
3. *Whether the terminal rule could be left to the values.* It could, and was refused. The
   state is what M1c's scrub acts on, so a rule that holds only for callers that remember it
   is the class this project treats as unenforced; the guard is a `CASE` in the statement's
   own `SET` clause, declared in the ownership row and asserted both ways (every guarded
   column emitted as a `CASE`, no other column emitted as one). A control test proves the
   guard is keyed on the *terminal* state alone: a moderator removal, which `decide` returns
   to `live`, is still updated.
4. *That an update-only ownership row cannot pass the declaration's rules vacuously.*
   `("posts", COMMENTS)` never inserts, so rules 2, 4, 5, 6 and 7 have no premise on it. It
   declares `upserts=False`, `_upsert_for` raises for it, and it is checked instead against
   the mapping its named statement writes — the same shape of check rule 4's value half gives
   an upsert. The value-builder parametrization gained a completeness test, so a future
   ingest path cannot declare `insert_columns` and sit outside it.
5. *That the parent resolution stays honest on a re-fetch.* `parent_comment_pk` is a derived
   column, never in the upsert's `SET` clause, and the resolving `UPDATE` touches only rows
   still NULL — so a parent resolved by an earlier fetch is not recomputed, and a parent that
   arrives in a later fetch is resolved then. DB-24 asserts both directions in one test.

**Refutations attempted.**

- *That the queue's new order needs an index on `created_utc`.* Refused: the range is still
  served from `ix_posts_next_check_at` and SQLite sorts it in a temporary b-tree, which at the
  few thousand posts this store holds costs nothing. The sort is asserted in DB-08 rather than
  tolerated, so the day it stops being nothing is visible.
- *That `stamp_tree_on_post` should take its eight columns as keyword arguments, as the brief
  wrote it.* Refused: eight would be a new `PLR0913` violation against a ceiling that only
  goes down, and a named value object makes a ninth column a change to a type the declaration
  is checked against. The deviation is here and in the function's docstring.
- *That `upsert_authors` should keep one hard-coded path.* Refused: the comment stage writes
  `authors` too, and the row that governs a write should be the row of the path making it. The
  emitted statement is identical either way (`authors` has no `source` column), so the
  parameter is the declaration's, not SQLite's, and it defaults to the sweep's path so no
  existing caller changes.
- *That the two `authors` rows should be written out twice, as the file's "declared as data"
  style says.* Refused: two copies of one declaration drift, and eight identical lines are a
  duplicate-code finding against a ceiling of zero. One builder with two concrete uses, and
  the thing that must differ between them — the path — is the only thing that does.
- *That the batch reads could take the whole tree in one `IN (...)`.* Refused: a tree at the
  expansion cap is thousands of ids and every id is a bound parameter; SQLite's compiled
  ceiling is 999 on older builds, so the reads are chunked and the reason is in the helper.

**Left open, named here rather than papered over.** The `comment_more` clause of the
`counters_equal_table_deltas` invariant still reads the old way: the ruling that narrows it is
recorded (D-41, ruling 2) and the write it is about is tested here
(`::test_a_tree_that_left_no_stubs_clears_the_post_s_old_ones`), but the invariant itself
changes with the stage that reads it, so between this commit and that one a re-fetch that
completes a tree would fail the invariant if the tree stage existed to run it. It does not
yet: nothing calls these writes until `services/trees.py` lands, which is the same milestone
and the brief that changes the invariant. The plan's step 2 and the normalizer's module
docstring were corrected in the same change as the write, under the mirrors rule, because the
shipped adapter reads trees as raw JSON and both still described PRAW model objects.
