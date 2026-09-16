# Review-round outputs in version two, part 2 (2026-09-16)

## Claim under test

Every finding the nine records of this seat accepted, every ruling they produced, and every item
they queued is still stated by plan version two, the decisions log, the known-issues register, or
the guards ledger, in a form a builder starting tranche B and M1b would read; nothing version two
says contradicts an unrevoked ruling; the version-two review's own restorations are present in
version two; and the queue those rounds produced (the between-run controls, the migration-checklist
tests, the storage canary matrix, the rev-2 UI items, the methodology items, the second external
round) is intact with its milestone.

**Verdict in one line: the claim holds for the fix-and-defect half and fails for the
queue-and-practice half.** Details in § Verdict.

## Method

1. Each of the nine records was read whole (the three long 2026-09-13 assessments through their
   decision-bearing sections: harness assessment §§ 4–7 and § 9, questions-answered § 4 and § 5,
   documentation-practices § 4 and § 6). Accepted findings, rulings and queued items were listed
   with what each required and, where one was named, its milestone.
2. For each item I looked for where it is stated **now** — `docs/PLAN.md`, `docs/decisions/DECISIONS.md`,
   `docs/runbook/KNOWN_ISSUES.md`, `docs/runbook/GUARDS.md`, `docs/recent/STATUS.md`,
   `docs/TEST_STRATEGY.md`, `docs/runbook/RUNBOOK.md`, `docs/learnings/LEARNINGS_TRANSFER.md`,
   `docs/reference/earlier-project/EARLIER_PROJECT_REFERENCE.md`, `docs/INSIGHTMINER_HARNESS.md`,
   and the review templates — and marked it **carried**, **not found**, or **contradicted**.
3. Claims about the tree were checked against the tree, not against a document: the invariant
   severities in `src/insightminer/services/invariants.py`, the planted-violation gate in
   `tests/gates/test_invariants_planted.py`, the packet bundle list in `tools/review_packet.py`,
   the scanned roots of `tests/gates/test_superseded_claims.py` and
   `tests/gates/test_routing_rows_resolve.py`, the register-id uniqueness check in
   `tests/gates/test_known_issues_cite_collected_tests.py`, and `.ratchets/review_only_rules.txt`.
4. For the plan-version-two record specifically, every item it says was *restored* to version two
   was located in `docs/PLAN.md` by quote before it was marked carried.
5. Nothing in the repository was edited. Version one
   (`…/scratchpad/review-2026-09-16/PLAN_v1.md`) was read only to test whether a missing item had
   ever had a home.

## Items

### 1. `2026-09-13-harness-assessment.md` — §§ 4–7 keep / simplify / trigger calls

| Item | What it required | Where stated now | Status |
|---|---|---|---|
| § 4.1–4.6 guard design rules and the four-question admission test | the rules in the plan, the ledger header | `docs/PLAN.md` § Robustness → "Guard design rules" (ten rows); `GUARDS.md` header ("Adding a guard needs a birth incident, a positive control, a row here, and a check whether an existing guard can be widened"); `DECISIONS.md` D-22 | carried |
| § 4.7 zero grandfathering, each suppression with a status and a review date | ratchet at the measured baseline; a status/`review_by` per suppression | ratchets carried (`GUARDS.md` G10, plan § Gates "Zero-suppression baseline"); the status/date half deferred to the quarterly review (`DECISIONS.md` 2026-09-15 "Suppression review dates"; plan § Workflows, "Guard review … suppression review dates") | carried |
| § 4.8–4.11 exception policy, secret scan, write guard in the chokepoint, hermetic tests | lint codes, gitleaks, G19/G31, fail-never-skip | plan § Silent-failure controls; `GUARDS.md` G01, G29, G19, G31, G06, G08/G09 | carried |
| § 4.12–4.14 cross-stage layer early; one blocking gate with a distinct exit code; a population canary per derived field | a workflow test layer, exit codes, population floors | plan § Testing ("Workflow" row), § Budget reality (exit codes), § Silent-failure controls (population floors) | carried |
| § 4.17–4.20 derive state; number homes; propagate to every mirror; doc-vs-contract cross-check | mechanical checks, not conventions | `GUARDS.md` G45, G34, G55, G33; `CLAUDE.md` § Practices "Every mirror in the same change", "Number homes" | carried |
| § 4.24–4.25 swept-and-clean; auto-memory plus an add/update-only snapshot | a written home; a snapshot with a completeness assertion | `KNOWN_ISSUES.md` § Swept (nine rows); `GUARDS.md` G47 | carried |
| § 4.26 budget a re-point pass into any move; know what is path-keyed | a rule, and knowing what breaks on a move | the memory home is recorded (`STATUS.md` § Do not undo; G47); no re-point procedure for a repo or data-directory move anywhere | not found (F11) |
| § 4.33 `caffeinate`, a patient retry ladder, per-item idempotent resume | all three on the collector | plan § Deployment path (`caffeinate -i`), § Resilience to outages (ladder, queue-based resume) | carried |
| § 4.34 a watchdog alerts, never silently restarts | a rule before M1d | plan § Alerts ("notifications are best-effort", the pill is canonical); no auto-heal exists | carried (implicitly) |
| § 5 simplify list (per-module prose, semantic search, the fleet apparatus, the two tenant lints) | skip, with the measured reason kept | `EARLIER_PROJECT_REFERENCE.md` § 6.2, one row each with its measurement; `docs/INSIGHTMINER_HARNESS.md` § 7 | carried |
| § 7 day-zero gap 1: the memory snapshot | build it | `tools/memory_snapshot.py`, G47 | carried |
| § 7 day-zero gap 2: record what memory is keyed to | a recorded answer plus the re-point budget | first half carried; second half — see § 4.26 above | partly not found (F11) |
| § 7 day-zero gap 4: `[DERIVE-LIVE]` for any count in prose | a convention plus a gate with the first generated block | ruled as D4 and built in substance: the harness page's block is rendered and gated (G54); the status page may restate no count (G45) | carried |
| § 7 day-zero gap 5: a three-to-five line "irreversible few" block | at the top of `CLAUDE.md` | `CLAUDE.md` § "The irreversible few", four rules each naming its enforcer | carried |
| § 7 day-zero gap 7: a path-resolution check inside `make check` (every path a hook, a `make` target or a ratchet names resolves) | a handful of lines in `make check` | G44 covers the three routing tables, the rule files and the memory snapshot only (`tests/gates/test_routing_rows_resolve.py` docstring); nothing reads hook scripts, the `Makefile` or `.ratchets/` for paths | not found (F11) |
| § 7 day-zero gap 8: a PreToolUse block on backgrounding a long collector run, and the matching irreversible-few rule | a hook plus a rule | neither: `CLAUDE.md`'s irreversible four do not include it, and no hook exists; no entry declines it | not found (F11) |
| § 7 day-zero gap 9: the uniform-staleness absolute anchor | one live "newest on the server vs newest in the store" check | declined with a reason: `DECISIONS.md` N-08; the residual risk is prediction P5 in `LEARNINGS_TRANSFER.md` § 5 | carried (declined with a home) |
| § 7 trigger catalogue (results ledger, confidence register, do-not-quote lint, parity/AST lock, delivery-surface guard, alert-path canary plus a genuine-vs-routine ledger, interleaved-write probe, architecture guide, data-traps page, characterisation pins, shim guard) | kept with birth incident and trigger | `EARLIER_PROJECT_REFERENCE.md` § 6.3, one row each with trigger and first step; routed from `CLAUDE.md` § Routing ("Decide whether to adopt a practice from the earlier project") | carried |
| § 9 the 26 questions | answered | `2026-09-13-harness-questions-answered.md`; `LEARNINGS_TRANSFER.md` § 7 (2026-09-13 night) | carried |

### 2. `2026-09-13-harness-questions-answered.md` — § 4, the sixteen catalogue moves

| Item | What it required | Where stated now | Status |
|---|---|---|---|
| Session-start carry-forward → keep only the state write; PreCompact subset → skip | skip the prescriptive halves | `EARLIER_PROJECT_REFERENCE.md` § 6.1 closing paragraph (both named as corrections to the first transfer) | carried |
| The ID allocator → "adopt the date-stamped id as the DEFAULT; rule out max+1-from-the-file" | register ids must not be max+1 | `LEARNINGS_TRANSFER.md` § 7 states it as adopted ("any register id here is date-stamped"); `EARLIER_PROJECT_REFERENCE.md` § 6.1 repeats it. The registers use sequential ids (KI-001…KI-026, G01…G55, D-01…D-32) and produced the 2026-09-14 duplicate incident; the fix was a uniqueness gate, not the allocator | **contradicted** (F5) |
| `last-verified` → the writer's half only, no reader-side alert | a stamp, no alerting | front matter `verified-at` on every living document; G55 checks it; no alert | carried |
| Register set → two (here three) with a routing rule above them | a routing rule | `docs/INDEX.md` router (G33) and `CLAUDE.md` § Routing; `EARLIER_PROJECT_REFERENCE.md` § 6.1 "Three registers with a sharp bar, not seven" | carried |
| Command surface → single digits; an uninvoked command is a document | hold the count | `INSIGHTMINER_HARNESS.md` § 7 ("No slash-command surface beyond two skills"); sixteen `make` targets in the generated inventory | carried |
| Path-keyed harness → adopt the rail | the path-resolution check | see § 7 day-zero gap 7 above | not found (F11) |
| Memory snapshot → completeness assertion plus a positive control | both | G47 with `test_restore_is_red_when_a_destination_byte_differs` and `test_a_deletion_in_live_memory_never_deletes_from_the_snapshot` | carried |
| "Which checks ever went red" → close, with the correction that a guard's clean record is not evidence | the verdict vocabulary and an honest default | `GUARDS.md` header ("Every row is born clean … and therefore UNPROVEN; a guard never seen failing is a hypothesis") | carried |
| THE SECOND RULE → positive controls **extended to the guard's own scope fence** | a control planted inside the scope the gate scans | asserted as adopted in `LEARNINGS_TRANSFER.md` § 7; the plan's guard rules say only "construct the bad state"; the ceiling counts rows, not scopes, and `GUARDS.md` G05 has no control for two of its halves while reading as controlled | **contradicted** (F6) |
| THE THIRD RULE → plus "assert what the code must do, never how it is written" and "never pin a binding test to a live defect" | two added rules | the first is present in substance (plan § Guard design rules, "Key on the invariant, not a proxy"); the second appears nowhere | partly not found (minor; folded into F11) |
| Use-triggered maintenance → plus a genuine-vs-routine ledger for every alerting path from day one | a ledger with the first real alert | `EARLIER_PROJECT_REFERENCE.md` § 6.3 (alert-path canary row, trigger: the first notification Wes relies on) | carried |
| The fetch stop rule → plus "the run's log must answer did this source stop and why" and "a stop rule must not fire below the non-stopping path's yield" | both | the first carried (`run_subreddits.stop_reason` in the plan's data model and § Collector algorithm step 1; KI-018 hardened it); the second appears nowhere | partly not found (minor) |
| One-committer invariant → adopt | a practice, then a guard | `STATUS.md` § Do not undo ("A second live session in this checkout works in a git worktree until the one-session guard lands"); the guard is on the waiting list | carried |
| `⛔ DO NOT REDISCOVER` → adopt explicitly as marker plus canonical home | a docstring marker convention | nowhere in the tree (one incidental use of the word in `EARLIER_PROJECT_REFERENCE.md` § 3.1) | not found (minor) |
| Agent-report exhaust → adopt the separation | transcripts and raw findings never committed | plan § Reference corpus ("Agent transcripts and raw findings are never committed"); `DECISIONS.md` 2026-09-14 | carried |
| Auto-memory → the index line is the only always-loaded surface; no second tier | one home, capped | G47 (one memory home, byte cap per topic file, a project memory naming a real repository path) | carried |

### 3. `2026-09-13-documentation-practices-assessment.md` — the eight decisions and the day-one set

| Item | What it required | Where stated now | Status |
|---|---|---|---|
| D1 one memory home | keep the repo-keyed directory | `DECISIONS.md` 2026-09-13 night; G47; `STATUS.md` § Do not undo | carried |
| D2 memory snapshot and integrity check now | build both, restore asserts completeness | G47, `tools/memory_snapshot.py` in `make check` | carried |
| D3 the architecture guide at M2, generated where it can be | written at M2, not before | `EARLIER_PROJECT_REFERENCE.md` § 6.3 ("A written architecture guide | M2, when the module set has stopped moving"); **not** in the plan's M2 definition of done | carried (weakly — F10) |
| D4 the derive-live gate with the first generated block | build it when a generated block exists | G54 (the harness inventory, rendered and diffed); plan § Robustness names it | carried |
| D5 cap and de-scope `STATUS.md` | ~50 lines, decision lists moved to the log | G45 (`tests/gates/test_status_page.py`); `DECISIONS.md` § "Moved from STATUS.md" | carried |
| D6 a status and review date on the 24 suppressions | with the `hard_after=` change | `hard_after=` built (G10/G51 note in `GUARDS.md`); the per-suppression date deferred to the quarterly review with a recommendation (`DECISIONS.md` 2026-09-15) | carried |
| D7 the approach as a `CLAUDE.md` section, not a file | no `METHOD.md`; the mechanize-don't-restate content moves into `CLAUDE.md` | the container decision holds and is re-affirmed (`DECISIONS.md` 2026-09-15, harness-page entry); the named section and its failure-class→mechanism table were never written | partly not found (F10) |
| D8 the sub-agent brief template | `docs/reference/AGENT_BRIEF.md` | exists; `CLAUDE.md` § Agent model tiers and § Routing both require it | carried |
| Day-one set 1–10 (always-loaded floor, number homes with a check, document classes with policies, one register with five properties, mechanise rather than restate, memory index plus integrity check, add/update-only snapshot, propagate-to-mirrors with a check, a trust header, the guard admission test) | installed at day zero | all ten appear in `CLAUDE.md`, the plan § Reference corpus, `GUARDS.md`, G45/G47/G55 and `EARLIER_PROJECT_REFERENCE.md` § 6.1 | carried |
| "Deliberately left for a named trigger" (eight rows) | kept with their triggers | `EARLIER_PROJECT_REFERENCE.md` § 6.3; the never-practised three-line measured-result note is explicitly retired with a home in the plan's version history | carried |

### 4. `2026-09-14-packet-brief-panel.md`

| Item | What it required | Where stated now | Status |
|---|---|---|---|
| Findings 1–17 on the packet and the brief (line numbers and citation form, the part index, "earlier reviews are recorded not withheld", a cost×confidence scale, the worked example, `STATUS.md` and `config/` included, the tranche-B caveat, the split Reddit question, an output budget, five added questions, the claims-list header, size-capped parts, the identifier test withheld, the honest README, the design inputs included, a built-versus-planned map with start-here lists) | applied to the builder, the README and the brief | `docs/reference/reviews/templates/external-deep-research.md` lines 66–67 (part, path, line, verbatim quote), 97 and 234–235 (cost×confidence, at most fifteen findings under 150 words each), 149–216 (start-here lists per question); `tools/review_packet.py` BUNDLES (`docs/recent/STATUS.md`, `config`, the research report and the collector design review) and EXCLUDED_PREFIXES (`tests/gates/test_no_imported_identifiers.py`) | carried |
| Not applied, held for Wes: owner-identity redaction; abstracting the earlier project's document names and archive paths | a ruling | ruled 2026-09-14 (`DECISIONS.md`): the identity redactions go in and are counted in the manifest; the document-name abstraction stays as recommended | carried |
| S1 index keeps scrubbed text until `optimize` | a failing test, then a fix | KI-009 fixed; strengthened by revision 0004 | carried |
| S2 bound parameters in error columns | `hide_parameters=True` plus a planted test | KI-010 fixed | carried |
| S3 `info()` omits a whole private subreddit; two reconciles would scrub it | a rule for M1c: a miss must not count while the source status is not `ok` | plan § Milestones M1c ("the private-subreddit rule for reconcile") | carried |
| S4 nothing stops a red tree reaching `main` | the merge hook keyed on the check summary | built: `tools/check_stamp.py` + G23; `STATUS.md` § Do not undo | carried |
| S5 hook bypasses | each becomes a red row first | KI-020 fixed with a row per shape | carried |
| S6 C-06 overclaims (repository root only) | narrow the claim; widen the test later | claim narrowed (`templates/claims.md` C-06); the widening is on `STATUS.md` ("the wider data-directory write test") | carried |
| S7 sequencing: one credentialed probe day before M1b | a ruling | ruled 2026-09-14; plan § Milestones M1a tranche B; `STATUS.md` § Next 1 | carried |
| S8 `sqlite_sequence` recycling after a batch migration | a test and a fix | KI-014 open; the migration checklist is queued (plan § Testing "Migrations" row, § Milestones M1c) | carried |

### 5. `2026-09-14-testing-and-workflow-panel.md`

| Item | What it required | Where stated now | Status |
|---|---|---|---|
| 1 duplicate register ids | a gate refusing a reused id in all three registers | `tests/gates/test_known_issues_cite_collected_tests.py::duplicate_ids` with its positive control | carried |
| 2 merge hook judged the starting branch; 3 the stamp survived a red check | both fixed with controls | G23 row; `DECISIONS.md` 2026-09-14 (later) | carried |
| 4–8 KI-011, KI-012, KI-013, KI-014, and the KI-009/KI-010 confirmations | fixes on one branch | KI-011/012/013 fixed, KI-014 open, KI-009/KI-010 fixed | carried |
| Methodology: byte-level assertions, one parametrized "canary absent from every byte-producing artifact" test | the canary covers the class of surfaces | plan § Testing names DB, index bytes and a fresh export (§ Workflows adds backups); error columns, the write-ahead log, `raw_rejects` and `raw_json` are absent from the canary spec; `STATUS.md` carries "the storage-level canary matrix at M1c" | partly not found (F4) |
| Methodology: three declared-but-unused test tools; a `make mutate` target; a reading-week record with a `doctor` age check | queued | `STATUS.md` § In flight, methodology items | carried |
| Failure modes: the five between-run controls | M1d blockers | plan § Milestones M1d (verbatim, "blockers, not features"); `STATUS.md` queue | carried |
| Failure modes: the search-index invariant at warning severity | raise it or record why not | nowhere; and the plan, the harness page and `GUARDS.md` state the opposite of the code | **contradicted** (F1) |
| Failure modes: the settings fingerprint stamped and never compared; the repository move unnoticed by `doctor`; an unrotated launchd log; a dependency upgrade unchecked against the lock | queued | only the last is partly covered (plan § Workflows "Dependency bump"; G53 for `praw`); the other three appear nowhere | not found (F11) |
| Operator workflows: ten rev-2 gaps for M2 | carried into the M2 design | seven of ten plus the round-one ranking item are enumerated on `STATUS.md`; the lock-contended theme save and double submit, paused-vs-stopped as one state, the sixty-day amber with no explanatory copy, and the M4 coworker's terminal-bound actions are only in the record | partly not found (F8) |
| Principal engineer: the post-migration index check is a proxy; fixtures hold only live rows; two pinning systems reconcile nowhere; the register surface includes the ratchet files; the memory audit in `make check` | fixes or rulings | the first is inside the migration checklist (plan § Testing, "triggers present, FTS integrity"); the register surface was narrowed by ruling; the memory audit was ruled kept; the fixture and pinning items appear nowhere | partly carried |
| SQLite: the four small fixes, then the migration-checklist tests | one branch, then the checklist | all four landed (`DECISIONS.md` 2026-09-14, the SQLite branch); the checklist is queued at M1c | carried |
| Five rulings requested | Wes rules | all five ruled 2026-09-14 and recorded with their consequences | carried |

### 6. `2026-09-14-external-round-1.md`

| Item | What it required | Where stated now | Status |
|---|---|---|---|
| KI-015 … KI-020 (restore ordering, crosspost parent text, no-enabled-source, capped listing, non-fast-forward merge, shell indirection) | reproduce, fix, register | all six `fixed` in `KNOWN_ISSUES.md` with node ids that resolve (G40); the plan states each consequence (§ Release KI-015, § From data to insight / data model KI-016, § Collector algorithm step 0 KI-017 and step 1 KI-018, § Gates KI-019/KI-020 through G23) | carried |
| KI-021 … KI-023 and the C-05 overstatement (fourth seat) | same | all three `fixed`; C-05 narrowed in `templates/claims.md` | carried |
| Finding 9: identity coverage and tree completeness beside the ranked count, with a golden | queued for M1d | plan § From data to insight ("The digest models gain explicit identity-coverage and tree-completeness fields beside the count at M1d") and § Milestones M1d; `STATUS.md` rev-2 list | carried |
| Finding 11: the access-approval step | into the setup checklist | `RUNBOOK.md` § 1; plan § Context and § Things only Wes can do 1 | carried |
| Revision 0004, FTS5 persistent secure-delete, with the `doctor` version check | build it | built 2026-09-15; plan § Schema revisions and § SQLite facts; `doctor` check in the plan's CLI table | carried |
| Ruling 1 backups and deletions (four options) | Wes chooses | D-31 (`DECISIONS.md` 2026-09-15); plan § Release; `RUNBOOK.md` § 5; live fact F-05 | carried |
| Ruling 2 login session | no daemon; the ping is the detector; the install note | plan § Deployment path ("Scheduled jobs run only inside a logged-in session … ruling 2026-09-14") | carried |
| Ruling 3 hook-boundary wording | into the ledger | `GUARDS.md` G23 ("**What these hooks are:** mistake prevention for the agent … not a security boundary"); plan § Gates | carried |
| Ruling 4 declining the demotion of the drift gates | recorded | `DECISIONS.md` 2026-09-14 (d) | carried |
| Reviewer A-3 ruling: `raw_rejects` holds raw text with no id to reconcile | add the surface to the deletion-boundary list in the canary spec | not in the plan's canary spec; the retention bound is stated (`raw_rejects` row, `config/settings.yaml`) but the surface is not a canary target | not found (F4) |
| C-14 + A-7: the three live probes and the 100-child chunking | "adopted into the probe-day checklist (`docs/PLAN.md` § M1 probe)" | no such section in version two **or** version one; the probe plan is P-01…P-17 in the 2026-09-13 ingest panel (a frozen record) routed from `docs/TEST_STRATEGY.md`; the chunking probe survives as FK-01's note and KI-023 | **not found** (F3) |
| Round two, aim 1: the fixes and revision 0004, one new claim per fix in `templates/claims.md` | claims added before the round | `templates/claims.md` has sixteen built claims and four planned; no claim names KI-015…KI-020 | not found (F9) |
| Round two, aims 2–5: the M1b/M1c designs; the adapter contract against captured fixtures; operator workflows and the UI plan (the thinnest coverage); the analytic layer's validation design | carried to the round | `STATUS.md` § Next 4 names the fixes and the M1b/M1c designs with a code-executing seat; aims 3, 4 and 5 appear nowhere else | partly not found (F9) |
| Round two, packet changes: carry the policy facts file and the SQLite facts; every location must be a packet part and line; discard a finding whose quote is not in the packet; ask for a code-executing seat | in the builder, the brief and the runbook | the discard rule is in `RUNBOOK.md` § 7 step 3 and the brief; the code-executing seat is on `STATUS.md`; `docs/reference/reddit-policy-facts-2026-09-14.md` is **not** in `tools/review_packet.py` BUNDLES, although `DECISIONS.md` 2026-09-14 rules "The next packet carries the facts file" | **contradicted** (F2) |
| Seven refuted claims | recorded so nobody re-investigates | `KNOWN_ISSUES.md` § Swept, seven rows with how each was checked | carried |

### 7. `2026-09-15-round-one-fix-panel.md`

| Item | What it required | Where stated now | Status |
|---|---|---|---|
| The four hook holes (line continuation, separated `--config-env`, doubled slash, case variants) | fixed with controls | `GUARDS.md` G23 names all four and the tokenizer changes; `tests/gates/test_hooks.py` controls resolve | carried |
| KI-016 non-mapping crosspost entry; KI-017 collectable sources; KI-021 non-consecutive omissions; KI-023 single large subtree; the KI-015 docstring | corrected | each register row carries the follow-up wording; the plan states the non-consecutive rule (§ Content-state machine, "which need not be consecutive (KI-021)") and the fake's fidelity limit (§ Testing strategy) | carried |
| Enforcement-reach gaps: a schedule contract without macOS tooling; a control for the `praw` pin; test-strategy citations gated | three closures | `tests/deploy/test_schedule_contract.py` (KI-024, KI-026 cite it), G53, `test_every_test_strategy_citation_exists` | carried |
| Held as out of scope: the deliberate-bypass shapes | stated as the documented limit | `GUARDS.md` G23; `LEARNINGS_TRANSFER.md` § 7 (2026-09-15) | carried |

### 8. `2026-09-15-plan-v2-review.md` — the restorations, checked by quote

| Item | Where in `docs/PLAN.md` now | Status |
|---|---|---|
| The eight declared indexes | § Data model: `posts(next_check_at)`, `posts(subreddit_pk, created_utc)`, `posts(author_fullname)`, `posts(content_state)`, `comments(post_pk, parent_comment_pk)`, `comments(author_fullname)`, `post_themes(theme_pk)`, `item_snapshots(item_pk, fetched_at)` — eight | carried |
| Content-state and author-state values, including terminal `gone` | § Data model `posts` row ("`live/deleted_by_author/removed_by_moderator/removed_by_reddit/gone_unconfirmed/gone`", "`known/account_deleted`") and § Content-state machine | carried |
| The reconcile cost estimate | § Collector algorithm 4 ("roughly eight hundred requests at the four-month mark and about two and a half thousand at one year") | carried |
| The coverage counters on the run row | § Silent-failure controls, "Coverage counters" bullet with all six | carried |
| The comment-tree wire facts | § Collector algorithm 2 ("PRAW objects are serialized with `vars()` minus private keys … a `count == 0` node is a continue-this-thread link") | carried |
| The comment deep-link form | § Web UI ("comments use `/_/{comment_id}/?context=3`") | carried |
| The Run-now options and the polling route | § Routes `/runs` ("full run, fetch only, reconcile only, re-tag only, saved searches only … polls `/runs/current` every two seconds") | carried |
| The single-function scrub assertion | § Gates, connection chokepoint ("scrub is one function whose test asserts the row, the index, and `post_themes` changed in the same call (M1c)") | carried |
| Cassette hygiene | § Testing ("auth headers and tokens filtered") and § Gates ("a personal restricted test subreddit … so cassettes contain no third-party content") | carried |
| The expand-and-contract recipe | § Release ("add nullable → write both → backfill from `raw_json` → switch reads → drop later; never rename in place") | carried |
| The cloud-review trigger | § Review harness ("Large changes and milestone merges | Wes may trigger the built-in multi-agent cloud review") | carried |
| The concrete UI values (page size, token names, the search grammar, the theme editor, the gate-state detail, the fake's builder surface, the mutating-command list, the browser command) | § Web UI design rules and routes; § Testing (the fake's nine builder calls); § Collector algorithm 0 (the ten mutating commands); § Power view (`uvx datasette`) | carried |
| Corrections: `comments_captured`; `optimize` in revision 0004 and the scrub stage; no ntfy notifier; `rule_group`; the seven built invariants named and the rest by stage; the `backups` columns; two files added to the layout; "went in at M0" and "every section walked" softened | § Data model, § Schema revisions, § Module map, § Silent-failure controls, § Repository layout, § Robustness lead, § Milestones D0 — each present as described | carried |
| Mirrors swept (exit-code row, `caffeinate`, the test strategy, the router row, the runbook, KI-021, the Swept row, the CI row) | `DECISIONS.md` § 6 exit-code row annotated; the rest verified in place | carried |
| Retired with a home: the two UI wireframes; the three-line measured-result note | § Version history, version 2 row | carried |
| Held by design: three counts removed; the compliance bounds annotated not rewritten | the harness page's generated block holds the counts; `DECISIONS.md` § 2 carries dated annotations | carried |

### 9. `2026-09-15-doc-policy-review.md`

| Item | What it required | Where stated now | Status |
|---|---|---|---|
| The append-only baseline is the merge base with `main`; a policy change cannot exempt a document | a control on a real git tree | `GUARDS.md` G55 mechanism and the controls `test_positive_control_a_deleted_line_in_an_append_only_document_is_red_even_when_committed`, `…_a_policy_change_cannot_exempt_an_append_only_document` | carried |
| Records are checked (byte-identical; the register append-only; templates reviewed like code) | a check, not a sentence | G55; `RUNBOOK.md` § 8 ("`docs/reference/` … a record is added, never edited") | carried |
| The accretion count excludes table rows and is a pressure, not a proof | wording and the ratchet | `RUNBOOK.md` § 8; `.ratchets/docs.txt`; plan § Reference corpus | carried |
| Vacuous passes closed (the `generated` policy removed, an empty facts table is red, a future stamp is red, fences ignored, `--check` exits non-zero) | controls | G55's control list; `make doc-policy` in `make check` | carried |
| Mirrors declared from both sides and described honestly | declarations corrected; wording softened | front matter of `PLAN.md`, `DECISIONS.md`, `GUARDS.md`, `KNOWN_ISSUES.md`, `STATUS.md`, `TEST_STRATEGY.md`; `RUNBOOK.md` § 8 ("only the facts table is checked mechanically") | carried |
| Every control plants its bad state on a real git tree | eleven controls | listed in `GUARDS.md` G55 and resolved by G40 | carried |
| Held by design: a self-declared milestone clock; short literals are weak substrings; a bare file name is not judged | stated where they live | `RUNBOOK.md` § 8; `GUARDS.md` G55 ("What stays review") | carried |

**Counts.** 107 items extracted across the nine records (grouping a record's numbered list into one
row where the whole list shares one destination): **86 carried**, **17 not found or only partly
found**, **4 contradicted** (the invariant severity, the date-stamped ids, the scope-fence claim,
the packet's missing policy-facts file).

## Findings

### F1 — CRITICAL: the plan, the harness page and the guards ledger say an invariant violation fails the run; five of seven are warnings, and the panel finding that flagged it was never queued

`docs/PLAN.md` § Silent-failure controls: "**Post-run invariants** (violations flip the run to
`failed`; each is planted through `insightminer run --gateway fake` by its positive control, G30)".
§ Gates, "Post-run invariants … Fails how: run `failed`, notification". § Failure-mode matrix:
"Column silently all NULL | Population-floor invariant **fails the run** and names the column".
`docs/INSIGHTMINER_HARNESS.md` § Enforcement: "Post-run invariants at runtime flip a run to
`failed` rather than warn."

The tree says otherwise. In `src/insightminer/services/invariants.py` only
`counters_equal_table_deltas` and `no_other_running_rows` raise `Severity.FAILURE`;
`fts_membership_equals_live`, `rows_carry_current_normalizer_version`,
`unknown_enum_values_are_counted`, `population_floors_hold` and `per_source_freshness` all raise
`Severity.WARNING`, and the module's own docstring says "``WARNING`` makes the run ``partial``,
``FAILURE`` makes it ``failed``". The gate agrees with the code, not the plan:
`tests/gates/test_invariants_planted.py::test_planted_violation_flips_the_run` asserts
`result.exit_code in {1, 3}` and `row["status"] != "ok"`.

This is also a lost queued item. The testing-and-workflow panel listed "the search-index invariant
at warning severity" among the findings recorded for the queue; it is not on `STATUS.md`, not in
`DECISIONS.md`, and not declined anywhere.

Why it matters now: the same paragraph queues the *unbuilt* invariants for M1b and M1c, including
"the last complete reconcile is within the per-tier bound … so compliance cannot lapse quietly". A
builder reading version two alone will ship that one as FAILURE (contradicting the shipped
pattern) or, reading the code, as WARNING — in which case a lapsed compliance re-check closes the
run amber, which is the silent-failure class the invariant exists to prevent. Wes's own D-29
("nothing advisory in the gate") makes the choice a decision, not a detail.

**Fix:** in `docs/PLAN.md` § Silent-failure controls, replace the blanket clause with the severity
rule the code implements and mark each invariant `failure` or `warning` (including the M1b/M1c
ones), then sweep the mirrors — the plan's Gates table and failure matrix, `GUARDS.md` G30/GT-01's
"Fails how" cell, and `INSIGHTMINER_HARNESS.md` § Enforcement — and decide in `DECISIONS.md`
whether the index-membership and compliance invariants are FAILURE.

### F2 — HIGH: the next external packet will not carry the Reddit policy facts, the harness page or the overview, against an explicit ruling

`DECISIONS.md` 2026-09-14 (Reddit policy pages): "The next packet carries the facts file". The
round-one record's round-two instruction: "Change the packet: carry the policy facts file and the
SQLite facts so reviewers attack code against known facts instead of re-fetching them."

`tools/review_packet.py` BUNDLES["1-documents"] lists `CLAUDE.md`, `docs/PLAN.md`,
`docs/decisions/DECISIONS.md`, `docs/recent/STATUS.md`, `docs/TEST_STRATEGY.md`, `docs/INDEX.md`,
`docs/runbook/*`, `docs/reference/reviews/REGISTER.md`, `docs/reference/AGENT_BRIEF.md`,
`docs/learnings`, `docs/insights`, the research report, the collector design review, `config`, and
`src/insightminer/db/schema.sql`. It does **not** list
`docs/reference/reddit-policy-facts-2026-09-14.md`, `docs/INSIGHTMINER_HARNESS.md` or
`docs/OVERVIEW.md` — the last two written on 2026-09-15, after the builder. The router carries all
three (`docs/INDEX.md` lines 17, 63–64, 96), so the omission is the builder's alone, and G52's test
(`test_a_packet_holds_only_the_allowlist_from_head`) is one-directional: a new living document can
never fail it by being absent.

Round two is scheduled at tranche B's design freeze, and two of its five aims are the M1b/M1c
compliance designs — the ones the policy facts govern. The harness page is the document that
answers the brief's own question 7 about the enforcement harness.

**Fix:** add the three paths to `BUNDLES["1-documents"]` in `tools/review_packet.py` and add a
test in `tests/gates/test_review_packet.py` asserting every tracked file under `docs/` is either in
a bundle or in `EXCLUDED_PREFIXES`, so a new document cannot be silently omitted.

### F3 — HIGH: the probe-day checklist the round-one record adopted has no home in any document

External round one, reviewer C-14: "the three-probe list is adopted into the probe-day checklist
(`docs/PLAN.md` § M1 probe) on the fix branch, with one more from A-7: the 100-child chunking of a
large `more` node." There is no `§ M1 probe` in `docs/PLAN.md` version two, and `grep -i probe`
over `PLAN_v1.md` shows there was none in version one either — the record commits to a section that
never existed. The plan now carries a single clause ("one credentialed probe day capturing the
shapes the deletion predicates and the fake assume") and `STATUS.md` § Next 1 the same. The real
probe plan is P-01…P-17 inside `docs/reference/reviews/2026-09-13-panel-ingest.md` § C, a dated
record that G55 holds byte-identical, so the three round-one probes (paged `/new` with recorded
cursors; a controlled tree carrying a `more` node, a deletion and a continue-thread node; a batched
`info()` over live, deleted, removed, missing, account-deleted and inaccessible items) cannot be
added to it. `docs/TEST_STRATEGY.md` line 289 similarly parks P-18 (the deleted link post) as a gap
to write.

The probe day is the next thing that happens after credentials arrive and it is a one-shot,
credentialed session; a checklist assembled from memory will miss the items two review rounds paid
for.

**Fix:** add a "Probe day" subsection to `docs/PLAN.md` § Milestones (or a `§ 3.3 Probe plan`
table in `docs/TEST_STRATEGY.md`, which is prune-stale and already routes to P-01…P-17) listing
P-01…P-18 plus the three round-one probes and the 100-child chunking capture, and point
`STATUS.md` § Next 1 at it.

### F4 — MEDIUM: the compliance canary's surface list is narrower than the surfaces two rounds proved were leaking

`docs/PLAN.md` § Testing strategy: "the **compliance canary** (ingest a unique phrase, delete it in
the fake, reconcile, scan the DB, the index bytes, and a fresh export)"; § Workflows adds "backups
within retention". Four surfaces. The rounds established more: KI-010 put post text in
`run_subreddits.error` and `subreddits.last_error`; KI-013 left pre-scrub page images in the
write-ahead log; reviewer A-3's ruling added `raw_rejects` ("the surface is added to the
deletion-boundary list in the fix branch's canary spec"); and round two's aim 2 names the matrix in
full — "live rows, index, write-ahead log, raw JSON, rejects, error columns, exports, backups …
with an owner, a mechanism and a witness test per surface". The testing panel's own recommendation
was "one parametrized 'canary absent from every byte-producing artifact' test covers the class".
Today only `STATUS.md` ("the storage-level canary matrix at M1c") carries the idea, without the
list.

**Fix:** replace the canary parenthesis in `docs/PLAN.md` § Testing strategy (and the matching row
in § Workflows) with the eight-surface deletion-boundary matrix, one line per surface with its
mechanism, so the M1c builder inherits the list rather than the phrase.

### F5 — MEDIUM: "any register id here is date-stamped" is stated as adopted and contradicted by every register

`docs/learnings/LEARNINGS_TRANSFER.md` § 7 (2026-09-13 night), item 4: "`max+1`-from-the-file is
ruled out as an id allocator, so any register id here is date-stamped".
`docs/reference/earlier-project/EARLIER_PROJECT_REFERENCE.md` § 6.1 repeats it as one of four
corrections carried at day zero: "the date-stamped identifier as the default (a max-plus-one
allocator read from a file is the mechanism that produced the earlier project's duplicate
numbers…)". Every register in the tree uses max+1: KI-001…KI-026, G01…G55, D-01…D-32, N-01…N-21 —
and on 2026-09-14 exactly the predicted failure occurred
(`tests/gates/test_known_issues_cite_collected_tests.py`: "Birth incident 2026-09-14: two open rows
reused KI-005 and KI-006"), plus N-18 twice. The fix chosen was a uniqueness gate, which is a
reasonable answer, but nothing records that the allocator ruling was superseded, so two documents
assert a practice the tree refutes. G55 cannot see it: it is a behavioural claim with no identifier,
which the 2026-09-16 ruling explicitly leaves to review.

**Fix:** correct `EARLIER_PROJECT_REFERENCE.md` § 6.1 in place (it is prune-stale for judgements)
to say the allocator call was superseded by the register-id uniqueness gate on 2026-09-14, and add
a dated parenthetical to the `LEARNINGS_TRANSFER.md` § 7 line pointing at it.

### F6 — MEDIUM: "every gate ships a positive control inside the same scope fence" is asserted while the ceiling counts rows, not scopes

The questions-answered record moved THE SECOND RULE to "adopt, **extended to the guard's own scope
fence**", on the evidence that "the commonest self-defect was a dead scope path — a clean 138-site
baseline reported *while never opening 138 files*". `LEARNINGS_TRANSFER.md` § 7 states it as
adopted: "every gate here ships a positive control that sits inside the same scope fence."
`docs/PLAN.md` § Guard design rules states only the unextended rule ("construct the bad state and
assert the gate goes red"). The ledger shows the gap: `GUARDS.md` G05's control cell reads "no
planted control yet for the `praw`-only-in-adapter or `fcntl`-only-in-`services.lock` halves", yet
`.ratchets/review_only_rules.txt` holds `guards_without_control=2` (G01 and G16 only) — because the
ceiling counts *rows* with an empty cell, not *scopes* without a control. A guard half of whose
scope is unproven reads as controlled.

**Fix:** add the scope-fence clause to `docs/PLAN.md` § Robustness → "Guard design rules" ("a
positive control plants the bad state inside the scope the gate actually scans, and a partly
controlled guard counts as uncontrolled"), and count part-controlled rows in the
`guards_without_control` ceiling.

### F7 — MEDIUM: three items Wes approved on 2026-09-13 have a milestone but no home in a document a builder reads

- **The duties record.** `DECISIONS.md` 2026-09-13: "Duties record: approved, kept light (one
  table, ages on `/system`, one digest line) at M2", expanded in `LEARNINGS_TRANSFER.md` G4 as "a
  `duties` table (last completed, interval) written only by the completing action … schema revision
  2 at M2". The plan contradicts it by omission: § Schema revisions says "The next planned revision
  is the **curation migration** at M2: `workspaces.archived_at`, `post_themes.origin`,
  `posts.watch_until`, in one migration" — an exhaustive list — and neither § Routes `/system` nor
  § Milestones M2 mentions duties.
- **R4's second half.** "`threshold: provisional|calibrated` on `GUARDS.md` rows, checked during
  the M1d digest week", approved 2026-09-13. `GUARDS.md` has no such column and nothing names the
  M1d check.
- **The two ratios (R7 and G1).** `DECISIONS.md` 2026-09-13: "both ratios approved for the
  quarterly review"; `LEARNINGS_TRANSFER.md` G1: "printed at each quarterly review". `RUNBOOK.md`
  § 6 (steps 1–6) prints firings, verdicts and runtime cost, and never the apparatus-to-product
  ratios or R7's surface-versus-internals tally; the plan's § Workflows quarterly row lists only
  verdicts, firings, the read-before-touch ledger and suppression dates. Prediction P12 is the only
  survivor, and it is a scoring note, not a procedure.

**Fix:** add the duties table to `docs/PLAN.md` § Schema revisions (the curation migration) and
§ Routes `/system`; add the `threshold` column to `docs/runbook/GUARDS.md` with the M1d check named
in § Milestones M1d; add the two ratios and the R7 tally as steps in `docs/runbook/RUNBOOK.md` § 6.

### F8 — MEDIUM: the status page's rev-2 enumeration reads as the whole list and is missing four of the workflow seat's gaps

`STATUS.md` § In flight enumerates eight rev-2 items in a parenthesis that reads as complete. The
workflow seat ranked ten gaps plus the M4 coworker case. Absent from both the status page and the
plan: a theme save while the collector holds the lock has no defined outcome and a double submit
reaches a 500; paused and stopped-keep-data are one state; the sixty-day amber-by-design period has
no copy explaining it; and "the coworker at M4 cannot edit static settings, place an import archive,
or initialise an empty volume without a terminal" — which is an operator-complete gap against D-28.
They survive only in the record, which the bullet's lead does name.

**Fix:** in `docs/recent/STATUS.md` § In flight, replace the eight-item enumeration with "the ten
rev-2 design items in `docs/reference/reviews/2026-09-14-testing-and-workflow-panel.md` § Operator
workflows, plus the M4 terminal-free gaps", so a partial list cannot read as the whole one.

### F9 — MEDIUM: round two lost three of its five aims and its claims-list preparation

The round-one record's § "Round two: what to aim at, and when" lists five aims in order and says
"one new claim per fix in `templates/claims.md`, with the brief telling reviewers the previous
round's conclusions are the target". `STATUS.md` § Next 4 carries aims 1 and 2 ("the fixes and the
M1b/M1c designs … with a code-executing seat"). Aim 3 (the real adapter's contract against the
captured fixtures), aim 4 (operator workflows and the UI plan — "question 7 drew the thinnest
coverage in round one") and aim 5 (the analytic layer's validation design: distinct authors against
distinct people, and how the reading week is scored) appear in no living document.
`templates/claims.md` still holds sixteen built claims and four planned ones; none names KI-015 to
KI-020 or the ff-only merge rule, so the round that is supposed to target the previous round's
conclusions has nothing to falsify about them.

**Fix:** move the five aims and the packet changes into `docs/recent/STATUS.md` § Next 4 (or a
"Round two" block in `docs/runbook/RUNBOOK.md` § 7) and add one claim per round-one fix to
`docs/reference/reviews/templates/claims.md` before the tranche B freeze.

### F10 — LOW: two documentation-practice rulings survive as a container decision without their content

D3 placed the architecture guide at M2; its only home is
`EARLIER_PROJECT_REFERENCE.md` § 6.3, and the plan's § Milestones M2 definition of done does not
name it, so an M2 builder reading version two alone will not write it. D7's ruling ("the approach
lives as a section of `CLAUDE.md`, not a file") holds as a container decision and was re-affirmed
on 2026-09-15, but the content it was meant to carry — the failure-class→mechanism table and the
sentence the assessment called the sharpest in the corpus ("a rule written in three places was
violated for months and obeyed from the moment it became a hook") — was never written into
`CLAUDE.md`, and `LEARNINGS_TRANSFER.md` § 6, named as its depth home, is about evolving the
transfer document instead.

**Fix:** name the architecture guide in `docs/PLAN.md` § Milestones M2, and add the six-row
"what turns a lesson into a mechanism" table to `docs/INSIGHTMINER_HARNESS.md` § 6, which is where
that reasoning now lives.

### F11 — LOW: a cadence residue in a live gate artifact, and four small day-zero items with no home

- `docs/reference/reviews/templates/external-deep-research.md` line 185 still asks reviewers "which
  designed-but-unbuilt controls must precede **the daily schedule**?" after D-30 made the schedule
  twice-weekly (line 4 of the same file was swept: "twice a week"). G34 cannot see it:
  `tests/gates/test_superseded_claims.py` scans `docs/**` minus `reference/`, plus `src/**/*.py`
  and `deploy/**` — so the templates, which `RUNBOOK.md` § 8 calls living artifacts "reviewed like
  code", sit inside the add-never-edit exclusion. This is the KI-025 class in the one artifact that
  gets pasted to outside reviewers.
- No path-resolution check covers hook scripts, the `Makefile` or `.ratchets/` (harness assessment
  § 7 day-zero item 7); G44's scope is the three routing tables, the rule files and the memory
  snapshot. Most of the `Makefile`'s exposure is covered by `make check` running the recipes.
- No re-point procedure exists for a repo or data-directory move (§ 4.26), and the workflow panel's
  "the repository move unnoticed by `doctor`" was never queued.
- The PreToolUse block on backgrounding a long collector run, proposed at day zero together with an
  irreversible-few rule, is neither built nor declined; `CLAUDE.md`'s irreversible four do not
  include it. The flock-means-alive rule, the wall-clock ceiling and stale-run detection cover most
  of the class, which is why this is low.
- `RUNBOOK.md` § 7 step 2 says "Upload the eight files of the upload set" while round one uploaded
  ten and the count depends on how the bundles split — a number in prose whose home is the builder's
  output.

**Fix:** add `docs/reference/reviews/templates/` to G34's scanned paths in
`tests/gates/test_superseded_claims.py` and sweep the brief's line 185; record the other four as
`DECISIONS.md` entries (adopt or decline) rather than leaving them unstated.

## What I could not check

- **The other seat's records.** The 2026-09-12 design reviews and the 2026-09-13 panels (ingest,
  db-integrity, ui, enforcement, adversarial) were read only where my records cite them (the probe
  plan P-01…P-17, the enforcement panel's ledger structure). Whether *their* accepted findings
  survive version two is the other seat's question.
- **Whether a cited test asserts what its row claims.** I resolved node ids structurally and read a
  few (the planted-violation gate, the duplicate-id check); I did not run `make check` or read every
  cited test body, so "carried" means stated and cited, not proven.
- **The three long 2026-09-13 assessments were read in full only in their decision-bearing
  sections** (§§ 4–7, § 9 of the harness assessment; § 4 and § 5 of the questions record; § 4 and
  § 6 of the documentation assessment) plus their opening arguments. A recommendation buried inside
  a mid-document paragraph could have escaped the extraction.
- **Whether `EARLIER_PROJECT_REFERENCE.md` may be edited in place.** Its own front matter declares
  "prune-stale for the judgements … append-only for the dated notes at the end of § 8", while
  `RUNBOOK.md` § 8 and G55 say a file under `docs/reference/` is held byte-identical to the merge
  base. F5's fix depends on which governs; I did not run `tools/doc_policy.py` to see which rule the
  tool applies to that path.
- **Round two's readiness in the packet's actual output.** I read `tools/review_packet.py`'s
  allowlist, not a built packet.

## Verdict

**The claim does not hold as stated, but it fails on one half only.**

Where it holds, it holds strongly. Every defect the rounds confirmed by reproduction — KI-009 to
KI-026 — is registered with a status that the plan, the register and the records agree on, and
every one of the version-two review's own restorations is present in `docs/PLAN.md`, checked here
by quote, along with its corrections, its swept mirrors and its two explicit retirements. All four
round-one rulings and all five testing-panel rulings are recorded with their consequences in the
tree. The doc-policy review's sixteen closures are all present with controls. The round-one fix
panel's items all landed. That is the great majority of the second half's output, and it is intact.

Where it fails, it fails on a pattern rather than at random: **items that were accepted but never
became code are the ones that went missing, and the rewrite did not cause it — the queue did.** Of
107 items, 86 are carried, 17 are missing or partial and 4 are contradicted. The four
contradictions are the serious ones (F1 the invariant severity, F2 the packet's missing policy
facts, F5 the id allocator, F6 the scope-fence claim), and three of those four are documents
claiming a discipline the tree does not implement — the failure class this project's whole
documentation apparatus exists to prevent, appearing in the places no gate reaches (a behavioural
claim without an identifier, a one-directional allowlist, a ceiling that counts rows instead of
scopes, a template inside an excluded directory).

For the specific question the main session is deciding: **F1 and F3 should be closed before tranche
B and M1b start**, because both are inputs to work that begins immediately — F1 governs every
invariant M1b and M1c add, and F3 governs a one-shot credentialed session. F2 and F9 should be
closed before the round-two packet is built. F4 belongs in the M1c brief. The rest can ride with the
next documentation pass.

**Confidence: high** on the carried/contradicted calls, each checked against the tree and quoted;
**medium** on completeness, because the three long assessments were mined section by section rather
than line by line, and a recommendation stated only in prose could have escaped (see § What I could
not check).
