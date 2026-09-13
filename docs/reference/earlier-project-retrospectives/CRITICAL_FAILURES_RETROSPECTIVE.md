# 🔥 Critical Failures Retrospective - the 15 that mattered most

> **Intent:** the single RANKED capstone view of the most consequential failures, wrong assumptions, and bad-data episodes of the bug-intelligence project's first ~3 months (Mar -> Jun 2026), assembled as the project closes on its first post-refactor version. The individual failures already have homes (the docs cited per entry); what was missing until now was ONE place that ranks them by impact, ties them to the arc of the project, and is honest about the fact that **several of the "different" failures are the same failure wearing different clothes.** This is the failure-spine companion to `STRATEGIC_DISCOVERIES_AND_PIVOTS.md` (not in the working tree; `git show d5b6ec22^:framework/docs/journey/retired/STRATEGIC_DISCOVERIES_AND_PIVOTS.md`) (the full Mar->Jun discovery/pivot arc, ~40 corrected beliefs) and [`KEY_LEARNINGS.md`](KEY_LEARNINGS.md) (the engineering-reliability log).
>
> **Why this exists (operator-surfaced 2026-06-17):** "capturing the failures is something I'm not sure we've been comprehensive enough about." The failures DID get captured - but scattered across five-plus homes, never ranked, never gathered into one progression a newcomer (or the operator, six months on) can read in one sitting. This doc is that read.
>
> **How to read the tags:** each entry is tagged ✅ **DOCUMENTED** (it already lived in a durable doc; the home is cited - this register just ranks and connects it) or 🆕 **NEWLY SURFACED** (caught in this 2026-06-17 transcript+doc sweep, not previously in a retro/learnings doc). The split answers the operator's direct question: what was already a key learning vs what this pass added.
>
> **Update policy:** APPEND-ONLY for new entries; the ranked 15 is curated - promote a new failure in only if it outranks something here, and move the displaced one to the "reserve" list. **last-verified: 2026-06-20 (extended P2: designated this doc the canonical REFUTED-CONCLUSIONS home (BACKLOG N2) - appended a "Refuted beliefs index" that ROUTES, by pointer not copy, to every scattered correction (the RESULTS_LEDGER do-not-quote NUMBERS, the U-NN rows, the NORTH_STAR_PIVOT/NARROW_CLAIMS/KEY_RETRO/KEY_LEARNINGS homes) + reconciled the failures-ranked-HERE / discovery-arc-THERE split with STRATEGIC_DISCOVERIES; cross-linked the companion DEAD_ENDS_AND_RULED_OUT.md (killed levers) and named the new check_superseded_claims.py enforcement. Ranked-15 body NOT re-attested - additive only. Predecessor 2026-06-17 (created from a two-agent sweep: full session-transcript history via `sessions.py` + the retro/reference doc family. Same day: entry B broadened from the single utf-8-codec bug into the full cross-OS failure CLUSTER - silent-vs-loud split + the 9 KI'd siblings - from the operator's "how significant was looping Windows in early" inquiry; KIs verified against KNOWN_ISSUES. No commits - staged per the standing session rule.))**

---

## The one-sentence lesson

**Almost every expensive failure here was a number (or a label, or a field) that was real but measured wrong, scoped wrong, or asked the wrong question of** - not a broken algorithm and not broken code. The code mostly worked. The framing was the failure surface. That realization is what collapsed the four north stars into three (The Memory / The Engine / The Proof, ADR-084) and made an honest ruler the center of The Proof. Full synthesis: `KEY_RETRO_PIVOT_2026-06-06.md` (not in the working tree; `git show d5b6ec22^:framework/docs/journey/retired/KEY_RETRO_PIVOT_2026-06-06.md`) + [`../journey/NORTH_STAR_PIVOT_RETROSPECTIVE.md`](../journey/NORTH_STAR_PIVOT_RETROSPECTIVE.md) §2.6 ("the same failure under different names").

---

## The ranked 15

### 1. The measurement reframe: "~69% accurate" was a leak; the real number was ~3.4%  ✅ DOCUMENTED
- **Wrong belief:** the triage scorer worked (~69% accuracy); a bigger/better model was the lever.
- **Truth:** ~69% was a train/test leak. Under a leak-free temporal split it was **~3.4%**, and a 150x retrain merely tied baseline - the signature of a leaking, uncalibrated eval. **Diagnosis is a measurement problem, not a model problem.**
- **Why it mattered most:** it is the root the whole "binding test" discipline grew from, and the single most-cited learning in the corpus. Everything below is a variation on it.
- **Home + date:** STRATEGIC_DISCOVERIES Arc #8 + §1 (May 20-23 2026); NORTH_STAR_PIVOT_RETROSPECTIVE §2.3.

### 2. Circular gold: we were grading the system against its own output  ✅ DOCUMENTED
- **Wrong belief:** the `links` / `cross_links` table was ground truth for scoring retrieval and ranking.
- **Truth:** ~40% of rows (~98% of crash links) were written by the same similarity heuristics being graded. Every recall/MRR number was inflated (bug->PR MRR ~0.49; `cross_links` coverage ~16x); the inflation reached foundation-level "dense moat" claims. Clean deterministic gold (e.g. `jira_key_commit`) already existed. Now mechanized as a regression test forbidding `synthes*` in any gold-source path.
- **Why it mattered:** it silently corrupted the evidence base that strategy was being built on - the most dangerous kind of failure, because it looked like success.
- **Home + date:** STRATEGIC_DISCOVERIES §1 (~May 31 2026); NORTH_STAR_PIVOT_RETROSPECTIVE §2.1. Appears in 5+ docs - one of the three central failures.

### 3. The denominator failures: real numbers, wrong population (the crash-blindness scare)  ✅ DOCUMENTED
- **Wrong belief:** the system was mostly crash-blind - "only ~2.9% of bugs join a crash," "~80.5% are prose-only on an unmounted SMB share." A P1 "mount the SMB share" task was created on it.
- **Truth:** the 2.9% was ONE join path (bug -> live Sentry telemetry), not the connect rate; ~16% of all bugs carry a usable extracted crash signature (**zero** from SMB); the 80.5% was a ~400-bug recent sample, not the steady state. The operator's disconfirmation prompt + a live-DB recheck caught it.
- **Why it mattered:** a real-but-mis-scoped number traveled through ~40 docs as load-bearing and nearly drove real engineering work. Birthed the master principle "scope before you weigh" and single-sourced headline numbers in DISCERNMENT.md §7.
- **Home + date:** KEY_RETRO_PIVOT_2026-06-06.md; KEY_LEARNINGS §2026-06-06; NORTH_STAR_PIVOT_RETROSPECTIVE §2.2. One of the three central failures.

### 4. First-green is not verified - banking a win on a friendly/small/permissive number  ✅ DOCUMENTED
- **Wrong belief:** an encouraging early result, or a green on a small pool, is a verified result.
- **Truth:** a hybrid-retrieval verdict from a ~2,079-item pool reversed on the real ~22,068; `recall@1000` "found it" was ~16% at a usable top-10. A finding is a HYPOTHESIS until it survives the binding test at a usable K, on the full pool, with a leak-free split. The fix is calibration, not effort.
- **Why it mattered:** it is the standing discipline that now gates every value-stage claim; the operator's own self-correction made it a master principle.
- **Home + date:** FINAL_RETRO_2026-06-01 ("what went sideways" #1); RF_RETRO_QUESTIONS §F; VALUE_STAGE_KEY_LEARNINGS. Closely fused with #1.

### 5. Sentry's own crash bucketing is fundamentally unreliable (the founding pivot)  ✅ DOCUMENTED
- **Wrong belief (Mar 2026):** trust Sentry's crash grouping.
- **Truth:** one crash handler fanned out to ~100 issues / 1.84M events; one catch-all bucket held 3,276 distinct signatures (~42-50% non-defect). This is the reason the entire clustering/fingerprint pipeline exists - the most consequential domain assumption the project had to reverse, and it did so at the very start.
- **Why it mattered:** it defined the product. Inheriting upstream grouping is acceptable only as a named decision; the Bucket Refinement Layer + the deterministic fingerprint are the response.
- **Home + date:** STRATEGIC_DISCOVERIES Arc #2 + §1 (~Mar 2026); INSIGHTS (May 18-19).

### 6. Schema-version drift across 6+ producers - the post-mortem that built `contract/`  ✅ DOCUMENTED
- **Wrong belief:** a single conceptual constant (the schema version) "can't drift - it's one thing."
- **Truth:** 6+ producers each held their own copy and silently diverged; 825K rows were stamped a stale `2.1.5` in a 2.2.2 system (KI #61). The "it's just one thing, how could it drift" mental model is exactly why it drifted. The same "consolidate later" anti-pattern shipped production bugs 4x (#61/#82/#106/#138).
- **Why it mattered:** birthed the entire `contract/` module + the 8-phase drift verifier. Schema/contract correctness is the #1 bug hot zone (~17 KIs; the top of the ~57%).
- **Home + date:** KNOWN_ISSUES KI #61; KEY_LEARNINGS; RF_BREAKAGE_PATTERNS Pattern 2.2 (Apr 19-20 2026).

### 7. Silent column drops at the NFS->DQS seam - the most-paid-for surface (KI #60/#142/#148)  ✅ DOCUMENTED
- **Wrong belief:** a lenient importer ("schema flexibility") is safe; import/migrate ordering can be trusted.
- **Truth:** #60 dropped 3 handoff cycles silently; #142 lost a 2.4.3 field (triage card production-down); #148 left all 9 schema-2.4.3 columns 100% NULL because rows imported BEFORE the migration added the columns. Three separate incidents, same seam.
- **Why it mattered:** named "the most expensive seam" (Crit-Op #11). The cure is a mesh: migrate->import ordering + producer-side emit canary + DQS-side post-import 100%-NULL canary.
- **Home + date:** KNOWN_ISSUES KI #60/#142/#148; RF_BREAKAGE_PATTERNS Cat 1 (Apr 20 -> May 21 2026).

### 8. Plausible-but-wrong: extractors reading the wrong shape, and a fixture that hid it for 2 weeks  ✅ DOCUMENTED
- **Wrong belief:** a field that validates as "present," with a green unit test, is populated correctly.
- **Truth (a family):** `event_count_90d` was a lifetime total, inflating crash rankings up to ~38x (KI #112); `release`/`culprit` were read top-level instead of under `tags`, 97% empty (KI #114); the top-frame extractor read the API shape while the corpus stored the bulk shape, so it recovered ZERO real signatures for ~2 weeks behind a passing test (KI #122); `signature_quality` was NULL on all 52,816 rows while every internal gate passed (KI #79); a classifier produced a believable 48% hang rate that would have shipped to 36K records, caught only by a domain specialist.
- **Why it mattered:** "a plausible-but-wrong fixture is worse than no test." Cure: population-floor canary per extracted field; build fixtures from real on-disk artifacts; run a stratified pilot + multi-lens review before any one-shot batch over ~1,000 derived records.
- **Home + date:** KNOWN_ISSUES KI #79/#112/#114/#122; RF_BREAKAGE_PATTERNS Pattern 1.4 (Apr -> May 2026).

### 9. Raw Jira `assignee` is not the dev owner - QE-biased by ~50x  ✅ DOCUMENTED
- **Wrong belief:** the Jira assignee field names who owns/fixes the bug.
- **Truth:** in the [company]-[org] workflow QE closes most tickets, so `bug_assignee` matched the actual fixer only **1.7%** of the time; 68.9% of assignees never committed anywhere. Dev attribution needs a priority chain (commit author -> fix-PR author -> explicit Dev field -> CODEOWNERS). Sibling correction: guessed `firstinitial+lastname` logins produced 49 dead roster entries; CODEOWNERS + git authorship are the ground truth.
- **Why it mattered:** ownership/routing is a whole north star (The Engine); building it on a field whose name lies would have poisoned every routing number. "Measure before trusting a field name's intuition."
- **Home + date:** KEY_LEARNINGS v2.3.0 + 2026-05-20/21; STRATEGIC_DISCOVERIES §1 (Apr 20 2026).

### 10. The "single largest unmined bridge" was verified dead (the customfield_30400 reversal)  ✅ DOCUMENTED
- **Wrong belief:** Jira's `customfield_30400` Dev-Status panel (present on 91.4% of bugs) was the largest untapped bug->PR link.
- **Truth:** the container is present, the content is empty - 0 of 2,031 cached and 0 of 45 live bugs carry data ([company] publishes no dev-status for [org]). The 91.4% was **container-presence verified from docs, never data-presence verified from the corpus.** `mentioned_prs` is the real path.
- **Why it mattered:** the canonical "verify the DATA exists, not just the field" lesson; it nearly anchored a major bridge-building effort on a phantom.
- **Home + date:** STRATEGIC_DISCOVERIES §1 (May 27 2026).

### 11. Impeccably measured, wrong question - prioritization AUC 0.811 answered "what did we already fix?"  ✅ DOCUMENTED
- **Wrong belief:** a high-AUC prioritization model (volume AUC 0.811, 34x lift) was answering the mission question "predict what will matter."
- **Truth:** the label was "engineering filed a Jira bug for it" - a BACKWARD label. Volume dominates a backward label by construction, and forward signals like acceleration are penalized (they look like misses). It answered "can we match past triage?" (yes) not "what matters next?" (unmeasured). The forward label is the beta->stable crossing.
- **Why it mattered:** the question-frame failure is the most expensive class, because nothing inside the work tells you the question is wrong - only stepping back does. (Even the forward replacement later had its volume-priority claim refuted; the lead-time + join mechanics stand.)
- **Home + date:** KEY_RETRO_PIVOT_2026-06-06.md (question-frame table); KEY_LEARNINGS §2026-06-05; STRATEGIC_DISCOVERIES §1 (Jun 5).

### 12. Confident NEGATIVES are claims too - three dead-ends that weren't dead  ✅ DOCUMENTED
- **Wrong belief:** three "confident negatives" were settled and could be skipped: crash-to-component attribution "fails (-13.6pp)," area-routing "is a confident negative (33.6%)," "recall is THE bottleneck."
- **Truth:** the -13.6pp was a top-10 aggregate inflated by single-component projects (near parity at top-1); the 33.6% benchmarked a thin lookup table in isolation, not the live router (withdrawn); "recall is the bottleneck" was stacked on a mis-posed eval and was downgraded to a hypothesis. "Provisional until binding test" applies to negatives too.
- **Why it mattered:** a stale negative is as expensive as a stale positive - a later session treats a dead end as settled and skips real work (cyclical waste).
- **Home + date:** STRATEGIC_DISCOVERIES Arc #14 + §1 (Jun 4 2026); RF_RETRO_QUESTIONS §F; NORTH_STAR_PIVOT_RETROSPECTIVE §2.4.

### 13. Technical quality does not validate architectural direction (and you cannot assert byte-identity past a non-deterministic stage)  ✅ DOCUMENTED
- **Wrong belief:** clean code + green tests confirm the design is right; a golden harness should assert bit-reproducible embeddings/cluster labels.
- **Truth:** `local_data_resolver` was clean with 213 green tests but architecturally backwards (a circular dependency) - reverted the same session. Separately, bge-m3/GPU embeddings are not bit-reproducible and HDBSCAN labels flip under jitter, so a byte-identity golden would have been permanently, uselessly red; it was switched to cosine-threshold / ARI at the embed boundary (an external red-team caught it before it shipped).
- **Why it mattered:** two distinct traps, one root - "green" is not the same as "right." Pre-existing test failures were also found to each hide a real regression (so "inert failures" is itself a wrong belief).
- **Home + date:** STRATEGIC_DISCOVERIES §1 (~Apr 2026 + May 20-23 2026); KEY_LEARNINGS v2.3.0 (pre-existing failures).

### 14. Process outran the work, and a big green test suite was not the safety net it looked like  ✅ DOCUMENTED
- **Wrong belief:** building governance/process artifacts is progress; a large green unit suite is a safety net.
- **Truth:** ~270 docs and ~74 ADRs accumulated before code moved - once attention shifted to moving code, modules relocated within a day. And ~13 NFS<->DQS seam guards were silently SKIPPED (path-existence guards flipped false->skip, not fail), so manual verification was the real net, not the suite. "Delete the suite to 3,000 tests" was mass-deletion-by-count, the wrong lever.
- **Why it mattered:** birthed "derive state, never narrate it," doc-creation restraint, and the test-strategy reframe from COUNT to SHAPE/RECURRENCE (aim guards at what recurs, not the finished one-off move). The apparatus-vs-product calibration theme.
- **Home + date:** FINAL_RETRO_2026-06-01 ("what went sideways" #2); RF_RETRO_QUESTIONS Theme B; STRATEGIC_DISCOVERIES §1 (Jun 2 2026).

### 15. The label-generating loop did not close, and the fleet drifted to measuring-on-history while the real gate sat at zero  ✅ DOCUMENTED (latest pivot)
- **Wrong belief:** the G4 agree/disagree feedback loop was capturing ground truth; adding measurement rigor was progress toward the mission.
- **Truth:** the Slack loop auto-promoted only explicit routing directives (a plain thumbs-up -> no label), and the first-pass card's capture seam was write-only and unread (the file did not even exist). With the human-validation keystone blocked, ~15 consecutive results-ledger rows measured machine-on-history retrieval and **zero** measured a human acting. The blocked keystone was misread as "defer human validation" instead of "find the cheapest human-validation substitute."
- **Why it mattered:** the loop generates every future eval's label - it was the foundational unbuilt build. This is the most recent pivot and named the current next gate: close the consumption loop (the per-crash dossier), not add more history-measurement.
- **Home + date:** NORTH_STAR_PIVOT_RETROSPECTIVE §2.7 + §0; VALUE_STAGE_KEY_LEARNINGS KL-5; FINAL_RETRO "further explorations" #3 (Jun 3 -> Jun 15 2026).

---

## 🆕 Newly surfaced this pass (not previously in a retro/learnings doc)

These came out of the 2026-06-17 transcript sweep. They are real, costly, and recent enough (the **June fleet-expansion window, 06-09 -> 06-16**) that they post-date most of the curated retro docs. Two of them (A, B) are the strongest "costly, real, and not in a durable retro doc" candidates and would each rank in the top half above on impact; they are grouped here so the documented spine stays readable. Several are filed as KIs but had no entry in the failure/learnings layer.

- **A. A 3-week-stale Sentry issue list silently hid 12,560 crash events.** 🆕 The bulk events fetch iterated a stale `issues_metadata.json` and skipped every new beta/stable issue (the Pass-2 refresh was not running in orchestration). 12,560 events (7,104 beta + 5,456 stable) were missing from the PRIMARY crash feed until a targeted re-fetch recovered them. Same CLASS as KI #112 but a distinct, costly incident - and a 90-day retention trigger would NOT have caught it (the real cadence intent is 3-7 days). Filed as a KI; **belongs in the learnings layer as "freshness of the source LIST is its own failure axis, separate from retention."**
- **B. The cross-OS failure CLUSTER: Mac-first assumptions surfaced together when the fleet went multi-OS - and the SILENT members were the hazard.** 🆕 (flagship) + ✅ (the KI'd siblings). The newly-surfaced flagship: the moment a Windows node read Mac-written corpus files without an explicit utf-8 codec, non-ASCII text (crash traces, Jira summaries) was silently mangled into the exact text used for signatures and scoring (fix: force `encoding="utf-8"` on read paths, a no-op on Mac) - the **OS-codec sibling of the python3.9 silent-corruption rule.** But it was not alone: the same June fleet-onboarding window surfaced a whole cluster of single-OS assumptions, already filed as KIs. The durable split is what matters - **SILENT and dangerous** (pipeline runs, output quietly wrong): KI #216 a colon in a macOS crash-filename silently dropped the attachment -> missing crash data; KI #98 lost Windows build paths -> degraded CODEOWNERS/repo-stats attribution; KI #215/#208 a node masquerading as the wrong machine -> defeated fleet-drift detection - **vs LOUD and merely painful** (crash on import/run, no bad data): KI #220 an unguarded `import fcntl` poisoned the whole sync/enrich/watchdog import chain (139 test hits); KI #221 `SIGHUP`; KI #214 `os.rename` over an existing file; KI #228 a hardcoded `model.to("mps")` wedging the embed on non-Mac; KI #222 a `'python3'` test literal. **Lesson: a Mac-first codebase meets a second OS as a CLUSTER (POSIX syscalls, filesystem semantics, text codec, GPU backend); the silent members are the python3.9-class hazard. Caught incrementally on a live fleet and fenced with `test_cross_platform_portability.py` - not in a big-bang port - which is the engineering case for looping Windows in early.** Full enumeration + RCA: [`KEY_LEARNINGS.md`](KEY_LEARNINGS.md) §2026-06-13 + [`../agent_reports/system-health/2026-06-12_fleet_portability_deep_rca.md`](../agent_reports/system-health/2026-06-12_fleet_portability_deep_rca.md).
- **C. The memory system ate the memory: `snapshot_memory.py` was silently deleting recovered-discipline memory files (KI #226).** 🆕 The export path mirrored deletions, so durable behavioral-discipline memories were being lost - a direct hit on The Memory north star's own substrate. Fixed to add/update-only; deleted files restored. High-irony, worth a permanent line.
- **D. Subagent writes are silently auto-denied under `bypassPermissions`.** 🆕 Time was spent attempting write-work through subagents before discovering writes are auto-denied by the permission config - subagents are read/investigate-shape, not write-shape. Shaped the hybrid session/subagent dispatch discipline.
- **E. The KI #142 silent-drop class re-fired in June (KI #219, FIXED 2026-06-13).** 🆕-as-a-retro-line `enrich_prs.py`'s local-raw path wrote ~12,231 rows with `schema_version=None` (it never stamped the version; the 2026-04-19 fix covered only the API path), which the DQS pre-embed gate rejects on import. Notable precisely because it shows the #1 hot zone (schema/contract drift across the seam) STILL recurring in month three, AND it is a shape-parity violation between a producer's two code paths - the exact class the 2026-04-20 shape-parity rule exists for. The guards catch it now; the class is not closed.
- **F. Doc-fixed but code-still-wrong: the crash-reach scripts kept mislabeling affected-sessions as "devices" (FIXED 2026-06-17, commits 31bae32 + f6e32d5).** 🆕 STRATEGIC_DISCOVERIES R-42 re-labeled the metric ([internal-symbol] counts sessions, an upper bound on devices, not a device count), but the SCRIPTS / dossiers still emitted "devices" and inverted the bound after the doc was corrected - a trust-survival risk on the operator-facing crash dossiers (The Proof's value vehicle). Resolved the same day this retrospective was written, by a systematic self-audit sweep across the affected dossiers. The lesson stands as history: a correction in a doc is not a correction in the code that ships to the operator - propagate a re-label to every consumer, not just the source doc.

---

> **Promoted / status (2026-06-17, verified):** A (source-LIST freshness) and B (the cross-OS cluster) now also live as a dated section in [`KEY_LEARNINGS.md`](KEY_LEARNINGS.md) §2026-06-13 (the engineering-reliability home), framed around their durable lesson. KI status: C = KI #226; E = KI #219 [FIXED 2026-06-13]; F was FIXED 2026-06-17 (the systematic reach-label device-vs-session sweep, commits 31bae32 + f6e32d5) - so F stands here as HISTORY, not a live gap. B's siblings are all KI'd + FIXED (#98, #208, #214, #215, #216, #220, #221, #222, #228 - the June cross-OS hardening cluster); **only A and B's *flagship* codec bug lack a dedicated KI** - tracked as a verify-and-file follow-up in `BACKLOG.md`.

## The reserve list (real failures, narrower - kept for completeness, not ranked)

- Gated promotion beats fusion: weighted RRF / score-fusion lost 5 independent times (signals are task-complementary, not fusion-complementary). [STRATEGIC_DISCOVERIES Jun-5]
- "Don't rebuild" misread as "don't swap models": off-the-shelf model swaps lost repeatedly (Qwen-7B -44.96pp); the lever is source-data re-embed, not a new model. [VALUE_STAGE_KEY_LEARNINGS KL-2]
- Verify is not Route: a derived subpath routing map passed token-agreement yet carried confident-WRONG sub-team rows until an 83K-PR git-authorship check. [STRATEGIC_DISCOVERIES Jun-5]
- Bot contamination nearly doubled the apparent human review corpus (40,528 `[service-account-1]`/`[service-account-2]` events); the generic `[bot]` convention is not enough - scan for project bots. [STRATEGIC_DISCOVERIES ~May 29]
- The year-typo that inflated a sub-agent's numbers 9x-24x (`2025` vs `2026` -> 13 months searched, not 30 days) - verify every number a sub-agent produces. [RF_BREAKAGE_PATTERNS 1.8]
- Corpus floored a year early (KI #116): `CUTOFF_DATE` was dead config because `EARLY_STOP_PAGES=50` terminated the date-walk before the year boundary - silent partial fetch. [KNOWN_ISSUES #116]
- EVAL-6 identity leak: 96.8% of bug->fix-PR pairs were identity-leaked; a temporally leak-free fix-PR eval is structurally impossible, so the gate becomes "leak-quantified + honestly labeled" (honest dense@10 = 49.9%). [STRATEGIC_DISCOVERIES Jun-3]
- Metric fragility: a crash-impact count swung 393 -> 918 -> 2,303 on counting convention alone - encode each metric as one tested function + a definition-hash. [STRATEGIC_DISCOVERIES Jun-3]
- KI #117 import-time config value-capture (`from M import CONST`) made GHES hit GHEC with the wrong token (silent 401) - the #1 import landmine.
- KI #145: the test-count headline drifted 57 from reality via `+N` arithmetic; KI numbers duplicated (#40/#97/#98) from grep-the-highest-and-add-one. Both now machine-allocated.

---

## Refuted beliefs index - the one place that ROUTES to every scattered correction

> **Added 2026-06-20 (P2):** this doc is the canonical REFUTED-CONCLUSIONS home (BACKLOG N2). The failures above already have homes; what was missing was ONE index that routes to every refuted *belief/number* scattered across the corpus, so a session checks here before re-quoting a settled-wrong claim. **Pointers, not copies** - each correction stays single-sourced in its home; this just names where to look.

**Killed *levers* vs refuted *beliefs* (the deliberate N2/N3 split).** This index covers refuted **beliefs/numbers** (a measurement-time "do NOT re-quote" check). The companion [`DEAD_ENDS_AND_RULED_OUT.md`](DEAD_ENDS_AND_RULED_OUT.md) covers killed **levers/approaches** (a build-time "do NOT rebuild" check). They are separate pages on purpose and cross-link each other: a wrong *number* is re-quoted; a dead *lever* is rebuilt.

**Where each refuted conclusion is single-sourced:**

| Refuted belief / number | Single-source (do NOT copy - point) |
|---|---|
| The do-not-quote NUMBERS (bug->fix-PR "64.4% top-1" / "MRR 0.49"; "2.9% join"; "80.5% prose-only"; "recall@1000 = found it"; "scorer 69%"; "area-routing FAILS 33.6%"; "crash->component FAILS -13.6pp"; "recall is THE bottleneck"; "96.8% recall"; "bug->crash 54%"; "dir-path +17.57pp"; "57.7% unmapped"; "routes the 60% majority"; "Spearman 0.90") | [`../RESULTS_LEDGER.md`](../RESULTS_LEDGER.md) ⚠ do-not-quote block (the human-readable view; the enforced view is `scripts/check_superseded_claims.py`) |
| The MED/LOW-confidence uncertainty rows (the U-NN register) | the U-NN entries cited per row above (e.g. U-61 leak, the uncertainty register) |
| The narrative correction arc (circular gold, the denominator miss, first-green, the three confident-negatives, the recall-bottleneck downgrade) | [`../journey/NORTH_STAR_PIVOT_RETROSPECTIVE.md`](../journey/NORTH_STAR_PIVOT_RETROSPECTIVE.md) §2 |
| The ~2.9% / ~80.5% denominator miss (full audit) | [`NARROW_CLAIMS_AUDIT_2026-06-06.md`](NARROW_CLAIMS_AUDIT_2026-06-06.md) + [`KEY_LEARNINGS.md`](KEY_LEARNINGS.md) §2026-06-06 |
| The question-frame failures (AUC 0.811 answered the wrong question) | `KEY_RETRO_PIVOT_2026-06-06.md` (not in the working tree; `git show d5b6ec22^:framework/docs/journey/retired/KEY_RETRO_PIVOT_2026-06-06.md`) |
| The KEY_LEARNINGS episodes (silent-failure / schema-drift / plausible-but-wrong) | [`KEY_LEARNINGS.md`](KEY_LEARNINGS.md) |
| The full corrected-beliefs discovery arc (~40 beliefs) | `STRATEGIC_DISCOVERIES_AND_PIVOTS.md` (not in the working tree; `git show d5b6ec22^:framework/docs/journey/retired/STRATEGIC_DISCOVERIES_AND_PIVOTS.md`) (see the split note below) |

**Relationship to `STRATEGIC_DISCOVERIES_AND_PIVOTS.md`:** failures are RANKED + indexed HERE (the 15 + the reserve list); the full discovery/pivot arc (every corrected belief, value-unlock, and insight, ranked or not) lives THERE. Read here for "the failures that mattered most + where every correction is single-sourced"; read there for "the whole Mar->Jun arc."

**Enforcement:** the do-not-quote NUMBERS are now mechanically guarded - `scripts/check_superseded_claims.py` greps the live routing corpus for any retired claim asserted outside its sanctioned home and flags it with file:line + the "use instead" (REMIND-level; the curated `SUPERSEDED_CLAIMS` registry is the single-source for "what is retired," kept in sync with the do-not-quote block). So a refuted number is no longer only a passive list - it has a lint.

---

## See also (the full picture)

- **The progression / arc:** `STRATEGIC_DISCOVERIES_AND_PIVOTS.md` (not in the working tree; `git show d5b6ec22^:framework/docs/journey/retired/STRATEGIC_DISCOVERIES_AND_PIVOTS.md`) - the Mar->Jun timeline of every pivot, value-unlock, insight, and corrected assumption.
- **The capstone synthesis:** `KEY_RETRO_PIVOT_2026-06-06.md` (not in the working tree; `git show d5b6ec22^:framework/docs/journey/retired/KEY_RETRO_PIVOT_2026-06-06.md`) and [`../journey/NORTH_STAR_PIVOT_RETROSPECTIVE.md`](../journey/NORTH_STAR_PIVOT_RETROSPECTIVE.md) - why the failures forced the FOUR->THREE pivot.
- **Engineering-reliability log:** [`KEY_LEARNINGS.md`](KEY_LEARNINGS.md) - the silent-failure / schema-drift / determinism hygiene.
- **The bug lineage:** [`KNOWN_ISSUES.md`](KNOWN_ISSUES.md) (every fixed bug) + [`../refactor/RF_BREAKAGE_PATTERNS.md`](../refactor/RF_BREAKAGE_PATTERNS.md) (the recurring-pattern catalogue with preventive guards).
- **The refactor retro:** `../journey/retired/FINAL_RETRO_2026-06-01.md` (not in the working tree; `git show d5b6ec22^:framework/docs/journey/retired/FINAL_RETRO_2026-06-01.md`) + [`../refactor/RF_RETRO_QUESTIONS.md`](../refactor/RF_RETRO_QUESTIONS.md).
