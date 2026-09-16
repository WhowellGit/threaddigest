# The version-two changes, scrutinized (2026-09-16)

## Claim under test

Each of the eight changes version two made relative to version one was scrutinized to the
standard version one's own rounds met: risks named, alternatives weighed, mirrors swept, the
code consistent with the prose, and a revisit trigger recorded.

The claim does not stand for all eight. Five changes held with gaps, two held, and one
(the cadence re-derivation, change 1) did not hold: three thresholds the cadence moved were
re-derived and bound by tests, and four more were not, while the decision itself carries no
revisit trigger.

## Method

For each change I read what version one said (the copy at
`/private/tmp/claude-501/-Users-wesmax-repos-insightminer/1dc53ec0-3821-41aa-a9e2-a0d2f2e742ac/scratchpad/review-2026-09-16/PLAN_v1.md`,
which is version one as annotated through 2026-09-15), what version two says, what
`docs/decisions/DECISIONS.md` records as the reason and the trigger, and then tried to break
it: arithmetic against `config/settings.yaml` and the launchd plists; the code that implements
the claim (`core/deletion.py`, `core/milestones.py`, `core/budget.py`, `core/digest.py`,
`core/themes.py`, `services/invariants.py`, `services/doctor.py`, `db/schema.sql`, `cli.py`);
and a grep of the whole tree, `src/` and `deploy/` included, for mirrors that still state the
old fact. I ran `uv run pytest tests/deploy/test_schedule_contract.py -q` (5 passed) to confirm
the cadence bindings that do exist are live. I edited nothing.

## Changes

### 1. The twice-weekly cadence (D-30) and the thresholds re-derived under it

**Version one said** (as annotated): the schedule was already twice weekly in the annotated
copy, but its derived numbers were the daily-era ones — `doctor [--alert-if-stale 36h]`
(v1:200), "a 600-request day takes ~10 minutes", searches run "daily" (v1:192), "the last
complete reconcile is within 48 h plus a 12 h grace period" (v1:423), "Daily run | daily,
automated" (v1:456).

**Version two says**: Monday and Thursday 06:30 with reconcile and a backup on every run
(PLAN.md:32); a staleness threshold "longer than the longest gap between scheduled runs"
(PLAN.md:194); `reconcile.full_sweep_every_hours` shorter than the gap so every run is a full
sweep, with `reconcile.tier_max_age_hours` as the fallback (PLAN.md:184); the reconcile-age
invariant tied to the schedule by test (PLAN.md:400).

**Reason and trigger recorded**: DECISIONS.md:218 gives the reason (Wes reads on his own
rhythm; the listing cap stays comfortable; the seven-digest validation finishes in under a
month) and a list of nine consequences to sweep. D-31 (:226), D-32 (:227), the workspace
direction (:228) and the deferred levers (:229) each carry a **Revisit when**. D-30 does not.

**Refutation.** Four of the nine consequences are enforced by
`tests/deploy/test_schedule_contract.py` (schedule, doctor default, both reconcile keys) and
that file is green. Of the rest:

- The **per-run request budget** was never re-derived, and version two added a claim about it
  that is false (finding 1). Version one made no such claim.
- The **revisit ladder**, named in D-30's own consequence list, did not move in either of its
  two homes and the collapse it now suffers is stated nowhere (finding 4).
- The **`gone` window** (two `info()` omissions, `GONE_AT_MISSES = 2`) roughly quadrupled and
  the two live documents that state a number still state the daily-era ones (finding 2).
- **Per-source staleness** is counted in runs, not days, so its wall-clock latency quadrupled
  silently (finding 12).
- Residues survive in `src/` that the widened retired-claims scan does not catch (finding 8),
  and the schedule's own README states a duration that contradicts D-30 (finding 9).

### 2. All use is personal and non-commercial (D-32)

**Version one said**: the commercial-use stance was an open item Wes was handling outside the
plan (v1:580, "(3) and (4) the compliance bounds and the commercial-use stance"); the second
domain was "AI adoption among small and medium businesses, for a consulting practice" (v1:687).

**Version two says**: "a personal project of a long-time editor, with no business application"
(PLAN.md:13); "commercial use only under a separate written agreement (not sought: all use here
is personal)" (PLAN.md:21); a choices-table row "Use | Personal interest only, for every
workspace" (PLAN.md:40); "No commercial use of any output" (PLAN.md:60); both domains on the
same non-commercial footing (PLAN.md:202). `docs/OVERVIEW.md:74` and the memory snapshot agree.

**Reason and trigger recorded**: DECISIONS.md:227 with **Revisit when:** any output would serve
a business.

**Refutation.** The sweep is good but incomplete: two live lists still ask the settled question
(finding 7). The decision also sits outside the enforcement inventory entirely — it is a rule
with no mechanical enforcer and no row in the working agreement's rules table, so it is not
counted in the review-only ceiling either (finding 16). The plan's choices table cites it as
"(Wes, 2026-09-15)" rather than "(D-32)", so a reader cannot route from the table to the entry;
the same is true of the cadence row's sibling decisions (finding 3's second half).

### 3. Premiere Pro first, workspaces the designed option, instances acceptable

**Version one said**: "Wes expects to point the same system at other niches within a month or
so" (v1:687), with the workspace-aware loop implied for the near term.

**Version two says**: version one focuses on Premiere Pro only; the run loop and the switcher
land when a second workspace is wanted; a separate instance is an equally acceptable shape;
leaving a domain is archive/delete or export plus a fresh data directory (PLAN.md:196–208).

**Reason and trigger recorded**: DECISIONS.md:228, **Revisit when:** a second workspace is
requested.

**Refutation, schema check.** The schema matches the claim. `workspaces` exists with `slug`,
`ranking` (default `distinct_authors`) and `digest_settings_json`
(`src/insightminer/db/schema.sql:22`); `workspace_pk` is on `subreddits`, `searches` and
`themes` with per-workspace uniqueness (`schema.sql:17,18,20`) and an index each
(`schema.sql:33–35`); `post_sources` deliberately carries no workspace column
(`schema.sql`, `post_sources`), so a post reaches a workspace through the source join, exactly
as PLAN.md:198 describes; `ranking` and `digest_settings_json` are written by the migration and
read by nothing in `src/`, which is what PLAN.md:200 claims. The path out is stated with its
cost. Two gaps: the stated cost of a second workspace omits the shared-source sweep (finding
11), and one new sentence overstates what deleting the database discharges (finding 5).

### 4. The high-volume levers deferred with triggers

**Version one said**: nothing; the levers and the very-large-subreddit case are new in version
two.

**Version two says**: a very large subreddit exceeds the listing cap at any cadence, so
completeness is not available there and the design does not pretend it is; two levers wait for
their trigger — a daily cadence (a configuration change) and a per-workspace ingest filter
(needs its own design round) (PLAN.md:206).

**Reason and trigger recorded**: DECISIONS.md:229, trigger "the second workspace's sources
being chosen with one that exceeds the cap".

**Refutation.** The trigger is observable: `stop_reason='cap'` and `gap_suspected_at` are
recorded by the sweep (PLAN.md:181, KI-018, `core/paging.py::gap_suspected`) and surfaced in
the digest. The honest statement that completeness is unavailable at any cadence is a real
improvement on version one. One gap: the trigger is keyed on a *second workspace's* sources,
while the same signal can fire for workspace one (adding r/AfterEffects or r/DavinciResolve
under D-01, or growth in r/premiere), and D-30 has no trigger of its own to receive it
(finding 3). The empirical premise under the whole cadence — "the busiest target produces tens
of posts a day" — has no source and no verification point (finding 14).

### 5. "From data to insight" against the ranking and digest code

**Version one said**: the same facts, scattered through the decisions table (v1:26), the
collector's step 6 (v1:188) and the adversarial-changes appendix (v1:488).

**Version two says**: one section (PLAN.md:42–60) gathering ranking, themes, the two discovery
signals, revisiting, denominators, live-only search, workspace scoping and the non-goals.

**Refutation, code check.** It matches the code closely:
`core/digest.py:127` `_rank_key = (-distinct_authors, -comments, -score, post_id)` and
`rank_posts` is the only ranking function; every count is a `Count` with its population
(`digest.py:76`); `UntaggedSection.min_distinct_authors` defaults to 3 with a validator that
refuses a listed post below it (`digest.py:169–191`); `RisingPhrasesSection.baseline_weeks`
defaults to 4 (`digest.py:208`); themes compile three rule groups
(`match/exclude/only_in`), four kinds (`keyword/regex/flair/subreddit`), four scopes, a
300-character cap and a one-second regex timeout, with `MATCHER_VERSION` folded into
`rules_hash` (`core/themes.py:38–48,129`); the FTS indexes are over the live-only views
(`schema.sql`). The identity-coverage and tree-completeness fields are genuinely absent from
the model, which is what PLAN.md:46 says (they arrive at M1d). The one substantive problem is
the third clause of the one question (finding 10).

### 6. The built/planned marks

**Version one said**: no state column; the module map had four columns (v1:128).

**Version two says**: a fifth "State" column (PLAN.md:126–142) and a state per CLI command
(PLAN.md:212–223).

**Refutation, ten "built" marks sampled, all true.** `core.normalize` (crosspost parent reduced
to `{id, subreddit}`, KI-016 fixed); `core.deletion` (state machine with `GONE_AT_MISSES`);
`core.paging` (`plan_stop`, `gap_suspected`, `removal_candidates`); `core.milestones`
(`next_check`); `core.themes` (as above); `core.budget` (`Budget`, `tree_cost`, reserve);
`core.retry`; `core.digest` ("built, not yet assembled from the DB" — the module is pure and
has no DB reader); `adapters.reddit_fake` (a package); `adapters.notify` (`MacNotifier` via
`osascript`, `LogNotifier`, `NullNotifier`, `FakeNotifier`, and no ntfy, exactly as the row
says); `db.*` (engine, schema, schema.sql, schema_dump, repo, ownership, fts, backup, migrate,
migrations 0001–0004); `services.*` (lock, runs, collect, sweep, seed, invariants, doctor,
migrate — the eight named); `cli` (`run`, `doctor`, `db init/upgrade/current`,
`config validate` and nothing else). The seven built invariants named at PLAN.md:400 are
exactly the seven exported by `services/invariants.py`. The `doctor` row's fifteen checks all
exist in `services/doctor.py`.

**Five "planned" marks sampled, nothing claims them built.** `adapters.reddit_praw` (no file;
every mention in `docs/` carries "tranche B"); `web.*` (no package); `insightminer report`
(M1d) and `export` (M2) (absent from `cli.py`); `db downgrade/backup/restore/...` (absent from
`cli.py`; `db/backup.py::restore` is a library function, not a command, which is what the row
implies); the M1b/M1c/M3 invariants (absent from `invariants.py`). This change held.

### 7. Backup retention (D-31)

**Version one said**: "Keep the last 3 pre-migration backups plus 7 daily / 4 weekly
`VACUUM INTO` backups" (v1:498) and "no backup older than 14 days is retained" (v1:487) — two
statements external round one flagged as contradictory.

**Version two says**: the database is the long-term archive; one online-backup copy per
scheduled run taken after reconcile; the two most recent post-reconcile copies plus the
off-machine copy and the last few pre-migration copies; pruning is an M1d blocker and until it
lands `retention.backups_days` is the configured bound and the compliance canary asserts file
ages (PLAN.md:462).

**Reason and trigger recorded**: DECISIONS.md:226, with mirrors named and **Revisit when:** a
restore drill needs a point older than the kept copies. `F-05` in the live-facts table
(DECISIONS.md:286) pins the literal "two most recent post-reconcile copies" in the plan and the
runbook, and `7 daily` is a retired claim (DECISIONS.md:265). The contradiction version one
carried is genuinely gone.

**Refutation.** The interim control named twice does not exist (finding 6), and the schema's
own data dictionary still names the retired backup kinds (finding 8b). `retention.backups_days`
kept its daily-era value of 14 while the policy above it tightened to two copies (about four
days), so the configured bound and the decided policy differ by roughly a factor of three; that
may be deliberate, but nothing says so.

### 8. The intent reframed around one question

**Version one said**: "Insight Miner exists to make managing Premiere Pro complaints easier"
with the one question as a second sentence (v1:5).

**Version two says**: the one question first — "what are people struggling with, how many
distinct people, and for how long" — then the method, the focus, and the non-goals
(PLAN.md:13–15). `F-03` pins the sentence in the plan and the overview.

**Refutation.** Clauses one and two are served everywhere: themes answer "what", the ranking
function answers "how many distinct people" and refuses every proxy. Clause three is not:
the section that claims to answer it answers a different question (finding 10), and the M1d
acceptance test (seven digests read against Reddit) does not exercise it.

## Findings

**1. HIGH — Version two asserts the full reconcile sweep fits the per-run budget through the
first year; against the shipped configuration it stops fitting around month seven.**
`docs/PLAN.md:184`: "roughly eight hundred requests at the four-month mark and about two and a
half thousand at one year … so a full sweep fits `budget.per_run_requests` through the first
year." `config/settings.yaml:5` sets `per_run_requests: 1500` (reserve 100), and `cli.py:469`
makes that one pool for the whole run, counted for every HTTP response
(`core/budget.py` docstring). At a hundred items per request, 1,500 requests covers 150,000
items; the plan's own figures put the store at ~80,000 items at four months and ~250,000 at a
year. Version one made no fit claim — it said the opposite ("when a full sweep would exceed the
configured budget it falls back to tiers", v1:186) — and version two keeps that hedge in the
same paragraph, so the section contradicts itself. This is a compliance surface: when the
sweep does not fit, purge latency moves to the 8-day and 35-day tiers. Nothing re-derived
`per_run_requests` under D-30, where a run now covers three to four days of new posts and trees
as well as the sweep. *Fix:* in `docs/PLAN.md` § Collector algorithm step 4, replace the fit
claim with the month at which the estimate crosses `budget.per_run_requests`, and either raise
the configured budget or state that the tier fallback is expected from that month.

**2. HIGH — The deletion-to-`gone` window roughly quadrupled under D-30 and the two live
documents that carry a number still carry the daily-era figures.**
`src/insightminer/core/deletion.py:GONE_AT_MISSES = 2`: an item absent from `info()` needs two
omissions to be declared `gone` and scrubbed, and reconcile runs once per scheduled run, so the
window is up to one gap plus one more gap — about seven to eight days, against about two days
at a daily cadence. `docs/decisions/DECISIONS.md:49` re-derives the bound as "scrubbed by the
next scheduled run, at most about four days plus the run after the deletion", which reads as
the single-observation path and is ambiguous about the two-omission path. Meanwhile
`docs/TEST_STRATEGY.md:331` (§ 6 item 9) still asks Wes to "confirm the compliance bounds as
written: … per-tier reconcile ages 60 h / 8 d / 35 d, real purge latency 48–72 h", where the
shipped `under_30d` bound is 120 hours (`config/settings.yaml:16`, KI-026), and § 6 item 12
still offers "accept up to ~4 days" for exactly this path. The compliance bounds are listed on
`docs/recent/STATUS.md:41` as awaiting Wes "now re-derived under the twice-weekly cadence";
he would be confirming superseded numbers. *Fix:* rewrite `docs/TEST_STRATEGY.md` § 6 items 9
and 12 to the shipped bounds and state the two-omission window explicitly in
`docs/decisions/DECISIONS.md` § 2's purge-latency row.

**3. HIGH — D-30, the largest change in version two, carries no revisit trigger, and three of
the plan's cited decisions are not where the plan says decisions live.**
`docs/decisions/DECISIONS.md:6` states the log's rule: "each entry carries a date and a
**revisit when**". D-31 (:226), D-32 (:227), the workspace direction (:228) and the deferred
levers (:229) each carry one; the D-30 ruling (:218) ends "Backups: two post-reconcile copies
are enough" with no trigger. `docs/PLAN.md:23` tells the reader that "the load-bearing choices
are registered in `docs/decisions/DECISIONS.md` § 1 with their revisit triggers" and then lists
Cadence (D-30) in that table — but D-30, D-31 and D-32 are dated bullets in later sections, not
§ 1 rows, and § 1 is where the revisit column lives. Nothing mechanical checks that a decision
has a trigger (`tools/doc_policy.py` checks front matter, append-only diffs, mirrors and the
facts table), so this is review-only and the review missed it. The natural trigger already
exists as a signal: a run recording `stop_reason='cap'`. *Fix:* add a dated parenthetical to
the D-30 bullet giving its revisit trigger (a capped sweep on any enabled source, or a
seven-digest reading that finds the gap too long), and correct `docs/PLAN.md` § Context's
sentence to say where post-§1 decisions live.

**4. MEDIUM — The revisit ladder, named in D-30's own consequence list, did not move in either
of its two homes, and the collapse it now suffers is stated nowhere.**
`docs/decisions/DECISIONS.md:218` lists "the revisit ladder's first rungs (effectively the next
run)" among the consequences to sweep. `config/settings.yaml:11` still reads
`revisit_ladder_days: [1, 3, 7, 30, 365]`, `core/milestones.py:18` still declares
`DEFAULT_LADDER_DAYS = (1, 3, 7, 30, 365)` citing "docs/PLAN.md, step 3", D-05 still records
"ladder 1/3/7/30/365 d", and `docs/PLAN.md:183` describes the ladder with no cadence note.
`core/milestones.py:44–48` advances exactly one rung per check and never skips a rung already
in the past, so at two runs a week a post consumes the 1-day, 3-day and 7-day rungs on three
successive runs: the ladder becomes "re-fetch at every run for three runs", and the rungs no
longer mean the days they are named after. Separately, the ladder has two homes — a validated
setting (`settings.py:178`) and a code constant — with no caller yet joining them
(`grep` finds no `next_check` call site), which is the KI-024 class of defect ("a configured
value has a code twin"), and the live-facts table does not list the pair. *Fix:* in
`docs/PLAN.md` § Collector algorithm step 3 state what the rungs mean at this cadence, and add
the ladder to the live-facts table in `docs/decisions/DECISIONS.md` with
`yaml:config/settings.yaml:revisit_ladder_days` as its home before M1c wires it.

**5. MEDIUM — "Deleting the database also discharges the deletion obligations that attached to
its rows" contradicts the project's own backup bound.**
`docs/PLAN.md:204` (a version-two sentence; version one has no equivalent). But
`docs/decisions/DECISIONS.md:52` records that a backup made before a scrub holds the text until
it ages out, and `docs/PLAN.md:462` says the same. Deleting the live database leaves every
retained copy and export untouched. *Fix:* amend that sentence in `docs/PLAN.md` § Workspaces →
"Leaving a domain" to name the backups and exports that must also go.

**6. MEDIUM — D-31's interim control does not exist: nothing reads `retention.backups_days` and
no canary asserts file ages, yet both are stated in the present tense.**
`docs/PLAN.md:462` and `docs/decisions/DECISIONS.md:226`: "until it is built,
`retention.backups_days` in `config/settings.yaml` is the configured bound and the compliance
canary asserts file ages." `grep -rn "backups_days" src/` finds only the settings declaration
(`settings.py:161`); no code prunes, and no test under `tests/` asserts a backup file's age.
The value is therefore a number in a file that bounds nothing, and D-31's "compliant by
construction" rests on it. The exposure is currently nil because per-run backups are themselves
unbuilt, which makes this cheap to fix now and expensive to discover at M1d. *Fix:* in
`docs/PLAN.md` § Release, mark both the bound and the canary as planned with the milestone, and
add the file-age assertion to the M1d blocker list on `docs/recent/STATUS.md`.

**7. MEDIUM — D-32 settled the commercial-use stance; two live lists still ask it as open.**
`docs/decisions/DECISIONS.md:122` (§ 7 "Pending Wes", item 4) and `docs/TEST_STRATEGY.md:331`
(§ 6 item 16) both still carry "Commercial-use stance for a coworker at the company that makes
Premiere Pro". The convention for closing such an item is already established in both files
(§ 7 item 2 struck through, item 5 annotated; § 6 item 10 annotated "cut, decided 2026-09-13"),
so this is a missed sweep, not a policy question. *Fix:* annotate
`docs/decisions/DECISIONS.md` § 7 item 4 and rewrite `docs/TEST_STRATEGY.md` § 6 item 16 to
cite D-32.

**8. MEDIUM — Cadence and retention residues survive in `src/` where the widened retired-claims
scan cannot see them.**
(a) `src/insightminer/db/schema.py:237`: "A saved Reddit-wide search run daily as a third
source type (M3)" — the daily cadence, in the same class as KI-025, which widened
`tests/gates/test_superseded_claims.py` to scan `src/` and `deploy/`; the gate misses it
because the retired-claims table lists `every 2 days`, `06:30, 12:30` and `INTERVALS_PER_DAY`
but no phrase matching this one. (b) `src/insightminer/db/schema.py:926`,
`src/insightminer/db/schema.sql:55` and `db/migrations/versions/0001_initial.py:1256`:
`backups.kind` is documented as "daily, weekly, pre-migrate, manual or export", the vocabulary
D-31 retired (the retired-claims row is `7 daily`, which does not match). `schema.sql` is the
data dictionary the plan points readers at (`docs/PLAN.md:146`), so this one is read by humans.
*Fix:* add a `run daily` (or `search run daily`) row and a `daily, weekly` row to the retired
claims table in `docs/decisions/DECISIONS.md`, then correct the two docstrings; the column
comment change moves `schema.sql` and so needs the schema-snapshot path.

**9. MEDIUM — The schedule's own README states a validation duration that contradicts D-30 and
the arithmetic.**
`deploy/launchd/README.md:18`: "the seven-digest reading week finishes in about seven weeks",
against `docs/decisions/DECISIONS.md:218` — the cadence "finishes the seven-digest validation
in under a month" — and against seven runs at two a week, which is about three and a half
weeks. This file is a declared mirror of the plan (`docs/PLAN.md` front matter) and the home of
fact F-01, so it is not a stray note. Version one carried the same error in its intent block
(v1:5); version two dropped the sentence without sweeping the mirror that repeats it.
*Fix:* correct the sentence in `deploy/launchd/README.md` § cadence to the figure D-30 states.

**10. MEDIUM — The third clause of the one question is answered by a different mechanism than
the section that claims to answer it, and nothing before M3/M5 answers it at all.**
`docs/PLAN.md:13` states the question as "what are people struggling with, how many distinct
people, and **for how long**". `docs/PLAN.md:52` answers: "**'For how long' comes from
revisiting.** Posts are re-fetched on the ladder … so comment counts reflect a thread's
maturity, and every fetch stores a numeric-only snapshot … the raw material for velocity at M3
and trend charts at M5." A thread's maturity is how long one post kept receiving replies, not
how long a problem has persisted in the community; the capability that answers the latter is
deferred to M3 and M5 by that same sentence. Nothing in `core/digest.py` carries a duration
signal (the closest is `RisingPhrasesSection`, which is a growth signal against a four-week
baseline), and the M1d acceptance — seven digests read against Reddit — cannot test it.
Cheap options exist inside M1d (per-theme first-seen and weeks-active from `post_themes.tagged_at`
and `created_utc`). *Fix:* in `docs/PLAN.md` § From data to insight, either add the duration
signal to the digest's M1d definition of done or say in the intent block that the third clause
arrives with the analysis layer.

**11. MEDIUM — The stated cost of a second workspace omits the shared-source case, which is
where "one budget pool" meets the run loop.**
`docs/PLAN.md:200` prices a second workspace as "a workspace-add command, a run loop over
enabled workspaces with the budget split and reported per workspace, and the two-workspace
tests". The schema makes a subreddit monitored by two workspaces two rows
(`uq_subreddits_workspace_name_lower`, `schema.sql:18`), and `docs/TEST_STRATEGY.md` WS-03
already assumes that case ("A and B both monitor r/premiere"), so a naive loop sweeps the same
listing twice and doubles its API cost and its writes. *Fix:* add source de-duplication across
workspaces to the cost list in `docs/PLAN.md` § Workspaces → "What is built and what is not".

**12. MEDIUM — Per-source staleness is counted in runs, so the cadence change quadrupled its
wall-clock latency silently.**
`core/digest.py:66` `STALE_AFTER_RUNS = 2`, rendered as "not fetched for at least 2 runs"
(`digest.py:663`). `docs/PLAN.md:194` and `:400` describe it as "within the last two runs".
Under a daily cadence a quietly failing source was named in the digest after about two days;
at two runs a week it takes up to seven, longer than the `doctor` staleness alarm of five days
that is meant to be the coarser check. The wording moved from "intervals" to "runs" in the
rewrite without anyone deriving the new number. *Fix:* state the wall-clock consequence beside
the rule in `docs/PLAN.md` § Silent-failure controls, or express the threshold in days.

**13. LOW — `core/digest.py` quotes a plan sentence that the rewrite changed.**
`core/digest.py:63–66` quotes "PLAN.md, Resilience: 'the freshness invariants say so in the
digest when a source has not been fetched for two intervals'"; `docs/PLAN.md:194` now says "two
runs". *Fix:* update the quotation in the `STALE_AFTER_RUNS` comment.

**14. LOW — The cadence's load-bearing empirical premise has no source and no verification
point.** `docs/PLAN.md:181`: "At the twice-weekly cadence the busiest target produces tens of
posts a day, so the cap stays comfortable (D-30)"; `deploy/launchd/README.md:14`: "the target
subreddits produce far fewer than 1,000 posts between runs". No credentialed run has happened
(tranche B is unstarted), so neither figure has been measured, and the project's own practice
requires a spot-check before a count is written into a document. *Fix:* mark it an assumption
in `docs/PLAN.md` § Collector algorithm step 1 with the probe day or first backfill as its
verification point.

**15. LOW — Identity coverage is stated in the present tense one sentence before it is marked
as arriving at M1d.** `docs/PLAN.md:46`: "every ranked list prints the identity coverage of the
ranked set and annotates rows from incomplete trees … The digest models gain explicit
identity-coverage and tree-completeness fields … at M1d." The model has neither field today.
The qualifier rescues it, but the paragraph reads as built. *Fix:* put the milestone marker on
the first clause in `docs/PLAN.md` § From data to insight.

**16. LOW — D-32 is a rule with no enforcer and no row in the enforcement inventory.**
The working agreement's rules table carries no use-of-output row, so D-32 is neither
mechanically enforced nor counted in `.ratchets/review_only_rules.txt`. Nothing here can be
mechanized cheaply (it is a statement of purpose), but the project's own standard is that such
a rule is *labelled* review-only. *Fix:* add a review-only row for it to `CLAUDE.md` § Rules
and what enforces them, or record in `docs/decisions/DECISIONS.md` that it is deliberately out
of the table.

**17. LOW — `post_sources` has no index for the lookups the workspace paths need.**
`schema.sql` gives `post_sources` a unique constraint on `(post_pk, source_type, source_pk)`,
whose leading column is the post; "which posts does this source reach", the query behind
workspace delete (PLAN.md:204) and per-workspace feeds, has no index. The declared-index list
at `docs/PLAN.md:146` does not mention `post_sources` either. *Fix:* note the index in
`docs/PLAN.md` § Data model with the curation migration at M2, where the query first runs.

## What I could not check

- Every empirical premise about Reddit: no credentials exist, `adapters/reddit_praw.py` is
  unwritten, and the probe day has not happened, so posts per day, requests per post, `info()`
  omission behaviour and the real shape of a capped listing are all assumptions. Findings 1, 2
  and 14 rest on the project's own numbers, not on measurements.
- The M1c reconcile-age invariant and the retention pruning are unbuilt, so I judged them from
  the plan and the configuration rather than from behaviour.
- I ran only `tests/deploy/test_schedule_contract.py`, not `make check`, so I make no claim
  about the gate as a whole.
- The raw findings file from the 2026-09-15 refute pass lives outside the repository; I read
  only its committed record, so I cannot tell whether any finding here was raised there and
  consciously declined.
- Whether the ladder, the per-run budget and the per-source staleness threshold *should* change
  under the new cadence is a judgement for Wes; I establish only that they were named or
  implied as consequences and then left unexamined.

## Verdict

| Change | Verdict |
|---|---|
| 1. Twice-weekly cadence (D-30) and its re-derivations | **did not hold** — four thresholds unexamined, no revisit trigger |
| 2. All use personal (D-32) | held with gaps — two open-question lists unswept |
| 3. Premiere first, workspaces the option | held with gaps — schema is consistent; shared-source cost and the backup caveat unnamed |
| 4. High-volume levers deferred | **held** — triggers named and observable; keyed only to a second workspace |
| 5. "From data to insight" | held with gaps — matches the code; the third clause answers a different question |
| 6. Built/planned marks | **held** — ten built and five planned marks sampled, all true |
| 7. Backup retention (D-31) | held with gaps — decision sound, interim control absent |
| 8. Intent reframed around one question | held with gaps — clause three unserved and untested |

**Overall confidence: high** on the seventeen findings themselves — each is a file:line
contradiction, an arithmetic check against the shipped configuration, or a code reading, and
every one can be re-checked in minutes. **Medium** on the weighting: whether the ladder and the
per-run budget actually need to move is Wes's call, and three of the four unexamined thresholds
are latent because the code they govern is unbuilt. The rewrite itself remains a clear
improvement; what it did not do is finish the sweep that the cadence decision started, which is
the same failure mode the 2026-09-15 pass recorded as its lesson.
