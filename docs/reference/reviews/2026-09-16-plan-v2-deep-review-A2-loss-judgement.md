# Version one to two: what was lost (2026-09-16)

## Claim under test

"Nothing version two reduced, dropped, or superseded was a load-bearing insight without a home:
every reduced row lost only detail a builder does not need or can find in the decisions log, the
runbook, the test strategy, or a review record it points at; every absent row is either superseded
by a recorded decision or retired with a named home; every superseded row's supersession is real
(the decisions log actually holds the content, not just a mention)."

**Verdict in one line: the claim does not hold, but it is close.** Seventy of the eighty rows lost
nothing. Ten rows lost something; one of those is serious, because version two does not merely omit
a distinction version one carried, it states the opposite of what the shipped code does.

## Method

Every row in `A1-disposition.md` with disposition `reduced` (48), `absent` (12), or `superseded`
(20) was taken, the version-one unit read in full, and the home the table names read in full. Each
row was judged on three questions: would a builder of tranche B, M1b, M1c or M1d act differently
without the dropped detail; would a reviewer re-derive or re-argue something the dropped text had
settled; and does the named home hold the content or only refer to it. Homes were read in the tree,
not assumed: `config/settings.yaml`, `config/seed.yaml`, `src/insightminer/core/retry.py`,
`src/insightminer/services/invariants.py`, `src/insightminer/services/runs.py`,
`.ratchets/suppressions.txt`, `.ratchets/skips.txt`, `docs/decisions/DECISIONS.md`,
`docs/learnings/DB_LEARNINGS_APPLIED_2026-09-12.md`, `docs/learnings/LEARNINGS_TRANSFER.md`,
`docs/TEST_STRATEGY.md`, `docs/runbook/RUNBOOK.md`, `docs/runbook/GUARDS.md`,
`docs/runbook/KNOWN_ISSUES.md`, `docs/INDEX.md`, `docs/OVERVIEW.md`,
`docs/INSIGHTMINER_HARNESS.md`, `docs/reference/reviews/2026-09-12-ui-design-review.md`,
`docs/reference/reviews/2026-09-13-adversarial-review.md`, and
`docs/reference/reviews/templates/external-deep-research.md`.

Corrections are not counted as losses: `comments_harvested` → `comments_captured`, `VACUUM INTO` →
the online backup API, the `SearchIndex` port → plain modules, "consulting practice" → D-32's
personal use, and the daily-era cadence numbers are all recorded changes of fact, not lost insight.

The restorations of `docs/reference/reviews/2026-09-15-plan-v2-review.md` were checked against the
rows judged here. That pass restored the eight declared indexes, the content- and author-state
values, the reconcile cost estimate, the coverage counters, the comment-tree wire facts, the
deep-link form, the Run-now options, the single-function scrub assertion, cassette hygiene, the
expand-and-contract recipe, the cloud-review trigger, and the concrete UI values. **None of the ten
findings below overlaps those restorations**; the earlier pass was aimed at compressed lists and at
statements false against the tree, and the residue is of a different kind: three back-references
that no longer resolve, two rules that became descriptions, and one behavioural qualification that
was dropped rather than compressed.

One row outside the eighty is reported. `v1-343` was classified `moved`, and following its home is
what exposed the highest-severity finding; it is listed in the table marked as out of set.

## Rows

| v1 id | section | disposition | class | reason |
|---|---|---|---|---|
| v1-007 | Context, decisions Q&A table | reduced | no loss | DECISIONS § 1 holds D-01…D-28 in full, each with a revisit trigger; the plan's 14-row table is a reading aid |
| v1-037 | Context, assumptions | reduced | no loss | the four facts live in D-17, D-24, D-06 and the tech-stack table |
| v1-039 | Architecture diagram | reduced | no loss | "daily" → "scheduled" is D-30; "(later) JSONL → Claude" → "(M5) … the analysis layer" is the no-model-names rule |
| v1-055 | Repository layout tree | reduced | no loss | `CONTRIBUTING.md` was never built; its role is `CLAUDE.md`, named in the portability bullet |
| v1-058 | Reference corpus, docs/ tree | reduced | no loss | the folders are restated in prose and `docs/INDEX.md` is the live inventory, checked both ways by G33 |
| v1-084 | Data model, `posts` row | reduced | no loss | "flair and flags" points at `src/insightminer/db/schema.sql`, the committed golden that G15 gates and that carries a generated column-comment section |
| v1-094 | Data model, FTS row | reduced | no loss | the trigger gating changed in revisions 0003 and 0004; a correction, and both are stated |
| v1-098 | Data model, panel corrections | reduced | no loss | every item traced: AUTOINCREMENT and the `backups` row into the data model, maintenance-only mode and the writer map into the Web-UI rows, the stale-run threshold and the operator-complete exclusions into DECISIONS § 6, exports into § 2 |
| v1-103 | Collector step 3, ladder | reduced | no loss | `revisit_ladder_days: [1, 3, 7, 30, 365]` is in `config/settings.yaml` and in D-05 |
| v1-106 | Collector step 6, finish | reduced | no loss | the digest's content moved to "From data to insight" intact; the backup wording is drift finding 24 |
| v1-107 | Budget reality | reduced | no loss | the ~4,500-request backfill estimate was disputed at the time (adversarial review E17: the collector review said ≈ 6,000, "measure on the first backfill"); D-05's revisit trigger names that measurement |
| v1-130 | Web UI, process model | reduced | no loss | "single uvicorn worker" → "single worker"; the load-bearing half (in-process job state, fetching always a subprocess) is kept |
| v1-153 | Web UI, curation controls | reduced | no loss | the revision-2 column list is stated in full in § Schema revisions as the curation migration |
| v1-164 | Testing, E2E Playwright row | reduced | no loss | UI-52 in `docs/TEST_STRATEGY.md` ("local-only, never in CI"); the plan points at that document for spec-level detail |
| v1-167 | Testing, sweeps row | reduced | no loss | the parenthetical named three retired mechanisms; G34 requires exactly that removal, and N-08, N-11 and the Alerts bullet hold them |
| v1-170 | Failure matrix, 429 row | reduced | **loss, recoverable** | `min(retry_after, 300)` now lives only in `MAX_RATE_LIMIT_WAIT_SECONDS`, and the module docstring cites a plan section that no longer holds it (finding 4) |
| v1-177 | Failure matrix, 5xx row | reduced | **loss, recoverable** | same: `30 s → 2 min → 5 min` lives only in `DEFAULT_LADDER_SECONDS` and the docstring's citation dangles (finding 4) |
| v1-183 | Failure matrix, malformed fields | reduced | no loss | NM-01 in the test strategy names the shipped node ids for the same fixtures |
| v1-186 | Failure matrix, missing from `info()` | reduced | no loss | "twice" was wrong and KI-021 corrected it; the correction is stated in the plan |
| v1-187 | Failure matrix, config validation | reduced | no loss | CF-01…CF-04 in the test strategy carry the cases with node ids |
| v1-190 | Failure matrix, clock skew | reduced | no loss | the magnitude was illustrative; the rule (all logic in the `created_utc` domain) is kept |
| v1-212 | Guard rules, source paragraph | reduced | no loss | the audited numbers have homes: GUARDS.md G10 (2,250 suppressions), DB_LEARNINGS rank 7 and 22, LEARNINGS_TRANSFER, INSIGHTS_2026-09-12 |
| v1-220 | Guard rules, zero-suppression baseline | reduced | **loss, restore** | a rule became a description, and the description disagrees with `.ratchets/suppressions.txt` (finding 2) |
| v1-233 | Gates and ratchets table | reduced | no loss | consolidation only; `docs/runbook/GUARDS.md` is the ledger and the harness page's inventory is generated from the tree |
| v1-254 | Gates, destructive-operation gate | reduced | no loss | RUNBOOK § 5 holds "a verified backup within N hours plus the `Confirmation`"; TEST_STRATEGY DB-39 and UI-44 hold the value object |
| v1-304 | Portability, CLAUDE/CONTRIBUTING/RUNBOOK | reduced | no loss | "the working agreement, the runbook, and the harness page" names what exists |
| v1-317 | Adversarial changes, smaller fixes | reduced | no loss | each of the twelve fixes traced to a home (flock-means-alive and the 2-minute `queued` rule in DECISIONS § 6, N-14, TID251, the 365-day stage, recorded purges, the LAN threat model in § 5) |
| v1-322 | Release, safety bullet | reduced | no loss | the `pre-migrate-<from>-<to>-<utc>.db` pattern is in RUNBOOK § 4; the daily/weekly counts are superseded by D-31 |
| v1-325 | Release, versioning bullet | reduced | **loss, restore** | the SemVer minor/patch convention has no home anywhere (finding 8) |
| v1-332 | Milestones, D0 row | reduced | no loss | version two's one sentence is more honest than version one's status table |
| v1-333 | Milestones, M0 row | reduced | no loss | a setup recap for work that is done |
| v1-334 | Milestones, M1a row | reduced | no loss | DECISIONS 2026-09-13 (night) holds the tranche-A detail and the eleven binding build decisions |
| v1-337 | Milestones, M1d row | reduced | no loss | `config/seed.yaml` holds the eight seed themes with their rules, and is authoritative over a prose list |
| v1-356 | Verification, item 5 | reduced | no loss | the CLI `export` row names the contents; the file names are an M2 detail |
| v1-377 | D0 walk, sub-heading | reduced | no loss | the walk is recorded in DECISIONS § 1, § 6 and § 7 |
| v1-378 | D0 walk, table | reduced | no loss | same |
| v1-379 | D0 walk, data model row | reduced | no loss | the itemized decisions are the content-state machine paragraph, stated in full |
| v1-380 | D0 walk, collector row | reduced | no loss | D-05 holds the ladder, expansions, per-post cap and budget verbatim; `config/settings.yaml` holds the values |
| v1-382 | D0 walk, prior learnings row | reduced | no loss | DB_LEARNINGS § 5 holds the four further documents and the questions raised |
| v1-383 | D0 walk, reference corpus row | reduced | no loss | superseded by the built corpus and D-27 |
| v1-384 | D0 walk, panels row | reduced | no loss | TEST_STRATEGY § 3 indexes all four panels' specs and INDEX.md routes to each record |
| v1-423 | Review harness, opening paragraph | reduced | no loss | model-name phrasing removed by rule; the register requirement (G50) added |
| v1-427 | Review harness, every ordinary PR | reduced | **loss, restore** | the review mechanism is named in no document (finding 5) |
| v1-428 | Review harness, large PRs | reduced | **loss, restore** | same (finding 5) |
| v1-430 | Review harness, mechanics | reduced | no loss | the runner was never built; DECISIONS 2026-09-14 records what was; the guard rule is in CLAUDE.md; "a panel never removes a gate" is superseded by the loosening protocol, D-29, and the quarterly review |
| v1-433 | Agent tiers, paragraph | reduced | no loss | the dropped narrative is history; the rule and the promotion rule are kept |
| v1-439 | Agent tiers, rules paragraph | reduced | no loss | "mix providers" survives in the milestone review row ("sent to more than one provider") |
| v1-441 | Workspaces, opening paragraph | reduced | no loss | D-32 settles it: personal interest, no business application |
| v1-154 | Web UI, feed wireframe | absent | no loss | verified present at `2026-09-12-ui-design-review.md` § 2 |
| v1-155 | Web UI, post-page wireframe | absent | **loss, recoverable** | it is in the same review record § 2, but the plan's retirement note says only the feed sketch is (finding 7) |
| v1-411 | Research brief, title | absent | no loss | D-13 closed 2026-09-15: the report never arrived; the external rounds took its place |
| v1-412 | Research brief, context | absent | no loss | same |
| v1-413 | Research brief, Q1 mechanical controls | absent | no loss | the controls it asked about are built and inventoried on the harness page; the successor brief's Q7 covers the same ground |
| v1-414 | Research brief, Q2 ratchet design | absent | no loss | `tools/ratchet.py` and the three-way compare are built; the design is in the enforcement panel record |
| v1-415 | Research brief, Q3 post-run invariants | absent | no loss | built in `services/invariants.py` |
| v1-416 | Research brief, Q4 agent working agreements | absent | no loss | `CLAUDE.md`, the hooks, and the harness page are the answer as executed |
| v1-417 | Research brief, Q5 mutation testing | absent | no loss | N-10 settled it; the question is no longer live |
| v1-418 | Research brief, Q6 SQLite failure modes | absent | no loss | the successor brief's Q3 asks it, and § SQLite facts holds the verified answers |
| v1-419 | Research brief, Q7 AI-Python anti-patterns | absent | no loss | the code-health family (vulture, ruff, radon, complexipy, pylint) is the answer as built |
| v1-420 | Research brief, deliverable | absent | no loss | the external-round brief's output section is the successor |
| v1-021 | Context, external research row | superseded | no loss | DECISIONS 2026-09-15: "D-13 closed. The targeted external research report … never arrived" |
| v1-024 | Context, compliance cadence row | superseded | no loss | D-16 carries an inline supersession to D-30, and the D-30 entry holds the reasoning and the sweep list |
| v1-025 | Context, GitHub row | superseded | **loss, recoverable** | the 2026-09-14 entry holds the deferral, but § 1's D-17 still states the retired plan un-annotated (finding 3) |
| v1-027 | Context, research timing row | superseded | no loss | tied to D-13, closed with it |
| v1-197 | Failure matrix, uniform staleness | superseded | no loss | N-08 holds the mechanism, the reason, and the revisit trigger |
| v1-236 | Gates, required CI on `main` | superseded | no loss | 2026-09-14: "CI and branch protection stay documentation-only until GitHub exists, and GUARDS.md § External controls says so" |
| v1-240 | Gates, test-count floor | superseded | no loss | N-09 holds the reason and the replacement; version two keeps the contradiction visible |
| v1-247 | Gates, mutation testing | superseded | no loss | N-10 holds the reason ("a blocking kill rate would be met with equivalent-mutant suppressions") |
| v1-258 | Gates, freshness anchor | superseded | no loss | N-08 |
| v1-260 | Gates, stress scenario | superseded | no loss | N-11, and the four `EXPLAIN QUERY PLAN` assertions survive with their test path in § Conventions |
| v1-291 | Workflows, daily run | superseded | no loss | D-30, with the full consequence sweep listed in the 2026-09-14 entry |
| v1-307 | Adversarial review, heading | superseded | **loss, recoverable** | the plan points at DECISIONS § 3 only; the record itself is reachable only through `docs/INDEX.md` (finding 6) |
| v1-308 | Adversarial review, central charge | superseded | **loss, recoverable** | § 3 is a table of negatives with no intro; the charge is only in the record (finding 6) |
| v1-309 | Adversarial review, gates cut | superseded | no loss | each cut is its own numbered row N-06…N-16 with a because and a trigger |
| v1-347 | Things only Wes, GitHub repo | superseded | no loss | version two's item 2 names the QNAP remote instead |
| v1-362 | Reviewers' questions, reconcile cadence | superseded | no loss | D-30 |
| v1-369 | Reviewers' questions, digest persistence | superseded | no loss | § 2's Digests row says "**supersedes** the 2026-09-12 'digest files kept 14 days'" |
| v1-386 | Appendix, retrospectives heading | superseded | no loss | all seventeen findings map onto DB_LEARNINGS' 26 ranked rows (checked one by one) |
| v1-406 | Appendix, test-strategy panels | superseded | no loss | the four panels were executed; TEST_STRATEGY § 3 indexes their specs and INDEX.md routes to each |
| v1-410 | Appendix, research brief heading | superseded | no loss | D-13 closed |
| *v1-343* | *Milestones, M0 foundation tranche (classified `moved`; out of set, re-examined)* | *moved* | **loss, restore** | *the invariant severity split was in this paragraph and is in neither of its homes; version two now states the opposite of the code (finding 1)* |

## Findings

### 1. The post-run invariants' severity split was lost, and version two states the opposite of the code — CRITICAL

*(attaches to `v1-343`, classified `moved`; the row that led here is `v1-098`)*

**Version one** (M0 foundation tranche paragraph):

> "invariants at M1a start with the compliance canary, counters-versus-deltas, structural
> population floors, and per-source freshness, and **only the first two flip a run to `failed`
> during the first 60 days**."

**Version two** (§ Silent-failure controls) drops the qualification and asserts the opposite:

> "**Post-run invariants** (violations flip the run to `failed`; each is planted through
> `insightminer run --gateway fake` by its positive control, G30). Built, in
> `services/invariants.py`: run counters equal table deltas; no `running` rows other than the
> current one; index membership equals the live rows …; every row written this run carries the
> current `normalizer_version`; unknown upstream enum values are counted …; **population floors** …;
> **per-source freshness** …"

**The code disagrees.** `src/insightminer/services/invariants.py`:

> "* **Severity is the whole status story.** ``WARNING`` makes the run ``partial``, ``FAILURE`` …"
> and `WARNING = "warning"`: *"The run ends ``partial`` (amber): the floors, freshness, FTS
> membership, DB-48."*

Five of the seven built invariants raise `Severity.WARNING`; only `counters_equal_table_deltas`
and `no_other_running_rows` raise `Severity.FAILURE`. `services.runs.resolve_status` reads only
`.severity`.

**The named homes do not hold it either, and what they hold is stale.** `docs/TEST_STRATEGY.md`
§ 4 says *"Only the first two flip a run to `failed` during the first 60 days; the others are
`partial`/amber"*, and `docs/runbook/GUARDS.md` repeats *"start as `partial`/amber for the first 60
days, as the plan says"* — a pointer back to a plan that no longer says it. There is **no 60-day
clock anywhere in `src/`** (grepped): the split is permanent by severity, not temporary by date.
So three surfaces now give three different answers, and the plan gives the one that is wrong.

**Why it is load-bearing.** M1c and M1d each add invariants (scrub, reconcile-age, `comments_captured`,
`authors` counts). A builder reading the plan will ship them as failures, which turns a normal amber
run red and invites the exact response the project forbids — weakening the check to get green.
It also touches the compliance story: the reconcile-age invariant is the one that makes "compliance
cannot lapse quietly" true, and whether it fails or ambers is a decision, not a detail.

**Fix — restore to § Silent-failure controls, replacing the parenthetical:**

> **Post-run invariants.** Severity, not the list, decides the status: `counters_equal_table_deltas`
> and `no_other_running_rows` are failures and flip the run to `failed`; the population floors,
> per-source freshness, index membership, and normalizer-version stamping are warnings and close the
> run `partial`, amber on the pill (`services/invariants.py`, read by `services.runs.resolve_status`).
> Whether any of the amber set is promoted to a failure is open: version one gave it sixty days, the
> code carries no clock, and the call belongs at the M1d retrospective with seven runs behind it.

Sweep with it: `docs/TEST_STRATEGY.md` § 4 and `docs/runbook/GUARDS.md` both say "for the first 60
days", which no code implements.

### 2. The zero-suppression baseline stopped being a rule and became a description the ratchet file contradicts — HIGH

**Version one** (guard design rules):

> "**Zero-suppression baseline** | Greenfield means the suppression and skip ratchets **start at
> zero**, and any exception is printed on every run"

**Version two**, same row:

> "Zero-suppression baseline | Suppression and skip ratchets **started at the measured baseline with
> no backlog**, and any exception is printed on every run"

**The home says otherwise.** `.ratchets/suppressions.txt`: `noqa=11`, `type_ignore=7`,
`pragma_no_cover=5`, `mypy_overrides=1` — twenty-four grandfathered entries. `.ratchets/skips.txt`
is `count=0`. DECISIONS 2026-09-15 has an open recommendation about exactly them: *"Suppression
review dates (the 24 grandfathered suppressions): recommendation, at the quarterly guard review,
give each suppression ceiling a `hard_after` date three months out through the loosening path."*
A backlog awaiting expiry dates is a backlog.

**Why it matters.** This row exists because of one audited number in the earlier project:
*"2,250 grandfathered entries across 13 baseline and allowlist files"* (`GUARDS.md` G10) becoming a
permanent exemption. A rule stated as a past-tense fact cannot be applied to the next ratchet, and
the fact as stated is not true. This is the failure mode the row was written to prevent, one
generation earlier.

**Fix — restore the rule and name the ceiling as the home:**

> Zero-suppression baseline | The skip ratchet starts at zero and stays there; the suppression
> ratchet started at the counts in `.ratchets/suppressions.txt` with a rule code on every entry, and
> those grandfathered entries are a backlog to clear or to re-approve with an expiry date at the
> quarterly guard review, never a permanent exemption.

### 3. DECISIONS § 1 still states the retired GitHub plan as live, in two rows — HIGH

**Version one** carried the amendment inline on its Version-control row:

> "*(Amended 2026-09-14: GitHub deferred; the first remote is a bare repository on the new QNAP
> reached over SSH when it arrives, milestone MB; until then local only …)*"

**Version two** moved that row to the log, where the amendment is not. `DECISIONS.md` § 1:

> "| D-17 | 2026-09-12 | GitHub | Wes creates the empty private repo `WhowellGit/insightminer` and
> pastes the URL; the agent connects, pushes, sets branch protection | The repo is shared with a
> coworker … |"
> "| D-26 | 2026-09-12 | Version control | Local git from the first commit; GitHub remote added as
> soon as it exists and doubles as the off-site backup … |"

Neither carries a supersession marker, although D-15, D-16 and D-25 in the same table carry exactly
that kind of dated parenthetical. The superseding content *is* in the log, in the 2026-09-14 entry
("Remote: GitHub deferred; a bare git remote on Wes's QNAP is the first backup"), so the
supersession is real — but the reader lands on § 1 first, because the plan's own choices table says
the load-bearing choices "are registered in `docs/decisions/DECISIONS.md` § 1 with their revisit
triggers". A session reading D-17 will set up GitHub and branch protection.

**Nothing catches this.** G34's retired-claims scan explicitly excludes this file ("everything under
`docs/` except `reference/`, `insights/`, and this file"), and the append-only gate permits the fix
("a dated parenthetical may be inserted into a line").

**Fix — annotate both rows in place, in the style D-15/D-16 already use:**

> D-17 … *(superseded 2026-09-14: GitHub deferred; the first remote is a bare repository on the
> QNAP over SSH, milestone MB; CI and branch protection are documentation-only until GitHub exists)*
> D-26 … *(amended 2026-09-14: the QNAP bare repository is the first remote; the pre-push hook has
> run `make check` since 2026-09-14)*

### 4. The retry numbers left the plan, and `core/retry.py` still cites the plan as their source — MEDIUM

**Version one**, failure matrix: "Sleep `min(retry_after, 300)` via injected clock"; 5xx row: "our
outer retry (30 s → 2 m → 5 m via fake clock)"; Resilience: "the outer retry ladder (30 s, 2 min,
5 min)".

**Version two** generalizes all three: "Sleep the bounded wait via the injected clock"; "then the
outer ladder via the fake clock"; "the outer retry ladder around every page, tree, and info batch".
By the number-homes rule this is right — the numbers belong in the code, and they are there
(`DEFAULT_LADDER_SECONDS = (30.0, 120.0, 300.0)`, `MAX_RATE_LIMIT_WAIT_SECONDS = 300.0`).

**But the reference now runs backwards into nothing.** `src/insightminer/core/retry.py`:

> "Sources: docs/PLAN.md "Resilience to outages" (**the 30 s / 2 min / 5 min outer ladder**, … the
> ``Retry-After`` pause capped by the wall-clock ceiling), the failure-mode matrix (**429: sleep
> ``min(retry_after, 300)``**)"

The module names the plan as the authority for three numbers the plan no longer contains. This is
the same shape as KI-025 (a module citing the plan for a schedule the plan had changed) and as drift
findings 23 and 24 — and the same blind spot: G55 checks identifiers in documents against the tree,
never a docstring's citation of a document.

**Fix — a pointer in each direction, no restored number:** the plan's Resilience sentence reads
"the outer retry ladder (`core.retry.DEFAULT_LADDER_SECONDS`)" and the 429 row reads "sleep the
bounded wait (`core.retry.MAX_RATE_LIMIT_WAIT_SECONDS`)"; the docstring's Sources line stops naming
the plan for the three numbers and names the constants below it instead.

### 5. The ordinary-change review has no named mechanism in any document — MEDIUM

**Version one:**

> "Every ordinary PR | One fresh-context review pass over the diff at medium effort (**the built-in
> `/code-review` skill**, which Wes can also run with `--comment` to post findings inline) …"
> "Large PRs, milestone merges | Wes may trigger the built-in multi-agent cloud review of the branch
> or PR (**`/code-review ultra`**) …"

**Version two:** "One fresh-context review pass over the diff"; "the built-in multi-agent cloud
review of the branch". `grep -rn 'code-review' docs/ CLAUDE.md` returns nothing, and the runbook has
no section for ordinary review (§ 6 is the quarterly guard review, § 7 the external packet). The
external round, the panels and the register all name their mechanism; the one that fires on every
change names none, which makes it the weakest row in the table and the easiest to skip.

**Fix — restore the tool names to the two rows:**

> Every ordinary change | One fresh-context review pass over the diff, the built-in `/code-review`
> skill at medium effort, with `--comment` to post findings inline | Advisory unless a P0 is found
> Large changes and milestone merges | Wes may trigger the built-in multi-agent cloud review of the
> branch (`/code-review ultra`); it is user-triggered and billed, so the harness only recommends it

### 6. The adversarial review's central charge is reachable only through the router — LOW

**Version one:**

> "The adversarial reviewer's central charge was that the plan cites the earlier project's 'hold the
> count' rule and then ships roughly 28 gates and 15 invariants on day zero, several of them
> unfalsifiable. That charge is correct. The gates table above is the menu; the shipped set starts
> smaller and grows only on recurrence."

**Version two** keeps the conclusion and points elsewhere for the charge: "The shipped set, each
with a ledger row; the M0 menu that the adversarial review cut down is history (DECISIONS § 3 and
the 2026-09-13 entries)." DECISIONS § 3 is a table of negatives whose intro is one line ("do not
rebuild these levers"); it does not hold the charge. The charge is in
`docs/reference/reviews/2026-09-13-adversarial-review.md` ("WHY_THE_GUARDS_EXIST 'hold the count
until one has a fired-in-anger record' → 28+ gates on day 0, all with someone else's birth
incident"), which `docs/INDEX.md` routes to for "tempted to add a gate" — so a reader following the
router arrives, and one following the plan's own pointer does not.

**Fix — add the record to the plan's pointer:** "(DECISIONS § 3, the 2026-09-13 entries, and
`docs/reference/reviews/2026-09-13-adversarial-review.md` § C)".

### 7. The version-history note understates where the wireframes live — LOW

**Version two**, version history: "the two UI wireframes (git history; **the feed sketch** is in
`docs/reference/reviews/2026-09-12-ui-design-review.md`)".

Both sketches are in that record, under § 2 "Wireframes (old-reddit density)": "### Feed (`/`,
`/r/{sub}`, `/t/{slug}` share this layout)" and "### Post + comments", the second richer than
version one's (it carries the selftext block, the "score/comments as of" line, the `[OP]` badge,
"(2 children)", and the tombstoned subtree). Nothing was lost; the plan's own note sends an M2
builder to git history for a sketch that is one file away.

**Fix:** "the two UI wireframes (both sketches are in
`docs/reference/reviews/2026-09-12-ui-design-review.md` § 2)".

### 8. The SemVer convention has no home — LOW

**Version one:** "SemVer (**minor for new commands or migrations, patch for fixes**); `CHANGELOG.md`;
git tags". **Version two:** "SemVer; git tags. No changelog ceremony beyond the version string unless
N-19 is ruled otherwise." The changelog half is a recorded decision (N-19) and correctly dropped; the
minor/patch convention is not recorded anywhere (`grep -rn 'SemVer' docs/` finds only these two
lines). It is small, but it is a settled convention that a release will otherwise re-derive, and the
version string is user-agent-visible to Reddit.

**Fix — one clause back into the Versioning bullet:** "SemVer, minor for a new command or a
migration and patch for a fix; git tags."

## New units

The twenty-two version-two units with no version-one ancestor. **None contradicts a carried
version-one unit without a recorded decision behind it.** Three are worth a sentence each.

1. **Front-matter contract** — no contradiction; a mechanism (G55) version one had no equivalent of.
2. **"From data to insight"** — no contradiction; it assembles D-09, D-02 and the denominator rule into prose.
3. **Built-versus-planned State columns** — no contradiction; it replaces version one's milestone recaps with a per-row fact.
4. **`workspaces` table row** — no contradiction; version one's Workspaces section already said revision 1 carries the table, the data-model table simply lacked the row.
5. **`backups` table row** — no contradiction; version one (v1-098) already said the table ships in revision 1; `schema_rev` and `table_counts_json` are additions.
6. **Schema revisions 0001–0004 paragraph** — a renumbering, not a contradiction: version one's "revision 2" is version two's curation migration at M2, with the same three columns.
7. **D-31 backup retention** — supersedes version one's "7 daily / 4 weekly plus 3 pre-migration" (v1-322), and does so through a recorded decision with `7 daily` in the retired-claims table. Legitimate.
8. **Workspaces "What is built and what is not"** — the one tension: version one implied a second domain is nearly free ("no migration is needed when the second domain arrives"), version two says it "costs a bounded amount of code, not just config". Both are true (no migration ≠ no code), and version two is the honest reading; no decision is contradicted.
9. **Workspaces "Leaving a domain"** — new path, no contradiction.
10. **Workspaces "What a second domain should expect"** — new limits with the deferred levers recorded 2026-09-15; no contradiction.
11. **OVERVIEW and HARNESS named as companions** — no contradiction.
12. **Version history table** — no contradiction; it is the retirement ledger this review reads.
13. **Review-harness row "A milestone or a design freeze"** — supersedes version one's unbuilt `tools/review/` runner; recorded in DECISIONS 2026-09-14 ("External reviewers").
14. **Web-UI "Writes" row** — reverses version one's `mode=ro` page routes, but N-07 records the reversal and version one already carried the note.
15. **Gates row "Documentation gates"** — no contradiction; it absorbs version one's single doc-currency row.
16. **Gates row "Dependency pins" (G53)** — no contradiction; version one said "PRAW 8.x" and this pins the tested major.
17. **Gates row "Schedule contract"** — no contradiction; it implements D-30 and KI-024.
18. **Gates row "Review-only ceiling"** — no contradiction; it is the mechanism behind version one's "every gate must satisfy these rules".
19. **Known-patterns row "a hook present but never installed"** — no contradiction; born from an incident version one predates.
20. **Workflows row "Staleness check"** — no contradiction; version one's deployment stage already had the hourly `doctor` job, at the daily-era threshold D-30 and KI-024 corrected.
21. **Workflows row "Guard review"** — no contradiction; version one's sweeps row carried "quarterly the guard pedigree review".
22. **Milestones D0 framing** — no contradiction; it matches version one's own walk table, which showed UI routes "In progress" and milestone sequencing "Pending".

## What I could not check

- Whether the scratchpad `PLAN_v1.md` is byte-identical to version one as committed. I read it as
  given and did not diff it against `git log --follow docs/PLAN.md`.
- The 295 `carried` and 69 `moved` rows, except `v1-343`, which a `reduced` row led me into. Finding
  1 is evidence that the `moved` set deserves the same pass: a row can be "moved" to a home that
  holds most of the paragraph and not the one clause that mattered.
- Whether `docs/decisions/DECISIONS.md` § 1 holds further un-annotated superseded rows beyond D-17
  and D-26. I checked the rows the eighty pointed at; nothing scans this file (G34 excludes it), so
  a full § 1 pass against the later dated entries is a separate job and I recommend it.
- Whether the four 2026-09-13 panel records' specs still match the code. I resolved node ids only
  where a judged row depended on them (NM-01, CF-01…04, UI-52, DB-39, DB-50, FR-01).
- I did not run `make check`, and I made no edit to the repository.

## Verdict

| class | rows |
|---|---|
| no loss | 70 |
| loss, recoverable | 6 (v1-170, v1-177, v1-155, v1-025, v1-307, v1-308) |
| loss, restore | 4 (v1-220, v1-325, v1-427, v1-428) |
| supersession unreal | 0 |
| *out of set* | *1 (v1-343, `loss, restore`)* |

By severity: one CRITICAL, two HIGH, two MEDIUM, three LOW.

**The claim does not hold.** Two of its three clauses survive: every `absent` row is superseded by a
recorded decision or retired with a home that exists, and every supersession is real in the sense the
claim means — the decisions log holds the content, in full, with the reasoning and a revisit trigger,
not merely a mention. The first clause fails. Four reduced rows lost content that lives nowhere a
builder would read, and the paragraph behind finding 1 lost a behavioural qualification that version
two then replaced with its opposite.

The pattern across the ten is narrow and worth naming: **version two's compression is sound, its
back-references are not.** Three findings (1, 4, 6) are pointers that no longer resolve — a plan
sentence pointing at a home that does not hold the fact, a module pointing at a plan section that
lost the numbers, a section pointing at a table with no intro — and two (2, 3) are rules or decisions
that stopped being stated as such. That is the same class of defect as drift findings 23 and 24 and
as KI-025, and none of the existing gates covers it: G55 resolves identifiers in documents against
the tree, G34 catches retired phrases stated as live, and neither reads a citation in either
direction.

**Confidence: high** for findings 1, 2, 3 and 4 — each was verified by reading the cited file, and
finding 1 was confirmed twice (the severity constants and `resolve_status`, then a grep proving no
60-day clock exists). **Medium** for 5, 6 and 8, which turn on a judgement about what a builder or
operator needs rather than on a contradiction. **High** for 7, which is a verified misstatement in
the plan's own retirement note.

**Recommendation:** restore finding 1 before any M1c invariant is written, because a builder acting
on the plan as it stands will ship an invariant at the wrong severity and the plan will have caused
it. Findings 2 and 3 next: both are rules that decayed into descriptions, which is the failure this
project's whole method exists to prevent. Findings 4 through 8 are one short editing pass and can
travel together. Consider one further gate, born from findings 1, 4 and 6: a check that a citation
resolves in both directions — a document that names a home must be findable from that home, and a
docstring that names a plan section for a fact must find the fact there. Confidence that such a gate
is worth building: medium; it would have caught three of these ten and KI-025 as well.
