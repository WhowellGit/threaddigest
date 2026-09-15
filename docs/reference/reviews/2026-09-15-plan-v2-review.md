# Plan version two against version one: the refute pass (2026-09-15)

After `docs/PLAN.md` was rewritten as version two, one fresh-context seat at the Opus tier, read-only,
was given both versions, the companion pages (`docs/OVERVIEW.md`, `docs/INSIGHTMINER_HARNESS.md`), the
decisions log, and the tree, and asked to break one claim: *every decision, number, constraint,
mechanism, test, route, table column, failure-matrix row, and owner duty in version one is either
present in version two or explicitly retired with a home; and every statement in version two is
true against the tree.* Every finding was re-checked against the tree by the main session before it
was acted on. The raw findings file stays outside the repository.

## Verdict

The claim did not stand, on either half. Version two had lost five items of design weight with no
home, eleven of its statements were false or overstated against the tree, ten of its statements
disagreed with another live document, and one cited record did not yet exist. The rewrite was
judged a clear improvement in readability and in built-versus-planned honesty; the defects were
concentrated where a list had been compressed into a phrase, and where the cadence decision of the
day before had not finished reaching the code.

## What it found in the code and configuration, and what changed

- **KI-025.** `core/retry.py` still carried the daily three-slot schedule: a constant of three
  intervals a day, a same-day deferral rule for `network` runs, a comment citing the plan for the
  three times, and tests pinning all of it. The rule and the constant are removed (a `network` run is
  retried at the next scheduled slot, which the launchd wrapper already does), the module docstring
  points at the cadence decision, and the retired-claims gate now scans `src/` and `deploy/` as well
  as the documents, with a positive control.
- **KI-026.** The shipped reconcile-age bound for items under thirty days was sixty hours, the
  daily-era derivation, shorter than the ninety-six-hour Thursday-to-Monday gap, so the M1c invariant
  it drives could never hold after one missed run. The bound is one hundred and twenty hours, and a
  schedule-contract test binds both reconcile keys to the launchd schedule.
- **The routing gate** checked only the first quoted target after an arrow in a router row; the
  second named a section version two had retired. Every quoted target is now checked.
- **Three retired-claims rows added** (`INTERVALS_PER_DAY`, `RawSink`, `collected-test floor`), and
  the widened scan surfaced two more residues on the way (the fake gateway's docstring naming the cut
  freshness anchor without its marker; the wrapper's help text calling the hourly check a dead-man).

## What it found in the documents, and what changed

- **Restored to the plan** (lost without a home): the eight declared indexes; the content-state and
  author-state values, including the terminal `gone`; the reconcile cost estimate; the coverage
  counters on the run row; the comment-tree wire facts; the comment deep-link form; the Run-now
  options and polling route; the single-function scrub assertion; cassette hygiene; the
  expand-and-contract recipe; the cloud-review trigger; and the concrete UI values a builder needs
  (page size, token names, the search grammar, the theme editor's behaviours, the gate-state detail,
  the fake's builder surface, the mutating-command list, the browser command).
- **Corrected in the plan** (false against the tree): the column is `comments_captured`; the
  `optimize` belongs to revision 0004 and the scrub stage, not 0003; no ntfy notifier exists; the
  rule column is `rule_group`; the seven built invariants are named and the rest marked by stage; the
  `backups` columns; two files missing from the layout; "went in at M0" and "every section walked"
  softened to what the record supports.
- **Mirrors swept**: the exit-code row and open item in the decisions log (5 `network` is
  implemented); the applied-learnings row on `caffeinate`; the test strategy's cut sink fake and its
  daily-era spec name; the router row naming a retired section; the runbook's pre-migration line;
  KI-021's wording; the Swept row describing the schedule; the working agreement's CI row.
- **Explicitly retired with a home**: the two UI wireframes and the never-practised three-line
  measured-result note.

## Held, by design

Three counts the seat flagged as restated in prose were removed from the plan (the module count of
the fake package, the hook count, the query-plan assertion count), so the harness page's generated
block and the test files are their only homes. The compliance bounds in the decisions log keep their
daily-era figures annotated rather than rewritten, because the log is append-only and the bounds as
a whole still await Wes's confirmation.

## Lesson

The inventory pass that preceded the rewrite read documents and found stale prose; this pass read
the code and found the two defects. Both seats were needed, and the second is the one that keeps a
rewrite honest: a plan that describes the code must be checked against the code, not against its
previous version.
