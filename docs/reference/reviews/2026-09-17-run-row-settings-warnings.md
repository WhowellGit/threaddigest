# Review record: revision 0005, the run row's settings and warnings (2026-09-17)

**Scope.** `src/threaddigest/db/migrations/versions/0005_run_settings_and_warnings.py`,
`src/threaddigest/db/repo.py` (a new write, two widened ones, one widened display read),
`src/threaddigest/db/schema.py` and `schema.sql`, `src/threaddigest/settings.py`,
`src/threaddigest/services/runs.py`, `runs_view.py`, `report.py`,
`src/threaddigest/core/digest.py` and both of its templates, the report page template and
the Runs routes, plus `tests/fixtures/db/0004.sqlite`. Landed as `3c25351`, `ec4ddd6` and
`f3f05a1`. A migration and `db/repo.py` are review-required surfaces, which is why this
record exists.

**Why now.** D-38's two follow-ups, parked on M2 and M1b by the entry that recorded them:
a run stored only the *fingerprint* of its settings, so a changed fingerprint could not be
resolved into the keys that changed, and a warning raised through `RunContext.warn`
survived only as `counters_json["warnings"]`, a number. Wes ruled on 2026-09-17 that both
should be done now rather than with later milestones (`DECISIONS.md`, D-39).

**How reviewed.** In-family, the session that built it under a bounded brief, tests before
the code; not an independent seat, which is this record's weakness. Four things were
checked rather than assumed:

1. *That the two behaviours were red first.* The warning test failed on
   `json.loads(None)` — the column held NULL — and the digest test on
   `assert [] == [SettingChange(key='budget.per_run_requests', previous='1500',
   current='500')]`. The migration's own two tests were watched red with the revision file
   held outside the versions directory, which is the only way to make an already-written
   migration fail honestly.
2. *That the fixture database was generated, not hand-made.* `tests/fixtures/db/0004.sqlite`
   was produced from the 0003 fixture by the migrations as they stood **before** revision
   0005 existed, checkpointed so no sidecar was left, with its row counts copied into the
   manifest — runbook § 4 step 1's documented fallback, the same way 0002's and 0003's were
   made. The generator script ran from the repository root against a working copy; the
   packaged file is the copy, so the committed fixture has never been opened read-write by a
   test.
3. *Whether the settings column could be written where the brief put it.* It could not. The
   brief specified the settings on the run-row insert; built that way, every `db upgrade`
   against an existing database died inside `repo.insert_run` with `no such column`, before
   the backup that makes the command recoverable, because `db upgrade` opens its run row on
   the file it is *about to* migrate. The existing migrate-service tests caught it on the
   branch. The deviation, its reason and its new control are recorded as KI-039 and in
   D-39's fourth bullet; the plan and the runbook state the rule in the same change.
4. *Whether the counter and the list can disagree.* `RunContext.warn` moves both, a unit
   test walks four warnings asserting the two lengths at each step, and an end-to-end test
   asserts `counters_json["warnings"] == len(warnings_json)` on a real run. The page's
   "named of counted" count is therefore `n of n` for every run since this revision, and
   short only for a row written before it.

**Refutations attempted.**

- *That `settings_changes` should stay a list and use a boolean beside it.* Refused: the
  row already draws the ``[]``-is-not-NULL distinction for `violations_json`, and a second
  spelling of the same idea in the same model would be the drift.
- *That `RunSummary.settings_changed` should return `0 of N` when nothing was recorded.*
  Refused: a zero there reads as "nothing changed", which is the lie the whole change
  exists to remove. It raises, and a rendering test proves neither template reaches it.
- *That the digest's denominator should be today's settings count.* Refused for the
  two-recorded case: a key added or removed between the runs would then put the numerator
  above the denominator and fail the model's own validator. It is the keys the two rows
  between them recorded, and today's count only where there is nothing to compare with.
- *That the warnings should be flushed by a statement of their own.* Refused: the heartbeat
  is already the one write that happens during a run, and a second statement per beat buys
  nothing. A beat carrying no warnings names the column at all, which is what keeps the
  heartbeat callable below head.
- *That `RunProblem` should gain a field saying which column a problem came from.* Refused
  under N-20: every reader asks the same question of it ("what is this called"), and no
  caller branches on the answer.

**The live check.** Two real runs through the fake gateway on a throwaway data directory,
with `budget.per_run_requests` changed between them. The digest's settings line read
`Changed since the previous run: 1 of 21 non-secret settings (5%) (9e8247f2… → 914a14e7…).
static.budget.per_run_requests: 1500 → 7`; the run page listed
`run_budget_or_ceiling stopped before r/aftereffects` and `Warnings named: 1 of 1 warnings
this run (100%)`.

**Left open, named here rather than papered over.** The fixture-database generator the
runbook's § 4 step 1 promises still does not exist, so a fixture is made by the documented
fallback and its correctness rests on the person following it; `make fixture` names the demo
corpus, not this. The review-required surfaces this change touched were reviewed by the
session that wrote them.
